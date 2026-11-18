# Implementation report

**The master specification is partially implemented.** Persistent corpus RAG, structured citations, bounded model-proposed retrieval and an MCP/Streamlit QA entry point are implemented. The evidence checker has limitations and the pilot does not establish reliable scientific extraction across papers.

## Architecture and scope

The original single-paper orchestrator and its specialists still run through the existing app and MCP contracts. The corpus path adds scoped ranking, context construction, a structured draft, citation resolution, deterministic numeric checks, and model entailment checking. MCP and Streamlit share the query service. See the [architecture diagram](ARCHITECTURE.md) and the [professor requirement mapping](PROFESSOR_REQUIREMENTS.md).

## Verification

- Real SDK stdio execution imported and reopened three full scientific PDFs. The evidence run checked 12 retrieved excerpts through the inspection tool and against original PDF page text. [Evidence run](../evaluation/results/corpus-evidence-live.json)
- The final generation run attempted four answerable questions. Three abstained after revision and one timed out. The no-evidence probe abstained immediately. The final run returned no generated factual claims. [Live QA outputs](../evaluation/results/corpus-rag-live.json)
- Keyword, semantic and hybrid ranking were compared on labelled passages. See the [metrics and method](SCIENTIFIC_EVALUATION.md).
- A mock-model regression verifies that a proposed follow-up can change retrieval, rejects invalid evidence and stops after two attempts. The stdio regression covers discovery, tool calls, re-ingestion and missing evidence.
- The Windows test suite recorded **163 passed in 52.53 seconds** on 18 November 2026.

## Files changed

- Application changes are in `research_swarm/corpus/`, `research_swarm/service.py`, `research_swarm/mcp_server.py`, and `research_swarm/summary_work.py`.
- QA instructions are in `prompts/baseline/` and `prompts/evidence/`.
- Regression coverage is in `tests/test_corpus.py`, `tests/test_corpus_qa.py`, and `tests/test_mcp.py`.
- The live demonstration, ranking evaluation, and prompt comparison are in `evaluation/corpus_rag_demo.py`, `evaluation/corpus_retrieval.py`, and `evaluation/corpus_prompts.py`. Their artifacts are in `evaluation/results/`.
- Usage and acceptance details are in `README.md`, `IMPLEMENTATION_STATUS.md`, and `docs/`.

## Remaining acceptance gaps

The existing summary, questions and literature tools still use their original agent-level schemas. Per-field summary validation, answered-versus-future research question classification, and literature records classified by full text, abstract or metadata coverage remain incomplete. Corpus QA can miss an answerable query or return part of a multi-paper answer. The semantic checker can accept unsupported assertions, especially when units or study context are implicit.

The pilot did not cover chunk-size ablation, held-out human review, or resource-usage measurements. Metadata registration primarily relies on supplied fields. Corpus upload registers one PDF at a time. The previous application browser run is recorded in the existing evaluation report. This implementation verified Streamlit with its automated tests.

## Demonstration

Use the [Windows startup and reproduction commands](WINDOWS_RUN_GUIDE.md). In an MCP client, ingest the three PDFs, reopen the client, list the indexed corpus, then retrieve evidence with a scoped search. Open the top chunk with `inspect_evidence` and compare the quoted substring with the PDF page. Run the QA demonstration to show the revision trace and current generation limitations.
