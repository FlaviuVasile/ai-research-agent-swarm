# Architecture

The original workflow accepts a PDF and invokes PDFMaster, SummaryAgent, QuestionsAgent and LiteratureAgent through Orchestrator. Its FAST path can select indexed excerpts. Its existing MCP tools expose the specialists and retrieve saved analyses. OpenAlex discovery primarily uses titles and should be read as discovery metadata.

```mermaid
flowchart LR
    PDF[Local scientific PDFs] --> I[Resumable PDF ingestion]
    I --> DB[(SQLite pages, passages, FTS5 and vectors)]
    MCP[MCP stdio] --> RS[ResearchService]
    ST[Streamlit corpus workspace] --> RS
    RS --> R[Scope and rank evidence]
    DB --> R
    R --> C[Budgeted JSON evidence]
    C --> Q[Corpus QA draft]
    Q --> V[Page and claim checks]
    Q -->|One follow-up query| R
    V --> O[Claims, citations and trace]
    RS --> S[Existing specialists and saved analyses]
```

Corpus QA has a separate output contract from the existing specialists. It can return scoped claims, a citation per claim, and a retrieval trace. See [the pipeline](RAG_PIPELINE.md) for validation details.
