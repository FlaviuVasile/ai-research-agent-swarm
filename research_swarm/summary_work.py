"""Durable summary steps and bounded evidence selection over the existing corpus."""
from research_swarm.prompt_loader import load_prompt
import hashlib
from io import BytesIO
import json
import re
import time
from dataclasses import replace

from research_swarm.budgets import BudgetExceeded,remaining_document
from research_swarm.corpus.config import CorpusConfig
from research_swarm.corpus.ingest import CorpusPipeline
from research_swarm.corpus.retrieval import EvidenceRetrieval,evidence_reference
from research_swarm.corpus.store import CorpusStore
from research_swarm.telemetry import emit


def utf8_prefix(text, budget):
    return text.encode("utf-8")[:budget].decode("utf-8",errors="ignore")


class SummaryJournal:
    def __init__(self, path):
        self.store=CorpusStore(path)
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS summary_steps (
                    source TEXT NOT NULL, profile TEXT NOT NULL, step TEXT NOT NULL,
                    output TEXT NOT NULL, seconds REAL NOT NULL, created REAL NOT NULL,
                    PRIMARY KEY(source,profile,step));
                CREATE TABLE IF NOT EXISTS summary_attempts (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL, profile TEXT NOT NULL,
                    step TEXT NOT NULL, status TEXT NOT NULL, seconds REAL NOT NULL, created REAL NOT NULL);
            """)

    def get(self,source,profile,step):
        with self.store.connect() as db:
            row=db.execute("SELECT output FROM summary_steps WHERE source=? AND profile=? AND step=?",
                           (source,profile,step)).fetchone()
        return row[0] if row else None

    def save(self,source,profile,step,output,seconds,status="completed"):
        if not isinstance(output,str) or not output.strip():
            raise ValueError("Cannot checkpoint an empty summary response.")
        with self.store.connect() as db:
            db.execute("INSERT OR REPLACE INTO summary_steps VALUES (?,?,?,?,?,?)",
                       (source,profile,step,output,seconds,time.time()))
            db.execute("INSERT INTO summary_attempts(source,profile,step,status,seconds,created) VALUES (?,?,?,?,?,?)",
                       (source,profile,step,status,seconds,time.time()))

    def failed(self,source,profile,step,seconds):
        with self.store.connect() as db:
            db.execute("INSERT INTO summary_attempts(source,profile,step,status,seconds,created) VALUES (?,?,?,?,?,?)",
                       (source,profile,step,"failed",seconds,time.time()))


def select_corpus_evidence(pdf, settings, journal, progress_path=None):
    """Index the actual PDF, reuse page checkpoints, then retrieve/diversify passages."""
    parent=journal.store.path.parent
    root=parent.parent if parent.name=="research" else parent
    config=CorpusConfig(root=root,max_pdf_bytes=settings.max_pdf_bytes,max_pages=settings.max_pages,
                        pages_per_run=200,passage_chars=600,overlap_chars=60)
    pipeline=CorpusPipeline(config,journal.store)
    sha=hashlib.sha256(pdf).hexdigest()
    with journal.store.connect() as db:
        existing=db.execute("SELECT id FROM documents WHERE sha256=?",(sha,)).fetchone()
    if existing:
        document=existing[0]
    else:
        publication=journal.store.add_publication(f"Uncatalogued uploaded PDF {sha[:12]} (metadata unverified)")
        document=pipeline.collect(publication,BytesIO(pdf))
    row=journal.store.document(document)
    if row["profile"]:
        profile=json.loads(row["profile"])
        config=replace(config,passage_chars=profile["size"],overlap_chars=profile["overlap"])
        pipeline=CorpusPipeline(config,journal.store)
    while row["status"]!="complete":
        if remaining_document()<=0:
            raise BudgetExceeded("Document time budget exceeded during evidence indexing. Page checkpoints were saved.")
        count=pipeline.process(document,progress=lambda _,page,total:
            emit("activity",text=f"Indexing evidence page {page} of {total}; no LLM call"))
        row=journal.store.document(document)
        if not count and row["status"]!="complete":
            raise ValueError("Evidence indexing is owned by another worker or could not advance; retry after its lease expires.")
    retrieval=EvidenceRetrieval(journal.store,config)
    hits=retrieval.keyword("architecture operating system runtime scheduling safety security licensing introduction conclusions limitations",
                           limit=32,publication_id=row["publication_id"])
    hits=[hit for hit in hits if hit["document_id"]==document]
    # Fall back to genuine source passages, never inferred automotive claims.
    if not hits:
        with journal.store.connect() as db:
            identifiers=db.execute("SELECT id FROM passages WHERE document_id=? ORDER BY page,start_char LIMIT 32",(document,)).fetchall()
        hits=journal.store.evidence_many(item[0] for item in identifiers)
    def relevance(hit):
        text=hit["text"].casefold()
        return sum(term in text for term in ("architecture","operating system","runtime","scheduling","safety","security","licens")) + (
            3 if re.search(r"abstract|introduction|conclusion|limitation|future work",text) else 0)
    candidates=sorted(hits,key=relevance,reverse=True)
    selected=[]
    seen=set()
    for hit in candidates:
        if hit["page"] in seen:
            continue
        selected.append(hit)
        seen.add(hit["page"])
        if len(selected)>=settings.fast_evidence_limit:
            break
    budget=settings.chunk_tokens
    per=max(40,(budget-250)//max(1,len(selected))-100)
    evidence=[load_prompt("selected_evidence")]
    manifest=[]
    for hit in selected:
        excerpt=utf8_prefix(hit["text"],per)
        # Prompt identity must survive a different run/database row ID so the
        # existing response cache remains reusable. Manifest IDs resolve this
        # stable checksum/page/offset citation to the actual corpus record.
        text_sha=hashlib.sha256(hit["text"].encode()).hexdigest()
        label=f"[Text {text_sha[:16]} p{hit['page']} chars {hit['start_char']}] [Page {hit['page']}]"
        remaining=budget-len("\n\n".join(evidence).encode())-len(label.encode())-3
        excerpt=utf8_prefix(excerpt,max(0,remaining))
        if not excerpt:
            break
        evidence.append(label+"\n"+excerpt)
        manifest.append({"evidence_id":hit["id"],"document_id":document,"page":hit["page"],
                         "start_char":hit["start_char"],"end_char":hit["start_char"]+len(excerpt),
                         "sha256":sha,"text_sha256":text_sha})
    result="\n\n".join(evidence)
    if progress_path:
        progress_path.write_text(json.dumps({"mode":"FAST_RESEARCH_MODE","coverage":"selected evidence only",
            "document_id":document,"selections":manifest},indent=2),encoding="utf-8")
    emit("activity",text=f"Selected {len(selected)} source passages from {row['page_count']} PDF pages; one summary request planned")
    return result
