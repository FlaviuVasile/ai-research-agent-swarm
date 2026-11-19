# Scientific RAG demonstration guide

## Prerequisites

- Windows PowerShell, repository virtual environment, local Ollama service.
- Installed `llama3.2:latest` and `all-minilm:latest` (no download required).
- A legally usable local research PDF. The smoke-test PDFs are already under `.runtime\evaluation-papers`.
- The app uses the current `.env` configuration; do not copy credentials into logs or reports.

## Streamlit corpus demonstration

```powershell
$env:LLM_PROVIDER = 'ollama'
$env:OLLAMA_MODEL = 'llama3.2:latest'
$env:LOCAL_TEST_MODE = 'false'
$env:ALLOW_PAID_API = 'false'
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

1. Open the **Research corpus — persistent evidence library** workspace and enable it.
2. Enter a publication title, select a PDF, and register it.
3. Click **Process / resume next batch** until the document status is complete.
4. Enter `What were beta1 and beta2 in Adam's default configuration?` in **Find evidence**, choose **Keyword**, and click **Retrieve evidence**.
5. Click **Answer scientific question**. Expand **Original PDF evidence** to inspect page text and source offsets.
6. Note the answer's validation disclosure: extractive excerpts have exact provenance but are not independently semantically assessed.
7. For a cross-paper example, use the Transformer and LoRA papers and ask how their methods differ. If output is `partial_evidence`, present the source excerpts as evidence and explicitly state that the comparison was not validated; do not paraphrase it as a complete answer.

The live Streamlit check used an isolated corpus and completed ingestion for the 15-page Adam paper. It did not persist a dedicated browser artifact. The latest repeatable cross-paper run is in [`evaluation/results/agentic-rag-cross-validation5-20261119.json`](evaluation/results/agentic-rag-cross-validation5-20261119.json).

## MCP SDK demonstration

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.agentic_rag_smoke `
  --case cross_paper `
  --corpus-root .runtime\<new-demo-corpus> `
  --output evaluation\results\<new-demo-output>.json `
  --pdf-root .runtime\evaluation-papers
```

The runner starts an MCP stdio server, discovers the registered tools, ingests the pinned papers, asks the comparison question, and verifies citation provenance. Use new paths; the runner refuses to overwrite existing artifacts. Inspect `status`, `claims`, `comparison_coverage`, `model_calls`, and the `provenance` summary. A result with exact provenance may still be semantically unsupported or partial.

## Regression and retrieval reproduction

```powershell
.\.venv-swarm\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv-swarm\Scripts\python.exe -m evaluation.retrieval_ablation `
  --corpus .runtime\<new-complete-three-paper-corpus> `
  --output evaluation\results\<new-retrieval-output>.json
```

For interpretation and current limitations see [`SCIENTIFIC_RAG_BENCHMARK.md`](SCIENTIFIC_RAG_BENCHMARK.md), [`AGENTIC_RAG_ABLATION_RESULTS.md`](AGENTIC_RAG_ABLATION_RESULTS.md), and [`FINAL_ARCHITECTURE.md`](FINAL_ARCHITECTURE.md).
