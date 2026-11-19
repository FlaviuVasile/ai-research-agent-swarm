# Final architecture: verified current state and target

This document distinguishes the running architecture from the still-unmet target. The target is incremental and retains SQLite/FTS5, Ollama, Streamlit, MCP, and the existing specialists.

## Current verified runtime

```mermaid
flowchart TD
    U[Streamlit corpus workspace] --> RS[ResearchService]
    M[11-tool MCP stdio server] --> RS
    RS --> CP[CorpusPipeline]
    CP --> PDF[Local PDF validation and page extraction]
    PDF --> DB[(SQLite pages, passages, metadata, FTS5)]
    DB --> KW[BM25 / normalized BM25]
    DB -. optional local vectors .-> EMB[Ollama All-MiniLM]
    KW --> QA[Shared CorpusQA]
    EMB -. semantic / hybrid modes .-> QA
    QA --> DECOMP[Question parts and per-paper retrieval]
    DECOMP --> SELECT[Bounded span selection]
    SELECT --> EXACT[Exact stored-page provenance]
    EXACT --> SYNTH[Complex-question synthesis]
    SYNTH --> CHECK[Numeric, polarity, coverage and model checks]
    CHECK -->|validated| ANSWER[Structured answer and citations]
    CHECK -->|not validated| PARTIAL[Partial answer / exact excerpts / abstention]
    ORCH[Separate fixed analyze-paper Orchestrator] --> AGENTS[PDFMaster, SummaryAgent, QuestionsAgent, LiteratureAgent]
    AGENTS --> REPORTS[Analysis outputs and OpenAlex metadata]
```

Streamlit and MCP share corpus service, retrieval and QA logic. The original paper-analysis flow is a separate fixed orchestration path. Corpus QA does not dynamically dispatch the specialist agents.

## Target incremental architecture

```mermaid
flowchart TD
    UI[Streamlit] --> S[Shared ResearchService]
    SDK[External MCP SDK client] --> S
    S --> ING[Bounded PDF ingest, normalized metadata, page-aware passages]
    ING --> STORE[(SQLite: exact pages, passages, FTS5, optional local vectors)]
    S --> ROUTER[Question intent and complexity assessment]
    ROUTER --> FAST[Fast path: normalized lexical retrieval]
    ROUTER --> ADAPT[Bounded adaptive path for complex / low-coverage questions]
    FAST --> SELECT[Relevant, section-aware, cross-paper context selection]
    ADAPT --> DECOMP[Decompose by claim / paper]
    DECOMP --> RETRIEVE[Targeted BM25; optional semantic/hybrid ablation winner]
    RETRIEVE --> SUFF[Coverage and evidence sufficiency]
    SUFF -->|insufficient and budget remains| RETRIEVE
    SUFF -->|useful specialist needed| AGENT[Existing specialist agent, explicit evidence contract]
    SUFF -->|sufficient| SYNTH[Structured scientific synthesis]
    AGENT --> SYNTH
    SELECT --> SYNTH
    SYNTH --> VALIDATE[Separate provenance, relevance, semantic, numeric and citation checks]
    VALIDATE -->|bounded correction| SYNTH
    VALIDATE -->|supported| OUT[Answer with claim-level citations]
    VALIDATE -->|uncertain| OUT2[Partial answer or justified abstention]
    OUT --> TRACE[(Correlated persisted query / model / retrieval / validation trace)]
    OUT2 --> TRACE
```

## Engineering decisions

1. Keep SQLite and FTS5 as the lexical source of truth; the pilot does not justify a vector database.
2. Keep normalized BM25 with clause splitting as the current default; reconsider after human-reviewed evaluation.
3. Use embeddings locally only when indexed and measured against lexical retrieval.
4. Preserve exact page offsets and hashes. Provenance validation, topical relevance, and semantic support are distinct outcomes.
5. Keep complex-question synthesis and correction budgeted. Do not invoke every specialist or perform unbounded retrieval.
6. Treat dynamic specialist selection, query-trace persistence for all error paths, and human-grounded claim evaluation as unfinished.

Sources: [`research_swarm/corpus/`](research_swarm/corpus/), [`research_swarm/service.py`](research_swarm/service.py), [`research_swarm/mcp_server.py`](research_swarm/mcp_server.py), [`orchestrator.py`](orchestrator.py), and [`AGENTIC_RAG_ABLATION_RESULTS.md`](AGENTIC_RAG_ABLATION_RESULTS.md).
