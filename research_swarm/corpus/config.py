from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import dotenv_values
from research_swarm.config import ROOT


@dataclass(frozen=True)
class CorpusConfig:
    root: Path = ROOT
    pages_per_run: int = 20
    documents_per_run: int = 5
    seconds_per_run: int = 30
    max_pdf_bytes: int = 50 * 1024 * 1024
    max_pages: int = 2000
    max_page_chars: int = 100000
    passage_chars: int = 1200
    overlap_chars: int = 120
    embedding_model: str = "all-minilm:latest"
    embedding_context: int = 512
    ollama_url: str = "http://127.0.0.1:11434"
    embeddings_per_run: int = 32
    retrieval_limit: int = 10
    vector_scan_limit: int = 50000

    def __post_init__(self):
        if not 1 <= self.pages_per_run <= 200 or not 1 <= self.documents_per_run <= 50:
            raise ValueError("Corpus page/document run limits are out of range.")
        if not 1 <= self.seconds_per_run <= 600 or not 1 <= self.max_pages <= 10000:
            raise ValueError("Corpus time/page limits are out of range.")
        if not 1024 <= self.max_pdf_bytes <= 512 * 1024 * 1024 or not 1000 <= self.max_page_chars <= 1000000:
            raise ValueError("Corpus PDF/page text limits are out of range.")
        if not 200 <= self.passage_chars <= 2000 or not 0 <= self.overlap_chars < self.passage_chars // 2:
            raise ValueError("Corpus passage/overlap limits are out of range.")
        if not 1 <= self.embeddings_per_run <= 256 or not 1 <= self.retrieval_limit <= 50:
            raise ValueError("Corpus embedding/retrieval limits are out of range.")
        if not 1 <= self.vector_scan_limit <= 500000:
            raise ValueError("Corpus vector scan limit is out of range.")
        if not 128 <= self.embedding_context <= 8192:
            raise ValueError("Corpus embedding context must be 128–8192.")

    @property
    def database(self):
        return Path(self.root) / "research" / "corpus.sqlite3"

    @property
    def pdf_dir(self):
        return Path(self.root) / "deCitit"

    @classmethod
    def from_env(cls):
        values = {**dotenv_values(ROOT / ".env"), **os.environ}
        fields = {"pages_per_run": "CORPUS_PAGES_PER_RUN", "documents_per_run": "CORPUS_DOCUMENTS_PER_RUN",
                  "seconds_per_run": "CORPUS_SECONDS_PER_RUN", "max_pdf_bytes": "CORPUS_MAX_PDF_BYTES",
                  "max_pages": "CORPUS_MAX_PAGES", "max_page_chars": "CORPUS_MAX_PAGE_CHARS",
                  "passage_chars": "CORPUS_PASSAGE_CHARS", "overlap_chars": "CORPUS_OVERLAP_CHARS",
                  "embeddings_per_run": "CORPUS_EMBEDDINGS_PER_RUN", "retrieval_limit": "CORPUS_RETRIEVAL_LIMIT",
                  "vector_scan_limit": "CORPUS_VECTOR_SCAN_LIMIT"}
        fields["embedding_context"] = "CORPUS_EMBEDDING_CONTEXT"
        kwargs = {field: int(values[name]) for field, name in fields.items() if values.get(name)}
        return cls(root=Path(values.get("CORPUS_ROOT") or ROOT),
                   ollama_url=values.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434",
                   embedding_model=values.get("CORPUS_EMBEDDING_MODEL") or "all-minilm:latest", **kwargs)
