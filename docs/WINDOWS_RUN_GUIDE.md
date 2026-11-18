# Windows startup and demonstration

Run from the repository root in PowerShell with the existing Python environment and local Ollama. See the [installation guide](../WINDOWS_RUN_GUIDE.md) for environment setup.

```powershell
$env:LLM_PROVIDER = 'ollama'
$env:OLLAMA_MODEL = 'llama3.2:latest'
$env:LOCAL_TEST_MODE = 'false'
$env:ALLOW_PAID_API = 'false'
ollama list
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

Run the stdio server from an MCP client or a separate terminal.

```powershell
.\.venv-swarm\Scripts\python.exe -m research_swarm.mcp_server --pdf-root .\deCitit
```

Place the pinned PDFs from [sources.json](../evaluation/sources.json) under `.runtime/evaluation-papers` with filenames matching their IDs. The demo uses a separate corpus in `.runtime/rag-demo`.

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.corpus_rag_demo --evidence-only
.\.venv-swarm\Scripts\python.exe -m evaluation.corpus_rag_demo
.\.venv-swarm\Scripts\python.exe -m evaluation.corpus_retrieval
.\.venv-swarm\Scripts\python.exe -m evaluation.corpus_prompts
.\.venv-swarm\Scripts\python.exe -m pytest -q --basetemp .runtime/rag-repro-tests
```

The live tools write their output under `evaluation/results`. Use the Streamlit corpus workspace to retrieve the same kind of evidence, ask a question, or download the response JSON.
