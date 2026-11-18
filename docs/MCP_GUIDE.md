# MCP corpus workflow

Start the stdio server using the [Windows commands](WINDOWS_RUN_GUIDE.md). Configure the client with that Python executable as the command and `-m`, `research_swarm.mcp_server`, `--pdf-root`, and your local source directory as arguments. Set the client's working directory to the repository root. Use `--corpus-root` for a separate persistent corpus.

- `ingest_paper` takes a root-relative PDF path and a publication title, with an optional DOI. Repeat the call until indexing reports complete.
- `list_indexed_papers` shows saved entries and progress.
- `search_evidence` takes a query, optional document ID, retrieval mode and top-k.
- `inspect_evidence` resolves a chunk ID returned by search or QA.
- `ask_scientific_question` returns claim text, source excerpts, offsets, provenance, and validation trace.

Existing analysis and specialist tools are documented in the [original MCP guide](../MCP_GUIDE.md).
