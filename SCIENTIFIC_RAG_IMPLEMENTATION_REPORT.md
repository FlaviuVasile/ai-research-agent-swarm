# Scientific RAG implementation report

**Status:** targeted implementation verified; scientific acceptance is not yet met.  
**Runtime checked:** 2026-11-19, Windows, local Ollama.  
**Scope:** preserve the existing Streamlit app, specialist agents, SQLite/FTS5 corpus, local Ollama, and MCP SDK server.

## Result

The existing application was incrementally hardened rather than rewritten. The corpus QA path now normalizes scientific terminology (including beta notation), retrieves comparison evidence separately per named paper, requires document coverage for validated comparison claims, verifies citation spans against stored PDF page text, checks numeric fidelity and source polarity, bounds synthesis/correction attempts, and returns exact source excerpts with an explicit partial status when synthesis is not validated. Streamlit and MCP use the shared `ResearchService` corpus QA path. The MCP smoke client discovered 11 tools.

The answer-quality gap remains material. A fresh live MCP cross-paper run used `llama3.2:latest`, made two exact-provenance citations, and returned `partial_evidence`: it did not validate a synthesized comparison. Its trace now distinguishes evidence actually selected from evidence lacking a validated synthesis. A live Streamlit corpus run ingested the 15-page Adam PDF and returned an extractive answer with an expandable original-evidence section. That answer disclosed that extractive content has not had semantic support independently assessed.

## Implemented and verified

- **Ingestion and persistence:** Streamlit registered and processed the local Adam PDF (15/15 pages) in an isolated runtime corpus.
- **Shared retrieval and QA:** `research_swarm/corpus/qa.py` uses the common corpus retrieval stack and produces traceable spans for Streamlit and MCP.
- **Scientific safeguards:** false-premise, numeric, polarity, and cross-paper coverage regressions are covered in `tests/test_corpus_qa.py`; beta normalization is covered in `tests/test_corpus.py`.
- **Coverage trace correction:** results now report `evidence_documents`, `missing_documents`, and `unvalidated_documents` separately. On the latest live comparison, both named papers had selected evidence; neither had a validated comparison claim.
- **Local runtime:** Llama 3.2 and All-MiniLM are installed; no model was downloaded and no paid API was enabled.
- **Automated regression:** `python -m pytest -q -p no:cacheprovider` completed with **182 passed** after the QA trace change.

## Not achieved / limitations

- No human-reviewed 50-question scientific dataset exists. The reproducible pilot has six questions across three PDFs; its annotations remain pending independent human review.
- The provisional held-out accuracy, evidence-recall, supported-claim, abstention, and cross-paper acceptance targets are not established.
- The live cross-paper workflow still returns a justified partial result rather than a scientifically useful synthesized comparison.
- Specialist-agent extraction is not part of each corpus-QA request; agent routing remains fixed in the separate analyze-paper workflow.
- Error-path traces, repeated-trial uncertainty, query-level persistence/restart acceptance, adversarial coverage, and a complete browser/MCP acceptance matrix remain incomplete.

## Reproduction

```powershell
.\.venv-swarm\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv-swarm\Scripts\python.exe -m evaluation.agentic_rag_smoke `
  --case cross_paper `
  --corpus-root .runtime\agentic-rag-cross-validation5-20261119 `
  --output evaluation\results\agentic-rag-cross-validation5-20261119.json `
  --pdf-root .runtime\evaluation-papers
```

The runner refuses to overwrite an existing corpus or output; use new paths for a rerun.

## Evidence

- Implementation: [`research_swarm/corpus/qa.py`](research_swarm/corpus/qa.py), [`research_swarm/corpus/query.py`](research_swarm/corpus/query.py), [`research_swarm/corpus/ui.py`](research_swarm/corpus/ui.py), [`research_swarm/mcp_server.py`](research_swarm/mcp_server.py)
- Tests: [`tests/test_corpus_qa.py`](tests/test_corpus_qa.py), [`tests/test_corpus.py`](tests/test_corpus.py), [`tests/test_ui.py`](tests/test_ui.py)
- Live MCP output: [`agentic-rag-cross-validation5-20261119.json`](evaluation/results/agentic-rag-cross-validation5-20261119.json)
- Existing pilot analysis: [`SCIENTIFIC_QUALITY_REPORT.md`](SCIENTIFIC_QUALITY_REPORT.md), [`SCIENTIFIC_BENCHMARK.md`](SCIENTIFIC_BENCHMARK.md)
