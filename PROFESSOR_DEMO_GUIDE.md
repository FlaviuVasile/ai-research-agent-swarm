# Professor demonstration guide

Use PowerShell from the repository root, with the installed project environment and local Ollama service. The three pinned arXiv PDFs must be present under `.runtime/evaluation-papers`. Their file names and checksums are listed in [evaluation/sources.json](evaluation/sources.json).

```powershell
ollama list
$env:LLM_PROVIDER = 'ollama'
$env:OLLAMA_MODEL = 'llama3.2:latest'
$env:LOCAL_TEST_MODE = 'false'
$env:ALLOW_PAID_API = 'false'
$env:LLM_CACHE_ENABLED = 'false'
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

1. Open the corpus workspace and enable it. Upload one paper, enter its title, register it, and process the next batch until indexing is complete.
2. Retrieve evidence for `adaptive estimates of lower-order moments`. Show the displayed PDF page, passage and checksum.
3. Try **Answer scientific question** and show the response or failure. Preserve any abstention as an observed result.
4. In the original single-paper workflow, upload Adam and run **Start Analysis**. Open the Summary, Research questions and Literature tabs. Literature discovery depends on OpenAlex availability.

Use the official SDK acceptance client to demonstrate persistent indexing, restart recovery, tool discovery, scoped search and page verification. It also runs the live question suite and preserves failures. The injected PDF is a fictitious test fixture in an isolated corpus.

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.acceptance_sdk
```

For a shorter evidence-only demonstration using the three scientific papers, run the following command. It saves a fresh output under the existing filename in `evaluation/results`.

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.corpus_rag_demo --evidence-only
```

For a separate MCP client, configure the Windows Python executable as the stdio command and use these server arguments.

```powershell
.\.venv-swarm\Scripts\python.exe -m research_swarm.mcp_server --pdf-root .\.runtime\evaluation-papers --corpus-root .\.runtime\professor-demo
```

The verified demonstration scope and limitations are recorded in the [acceptance report](FINAL_ACCEPTANCE_REPORT.md).
