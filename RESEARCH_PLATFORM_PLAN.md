# Academic research platform: phased implementation

Research objective: **Automotive-Specific Operating Systems: A Comparative Study**.

This iteration implements and verifies the smallest corpus foundation first. It does not replace the four-agent PDF workflow or claim that discovery and comparative report generation are complete.

## Phase 1 — persistent corpus and evidence retrieval (implemented)

Files are under `research_swarm/corpus/`, with a small optional workspace added to `app.py`.

- Versioned SQLite database: publication metadata, DOI/publication identities, document checksums and paths, processing state, page checkpoints, exact extracted page text, passages, local vectors and retrieval history.
- Operator-supplied PDFs are streamed to `deCitit/<sha256>.pdf`. Invalid, encrypted, oversized and conflicting document associations are rejected. Remote collection and access-right verification are not implemented yet; import only material you are entitled to store.
- DOI normalization/deduplication and conservative title/year/first-author deduplication. Conflicting DOIs require review. Incomplete metadata is kept separate instead of guessing duplicate publications. Reconciliation of provider records and aliases is a phase-2 task.
- A page-by-page bounded scheduling slice processes at most 20 pages across at most five documents by default. It has a 30-second soft deadline, file/page/text bounds, and bounded passage sizes. It never assembles the full document text for a model and does not raise `MAX_CHUNKS`.
- Each page's exact text, passages, FTS entries and checkpoint commit atomically. Document leases prevent simultaneous ingestion of the same PDF. Caught failures release the lease; after an abrupt process death, a lease expires in 120 seconds. Resume checks the file checksum and extraction profile. Explicit reset invalidates derived pages/vectors; retired evidence IDs are never reused.
- PDF page numbers and character ranges preserve provenance. Sections are recognized heuristically from headings and used as passage boundaries where possible. Printed/logical page numbers and a full document outline parser are not implemented.
- SQLite FTS5 keyword retrieval works with no model or network. Optional semantic retrieval uses local Ollama embeddings, persistent model-digest-keyed vectors, and bounded exact cosine search. No vector service or paid API is introduced. Retrieval records exact evidence IDs in history.
- CLI and an opt-in Streamlit corpus workspace provide registration, resume, progress, metadata inspection, indexing and evidence search. The original UI remains available.

Phase-1 verification gate: persistent/idempotent storage, metadata deduplication, invalid PDF handling, atomic page rollback, interrupted/abandoned-worker recovery, Unicode/text offsets, long-document scheduling limits, retrieval references, vector persistence/cache reuse, local-only embedding requests, and the complete legacy regression suite must pass. A real local embedding smoke test must separately verify the installed model. See the results below and the README.

## Phase 2 — discovery and legally accessible collection (planned)

Add a Discovery Agent with provider adapters for OpenAlex and Crossref, and optional Semantic Scholar when accessible. The existing OpenAlex client remains the per-PDF literature helper; it is not yet a paginated corpus discovery service.

Persist each query, provider, filters, cursor/page, timestamp, returned provider IDs, raw metadata provenance and errors. Support multiple queries and publication-date filters. Persist checkpoints before requesting another page so interrupted searches can resume. Establish provider-specific throttling, contact/identification headers where required, Retry-After handling, explicit quotas and terms-of-service checks using current official documentation.

Add a Collection Agent that only follows verified open-access full-text locations or operator-authorized sources. Preserve source URL, access/license evidence and download timestamp. Stream downloads with content/type/size checks; validate redirect destinations and block private/internal targets, credential-bearing URLs and access-control circumvention. Keep unavailable and restricted records as metadata; never invent a PDF or citation. Reconcile duplicates and alternate versions without silently merging different DOIs.

Gate: mocked pagination, date filters, rate-limit/retry behavior, cursor recovery, identity conflicts, legal-access decisions, safe downloads and database provenance tests. Live provider access must be reported separately from mocks.

## Phase 3 — evidence-based automotive synthesis and reports (planned)

Add an Evidence Agent that classifies retrieved passages into claims and explicitly distinguishes quotations, author findings, vendor statements and model inference. Each claim must reference immutable document/checksum/page/passage IDs. Reuse the existing LLM facade, summaries/questions specialists and cache; supply bounded retrieved evidence rather than an entire corpus.

Add a Comparison Agent with a reviewed taxonomy:

| Category | Subjects |
| --- | --- |
| Standardized automotive software platforms | AUTOSAR Classic; AUTOSAR Adaptive |
| Operating-system subjects | QNX Neutrino; Embedded Linux; Android Automotive OS; FreeRTOS; Zephyr |

The taxonomy is a research organizing scheme, not evidence for platform capabilities. Preserve the distinctions between a standard, implementations/stacks, a kernel, an OS/distribution and a product version. Compare architecture, real-time behavior, functional safety, cybersecurity, hardware needs, resource consumption, portability, licensing and automotive applications only when the retrieved sources support the particular version and claim. Leave missing evidence explicitly unfilled.

Add a Report Agent producing:

- `reports/01-state-of-the-art.md`
- `reports/02-autosar-architecture.md`
- `reports/03-comparative-analysis.md`
- `references/bibliography.bib`
- `references/literature-matrix.md`

Do not create apparently completed reports from an empty/synthetic corpus. Bibliography fields must derive from stored verified metadata, and important report claims must resolve to stored source passages. Record query/model/profile provenance, contradictions, uncertainty and missing evidence. Add claim-to-passage and report-version tables before emitting reusable conclusions; exact retrieved passages alone are the current foundation.

Gate: evidence-agent schema validation, citation resolution and versioning, claim entailment review, contradictory/missing evidence, reproducible report snapshots, BibTeX escaping and the full test suite. A comparative research-quality evaluation and human citation review are required in addition to software tests.

## Limits and operating model

The hardware target remains 16 GB RAM and a 4 GB RTX 3050 Ti. The optional embedding model is `all-minilm:latest`, approximately 46 MB, with a default 512-token context; this does not increase the generation model's 8192-token context. No automatic model pull occurs in application code. A model was explicitly downloaded during verification.

Page extraction is incremental at the application level, but PyMuPDF can allocate native memory while parsing a file/page. The text-size check occurs after extraction, and the time deadline is checked between pages or embedding batches; it cannot preempt an in-flight native extraction or HTTP request. This foundation does not enforce a hard OS memory/CPU budget. Production processing of untrusted PDFs needs process isolation, watchdogs, quotas and storage-retention controls.

Vector search uses a persistent SQLite vector table and exact bounded scanning, not an approximate-nearest-neighbor index. Default scan cap is 50,000 vectors. If the cap is exceeded, filter by publication or deliberately configure a larger bounded scan; no subset is silently treated as the complete corpus. Search quality is not established by synthetic ranking tests. Separate keyword and semantic searches are supported; hybrid rank fusion and generative RAG answers remain later work.

No OCR, remote discovery/download pipeline, automated rights determination, specialized comparison/report agents, generated corpus conclusions or requested research output files are included in phase 1. Their tests are future phase gates, not claimed passed tests. The existing per-paper Markdown reports are unchanged.

## Verification results — 4 November 2026

The final complete foundation suite passed **102 tests in 47.82 seconds**, with no failures or skips, including the original 78 tests and 24 additional corpus/UI cases. An earlier full run passed in 61.70 seconds. One earlier targeted run exposed corrupt-PDF cleanup on Windows; the implementation was repaired and the expanded corrupt/truncated-PDF tests passed.

The scale fixture persisted **201 publication records** and processed a **41-page generated PDF** over 21 slices with a two-page per-slice cap. This verifies bounded scheduling and persistence, not throughput or research quality on hundreds of real PDFs.

A live local smoke test imported two synthetic fixture publications/four PDF pages, resumed ingestion across pipeline instances, indexed four passages with actual `all-minilm` inference, skipped all already-indexed passages on repeat, and retrieved the expected automotive page through both keyword and semantic queries. There was one four-item embedding batch and one query embedding; the top semantic score was approximately 0.674. It completed in **6.71 seconds**, with HTTP restricted to loopback. Artifacts are in ignored `.runtime/corpus-live-944755d6/`. No OpenAI or other paid request was made. These fixtures are not academic publications and are not research findings.

SQLite 3.45.1 with FTS5 was verified in the installed environment. Source compilation, `pip check`, CLI help and an actual CLI keyword search against the live fixture corpus passed. Browser-native file selection/downloads, native-memory profiling and a production corpus benchmark were not performed. No commits or pushes were made.
