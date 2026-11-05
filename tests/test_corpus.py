import asyncio
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pymupdf
import pytest

from research_swarm.corpus.config import CorpusConfig
from research_swarm.corpus.ingest import CorpusPipeline, passages
from research_swarm.corpus.retrieval import EvidenceRetrieval, LocalEmbeddings, evidence_reference, unit_vector
from research_swarm.corpus.store import CorpusStore


def pdf(pages=3, blank=False):
    with pymupdf.open() as doc:
        for number in range(pages):
            page = doc.new_page()
            if not blank:
                page.insert_text((72,72), f"1 Architecture\nPage {number+1}: QNX microkernel scheduling.\n"
                                 "AUTOSAR Adaptive is a standardized software platform.\n"
                                 "No hardware performance claim is established by this synthetic example.")
        return doc.tobytes()


@pytest.fixture
def pipeline(tmp_path):
    return CorpusPipeline(CorpusConfig(root=tmp_path,pages_per_run=2,passage_chars=200,overlap_chars=20))


def register(pipeline, data=None, title="Synthetic automotive paper", doi="10.1234/synthetic"):
    publication = pipeline.store.add_publication(title,doi,authors=["Test Author"],year=2024)
    document = pipeline.collect(publication,BytesIO(data if data is not None else pdf()))
    return publication,document


def test_storage_doi_identity_deduplication_and_persistence(pipeline):
    store = pipeline.store
    first = store.add_publication("Scheduling", "https://doi.org/10.1234/ABC")
    assert store.add_publication("Different provider title", "doi:10.1234/abc") == first
    second = store.add_publication("An OS study", authors=["A. Author"],year=2020)
    assert store.add_publication("AN OS STUDY", authors=["a. author"],year=2020) == second
    assert store.add_publication("An OS study","10.9999/new",authors=["A. Author"],year=2020) == second
    with pytest.raises(ValueError,match="Conflicting DOI"):
        store.add_publication("An OS study","10.9999/conflict",authors=["A. Author"],year=2020)
    reopened = CorpusStore(store.path)
    with reopened.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 2


def test_incomplete_metadata_does_not_guess_duplicates(pipeline):
    a = pipeline.store.add_publication("A common title")
    b = pipeline.store.add_publication("A common title")
    assert a != b
    with pytest.raises(ValueError):
        pipeline.store.add_publication("Invented DOI",doi="made-up")


def test_collection_hash_dedup_and_references(pipeline):
    data = pdf()
    publication,document = register(pipeline,data)
    assert pipeline.collect(publication,BytesIO(data)) == document
    row = pipeline.store.document(document)
    assert (pipeline.config.pdf_dir / row["relative_path"]).read_bytes() == data
    other = pipeline.store.add_publication("Different publication")
    with pytest.raises(ValueError,match="another publication"):
        pipeline.collect(other,BytesIO(data))
    assert not list(pipeline.config.pdf_dir.glob("*.part"))


@pytest.mark.parametrize("data", [b"",b"not a PDF",b"%PDF-1.7\ninvalid truncated data"])
def test_invalid_collection_leaves_no_document(pipeline,data):
    publication = pipeline.store.add_publication("Invalid test")
    with pytest.raises(ValueError):
        pipeline.collect(publication,BytesIO(data))
    assert pipeline.store.documents() == []
    assert not list(pipeline.config.pdf_dir.iterdir())


def test_encrypted_and_oversize_collection(pipeline):
    with pymupdf.open(stream=pdf(),filetype="pdf") as doc:
        data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,owner_pw="owner",user_pw="reader")
    with pytest.raises(ValueError,match="Password"):
        register(pipeline,data)
    small = CorpusPipeline(replace(pipeline.config,max_pdf_bytes=1024),pipeline.store)
    with pytest.raises(ValueError,match="MAX_PDF_BYTES"):
        register(small,pdf(pages=10))


def test_resumable_page_slices_and_exact_evidence(pipeline):
    publication,document = register(pipeline)
    first = pipeline.run()
    assert first[0]["pages_processed"] == 2
    assert pipeline.store.document(document)["last_page"] == 2
    assert pipeline.store.document(document)["status"] == "pending"
    reopened = CorpusPipeline(pipeline.config)
    assert reopened.run()[0]["pages_processed"] == 1
    assert reopened.store.document(document)["status"] == "complete"
    assert reopened.run() == []
    hits = EvidenceRetrieval(reopened.store,pipeline.config).keyword("QNX scheduling")
    assert hits and all(hit["publication_id"] == publication for hit in hits)
    with reopened.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 3
        for hit in hits:
            page = db.execute("SELECT text FROM pages WHERE document_id=? AND number=?",(document,hit["page"])).fetchone()[0]
            assert page[hit["start_char"]:hit["end_char"]] == hit["text"]
            assert hit["sha256"] and hit["doi"] == "10.1234/synthetic"
            assert evidence_reference(hit).endswith(f"/E{hit['id']}]")
            assert reopened.store.evidence(hit["id"])["text"] == hit["text"]


def test_exception_keeps_committed_pages_and_resumes(pipeline):
    _,document = register(pipeline)
    def interrupt(identifier,page,total):
        raise RuntimeError("injected interruption")
    with pytest.raises(RuntimeError):
        pipeline.process(document,progress=interrupt)
    assert pipeline.store.document(document)["last_page"] == 1
    assert pipeline.store.document(document)["status"] == "failed"
    pipeline.process(document)
    assert pipeline.store.document(document)["status"] == "complete"
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 3


def test_abandoned_worker_lease_recovers_after_expiry(pipeline):
    _,document = register(pipeline)
    def kill(*args):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        pipeline.process(document,progress=kill)
    assert pipeline.store.document(document)["last_page"] == 1
    assert pipeline.process(document) == 0  # Another worker still owns the lease.
    with patch("research_swarm.corpus.store.time.time",return_value=time.time()+121):
        assert pipeline.process(document) == 2
    assert pipeline.store.document(document)["status"] == "complete"


def test_page_transaction_rolls_back_evidence_and_checkpoint(pipeline):
    _,document = register(pipeline)
    owner = pipeline.store.claim(document,"test-profile")
    with pytest.raises(sqlite3.IntegrityError):
        pipeline.store.commit_page(document,owner,1,"text",[(0,4,None,"text"),(0,4,None,"text")])
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM passages").fetchone()[0] == 0
    assert pipeline.store.document(document)["last_page"] == 0


def test_pdf_change_is_detected_before_resume(pipeline):
    _,document = register(pipeline)
    pipeline.process(document,page_budget=1)
    row = pipeline.store.document(document)
    with (pipeline.config.pdf_dir / row["relative_path"]).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError,match="checksum"):
        pipeline.process(document)
    assert pipeline.store.document(document)["last_page"] == 1


def test_limits_blank_pages_and_section_splitting(pipeline):
    _,document = register(pipeline,pdf(blank=True))
    pipeline.run()
    outcome = pipeline.run()
    assert outcome[0]["status"] == "failed" and "OCR" in outcome[0]["error"]
    text = "1 Introduction\n" + "evidence " * 100
    fragments = list(passages(text,200,20))
    assert all(end-start <= 200 and text[start:end] == body for start,end,section,body in fragments)
    assert fragments[0][2] == "1 Introduction"
    covered = set()
    for start,end,_,_ in fragments:
        covered.update(range(start,end))
    assert len(covered) == len(text)
    section_text = "1 Introduction\nIntro text.\n2 Architecture\nKernel evidence."
    section_parts = list(passages(section_text,200,20))
    assert len(section_parts) == 2
    assert section_parts[0][2] == "1 Introduction"
    assert section_parts[1][2] == "2 Architecture"
    assert section_parts[0][1] == section_parts[1][0]


def test_changed_extraction_profile_requires_explicit_reset(pipeline):
    _,document = register(pipeline)
    pipeline.run()
    old = EvidenceRetrieval(pipeline.store,pipeline.config).keyword("QNX")[0]["id"]
    altered = CorpusPipeline(replace(pipeline.config,passage_chars=300),pipeline.store)
    with pytest.raises(ValueError,match="settings changed"):
        altered.process(document)
    pipeline.store.reset(document)
    with pytest.raises(ValueError,match="Unknown evidence"):
        pipeline.store.evidence(old)
    altered.process(document)
    new = EvidenceRetrieval(pipeline.store,altered.config).keyword("QNX")[0]["id"]
    assert new > old  # Retired references cannot accidentally identify a new passage.


def test_hundreds_of_records_and_long_document_are_bounded(pipeline):
    for index in range(200):
        pipeline.store.add_publication(f"Publication {index}",doi=f"10.1234/p{index}")
    _,document = register(pipeline,pdf(pages=41))
    for _ in range(21):
        results = pipeline.run()
        assert sum(row["pages_processed"] for row in results) <= 2
    assert pipeline.store.document(document)["status"] == "complete"
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 201
        assert db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 41


def test_keyword_query_safety_limits_and_history(pipeline):
    publication,_ = register(pipeline)
    pipeline.run()
    search = EvidenceRetrieval(pipeline.store,pipeline.config)
    assert search.keyword('QNX " OR *',limit=1,publication_id=publication)
    assert search.keyword("unfindableterm") == []
    with pytest.raises(ValueError):
        search.keyword("QNX",limit=1000)
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM retrieval_history").fetchone()[0] == 2


class FakeEmbeddings:
    def __init__(self):
        self.calls = 0
    async def identity(self):
        return "local-fixture:weights-v1"
    async def embed(self,texts):
        self.calls += 1
        return [[1.,0.] if "QNX" in text else [0.,1.] for text in texts]


def test_persistent_semantic_vectors_resume_and_retrieve(pipeline):
    _,document = register(pipeline)
    pipeline.run()
    embeddings = FakeEmbeddings()
    retrieval = EvidenceRetrieval(pipeline.store,pipeline.config,embeddings)
    assert asyncio.run(retrieval.index(limit=1)) == 1
    assert asyncio.run(retrieval.index()) > 0
    before = embeddings.calls
    assert asyncio.run(retrieval.index()) == 0
    assert embeddings.calls == before
    reopened = EvidenceRetrieval(CorpusStore(pipeline.store.path),pipeline.config,embeddings)
    results = asyncio.run(reopened.semantic("QNX",limit=2))
    assert results[0]["score"] > .99
    assert reopened.store.evidence(results[0]["id"])["document_id"] == document
    pipeline.store.reset(document)
    with pipeline.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 0


def test_semantic_scan_limit_is_explicit(pipeline):
    register(pipeline)
    pipeline.run()
    embeddings = FakeEmbeddings()
    retrieval = EvidenceRetrieval(pipeline.store,pipeline.config,embeddings)
    asyncio.run(retrieval.index())
    retrieval.config = replace(pipeline.config,vector_scan_limit=1)
    with pytest.raises(ValueError,match="scan limit"):
        asyncio.run(retrieval.semantic("QNX"))


@pytest.mark.parametrize("vector", [[0.,0.],[float("nan"),1.],["text"],[]])
def test_invalid_vectors_are_rejected(vector):
    with pytest.raises(ValueError):
        unit_vector(vector)


def test_embedding_api_is_local_and_does_not_truncate(pipeline):
    embeddings = LocalEmbeddings(pipeline.config)
    embeddings.guard._identity = "installed-local-model"
    response = httpx.Response(200,json={"embeddings":[[1.,2.]]},
                             request=httpx.Request("POST","http://127.0.0.1:11434/api/embed"))
    with patch("httpx.AsyncClient.post",AsyncMock(return_value=response)) as post:
        vectors = asyncio.run(embeddings.embed(["QNX scheduling"]))
    payload = post.await_args.kwargs["json"]
    assert payload["truncate"] is False and payload["options"]["num_ctx"] == 512
    assert len(vectors) == 1
    with pytest.raises(ValueError,match="loopback"):
        LocalEmbeddings(replace(pipeline.config,ollama_url="https://api.openai.com"))


def test_evidence_batch_preserves_rank_and_uses_one_connection(pipeline):
    register(pipeline)
    pipeline.run()
    hits = EvidenceRetrieval(pipeline.store, pipeline.config).keyword("QNX scheduling")
    identifiers = [hit["id"] for hit in reversed(hits)]
    identifiers.append(identifiers[0])
    with patch.object(pipeline.store, "connect", wraps=pipeline.store.connect) as connect:
        rows = pipeline.store.evidence_many(iter(identifiers))
    assert connect.call_count == 1
    assert [row["id"] for row in rows] == identifiers
    assert rows[0] == rows[-1]
    assert rows[0] is not rows[-1]
    assert pipeline.store.evidence_many([]) == []
    with pytest.raises(ValueError, match="Unknown evidence"):
        pipeline.store.evidence_many([identifiers[0], -1])
