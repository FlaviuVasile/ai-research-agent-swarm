# RAG pipeline

Streamlit corpus QA and MCP `ask_scientific_question` share
`ResearchService.ask_corpus` → `CorpusQA` → `EvidenceRetrieval`. The default
strategy is `spans`; the older draft/revision workflow remains available only
through the internal `strategy="legacy"` option. Corpus QA does not invoke the
Summary, Questions or Literature specialist agents.

PyMuPDF extracts text by page into a checkpointed SQLite corpus. The original
PDF is identified by SHA-256. Pages, section labels when recognized, passages,
and exact character offsets are stored locally. Defaults are 1,200 characters
per passage with up to 120 characters of overlap; chunking prefers paragraph
and recognized heading boundaries. Section detection is page-local. Tables,
equations, scans and complex reading order can degrade coverage; OCR is not
implemented.

Keyword BM25 is the default. Scientific morphology is normalized before
lexical search and multipart questions are retrieved clause-by-clause. Local
semantic search and reciprocal-rank-fusion hybrid search remain optional and
require previously indexed local embeddings. Document filters are applied
before ranking. The exact ranking method should be revisited against the
human-reviewed benchmark when available; the current six-question retrieval
pilot is not ground truth.

For a simple question, one model call selects exact page excerpts. Their
provenance is rechecked against stored page text and offsets. These fast-path
responses use `evidence_available` or `partial_evidence`; they do **not** claim
that a generated scientific interpretation was semantically verified.

For multipart or complex questions, the selector can request at most one
targeted follow-up retrieval per unanswered part, within the original
document scope. A second selection call is made only if that retrieval returns
new candidate spans. The selected, exact excerpts are sent to a structured
synthesis prompt. Each generated claim must cite selected span IDs; invalid
span IDs are rejected. Deterministic checks reject digit-form values absent
from the cited spans and flag direct source-polarity conflicts before a separate
local-model semantic support assessment. Unsupported or incomplete drafts
receive at most one correction and another support check.
For comparisons between named papers, retrieval is scoped per paper and
selection requires a span from each side when available. If synthesis still
fails its support check, the response exposes exact source excerpts as
`partial_evidence`; it does not present them as a validated comparison.
The comparison trace distinguishes papers with selected evidence,
`missing_documents` (no selected evidence), and
`unvalidated_documents` (evidence exists but no supported comparison claim was
validated).
The maximum is six model calls for this path (two selection, two synthesis,
two validation), subject to the 90-second per-model-call and 600-second
document-operation defaults. The validator is a model judgment, not human
verification or proof. `model_checked_answer`, `partial_evidence`,
`evidence_only`, and `insufficient_evidence` distinguish the outcomes.

Each response includes retrieval traces, selected source spans, validation
outcomes and per-stage model-call counts. Retrieval queries are recorded in
SQLite, but the complete QA answer and correlated model/validation trace are
not yet persisted as a single durable run record. Semantic and hybrid requests
can fail if embeddings are unavailable; they do not silently fall back.
Pending ingestion exposes only pages committed so far.
