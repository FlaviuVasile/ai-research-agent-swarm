"""Bounded local collection and page-transaction ingestion. No model calls."""
import hashlib
import gc
import json
from pathlib import Path
import re
import time
from uuid import uuid4

import pymupdf

from .config import CorpusConfig
from .store import CorpusStore


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def passages(text, size, overlap):
    """Character offsets refer to exact page text, never generated paraphrases."""
    section = None
    headings = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if len(stripped) <= 100 and re.match(
                r"^(?:\d+(?:\.\d+)*[.\s]+\w|abstract\b|introduction\b|conclusions?\b|references\b)", stripped, re.I):
            headings.append((offset, stripped))
        offset += len(line)
    start = 0
    while start < len(text):
        # Prefer paragraph boundaries, then hard bound unusually long paragraphs.
        end = min(start + size, len(text))
        section_break = False
        if end < len(text):
            boundary = text.rfind("\n\n", start + size // 2, end)
            if boundary >= 0:
                end = boundary + 2
        for position, heading in headings:
            if start < position < end and text[start:position].strip():
                end = position
                section_break = True
                break
        for position, heading in headings:
            if position <= start:
                section = heading
        if text[start:end].strip():
            yield start, end, section, text[start:end]
        if end == len(text):
            break
        start = end if section_break else max(start + 1, end - overlap)


class CorpusPipeline:
    def __init__(self, config: CorpusConfig | None = None, store: CorpusStore | None = None):
        self.config = config or CorpusConfig.from_env()
        self.store = store or CorpusStore(self.config.database)

    def collect(self, publication_id, stream):
        """Import an operator-supplied PDF they are entitled to store.

        Remote downloading and licence checks belong to the next collection phase.
        Only a bounded copy buffer is allocated; no full PDF byte array is created.
        """
        config = self.config
        config.pdf_dir.mkdir(parents=True, exist_ok=True)
        temporary = config.pdf_dir / (uuid4().hex + ".part")
        digest = hashlib.sha256()
        total = 0
        try:
            with temporary.open("xb") as target:
                while block := stream.read(65536):
                    total += len(block)
                    if total > config.max_pdf_bytes:
                        raise ValueError("PDF exceeds CORPUS_MAX_PDF_BYTES; use a smaller document.")
                    target.write(block)
                    digest.update(block)
            if not total:
                raise ValueError("PDF is empty.")
            with temporary.open("rb") as header:
                if b"%PDF-" not in header.read(1024):
                    raise ValueError("Invalid PDF header.")
            invalid = False
            try:
                with pymupdf.open(temporary, filetype="pdf") as pdf:
                    if not pdf.is_pdf:
                        raise ValueError("Only PDF documents are supported.")
                    if pdf.needs_pass:
                        raise ValueError("Password-protected PDFs are not supported.")
                    page_count = len(pdf)
                    if not 1 <= page_count <= config.max_pages:
                        raise ValueError("PDF exceeds CORPUS_MAX_PAGES or contains no pages.")
            except (pymupdf.FileDataError, pymupdf.EmptyFileError):
                invalid = True
            if invalid:
                # Some PyMuPDF builds leave a cyclic partial Document on failed
                # construction. Release it after the exception traceback clears,
                # before unlinking the temporary file on Windows.
                gc.collect()
                raise ValueError("Invalid or corrupt PDF.")
            sha = digest.hexdigest()
            filename = sha + ".pdf"
            path = config.pdf_dir / filename
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if not db.execute("SELECT id FROM publications WHERE id=?", (publication_id,)).fetchone():
                    raise ValueError("Unknown publication identifier.")
                old = db.execute("SELECT * FROM documents WHERE sha256=?", (sha,)).fetchone()
                if old and old["publication_id"] != publication_id:
                    raise ValueError("This PDF already belongs to another publication; reconcile its metadata first.")
                if path.exists():
                    if file_hash(path) != sha:
                        raise ValueError("Stored PDF checksum mismatch; restore the original file before proceeding.")
                else:
                    temporary.replace(path)
                if old:
                    return old["id"]
                identifier = uuid4().hex
                db.execute("INSERT INTO documents(id,publication_id,sha256,relative_path,page_count,updated) VALUES (?,?,?,?,?,?)",
                           (identifier,publication_id,sha,filename,page_count,time.time()))
                return identifier
        finally:
            temporary.unlink(missing_ok=True)

    def process(self, identifier, *, page_budget=None, deadline=None, progress=None):
        config = self.config
        budget = config.pages_per_run if page_budget is None else min(page_budget, config.pages_per_run)
        if budget < 1:
            return 0
        deadline = min(deadline or float("inf"), time.monotonic() + config.seconds_per_run)
        profile = json.dumps({"version": 1, "pymupdf": pymupdf.VersionBind,
                              "size": config.passage_chars, "overlap": config.overlap_chars}, sort_keys=True)
        owner = self.store.claim(identifier, profile)
        if owner is None:
            return 0
        processed = 0
        try:
            row = self.store.document(identifier)
            path = (config.pdf_dir / row["relative_path"]).resolve()
            if path.parent != config.pdf_dir.resolve():
                raise ValueError("Document path is outside deCitit.")
            if path.stat().st_size > config.max_pdf_bytes or row["page_count"] > config.max_pages:
                raise ValueError("Document exceeds the current corpus size/page limits.")
            if file_hash(path) != row["sha256"]:
                raise ValueError("PDF checksum mismatch; evidence cannot be resumed against a changed file.")
            with pymupdf.open(path) as pdf:
                for index in range(row["last_page"], len(pdf)):
                    if processed >= budget or time.monotonic() >= deadline:
                        break
                    text = pdf[index].get_text("text", sort=True)
                    if len(text) > config.max_page_chars:
                        raise ValueError("Page exceeds CORPUS_MAX_PAGE_CHARS; extraction stopped without truncation.")
                    self.store.commit_page(identifier, owner, index + 1, text,
                                           list(passages(text,config.passage_chars,config.overlap_chars)))
                    processed += 1
                    if progress:
                        progress(identifier, index + 1, len(pdf))
            current = self.store.document(identifier)
            status = "complete" if current["last_page"] == current["page_count"] else "pending"
            if status == "complete":
                with self.store.connect() as db:
                    readable = db.execute("SELECT 1 FROM passages WHERE document_id=? LIMIT 1", (identifier,)).fetchone()
                if not readable:
                    raise ValueError("No readable text; OCR is not implemented.")
            self.store.release(identifier, owner, status)
            return processed
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else "Extraction interrupted; resume from the last committed page."
            self.store.release(identifier, owner, "failed", message)
            raise

    def run(self, progress=None):
        """One bounded scheduling slice; restart/rerun until the queue is complete."""
        remaining = self.config.pages_per_run
        deadline = time.monotonic() + self.config.seconds_per_run
        results = []
        for document in self.store.documents(limit=self.config.documents_per_run, pending_only=True):
            if remaining <= 0 or time.monotonic() >= deadline:
                break
            try:
                count = self.process(document["id"], page_budget=remaining, deadline=deadline, progress=progress)
                remaining -= count
                results.append({"document_id":document["id"], "pages_processed":count,
                                "status":self.store.document(document["id"])["status"]})
            except Exception:
                # One failed PDF does not discard another paper's committed evidence.
                row = self.store.document(document["id"])
                committed = row["last_page"] - document["last_page"]
                remaining -= committed
                results.append({"document_id":document["id"], "pages_processed":committed,
                                "status":"failed", "error":row["error"] or "Document processing failed."})
        return results
