# MCP integration guide

Use the official Python MCP SDK in stdio mode. On Windows, run from the repository root.

```powershell
.\.venv-swarm\Scripts\python.exe -m research_swarm.mcp_server --pdf-root .\.runtime\evaluation-papers --corpus-root .\.runtime\professor-demo
```

A client lists tools, calls `ingest_paper` with a root-relative filename and title, then uses `list_indexed_papers` to confirm indexing. `search_evidence` and `ask_scientific_question` accept either a single `document_id` or a list of up to eight `document_ids`. Leave both unspecified for the whole corpus. `inspect_evidence` resolves a chunk for independent review. Existing specialist and saved-result tools remain available.

Corpus QA returns `supported_claims`, `partial_evidence`, or `insufficient_evidence`. Claims marked `source_excerpt` include the raw quote, document checksum, PDF page, chunk and character offsets. Relevance is model-selected and provenance is checked against the stored page. Client errors are separate from insufficient evidence.

[Live SDK release log](evaluation/results/span-engineering-release/mcp-acceptance.json) · [Two-paper scope recheck](evaluation/results/span-engineering-release/mcp-comparison-recheck.json) · [Original specialist client verification](evaluation/results/final-acceptance/mcp-specialists.json)
