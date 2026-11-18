# Windows run guide

Run these commands in PowerShell. Close other live analysis runs before using
the local GPU. The verified environment is Python 3.11.9, Ollama
`llama3.2:latest`, and the official MCP SDK 2.3.0.

## 1. Open the project and verify Python

```powershell
Set-Location -LiteralPath 'C:\Users\flavi\OneDrive\Documente\neuro'
py -3.11 --version
```

If you are using a different checkout, substitute its path. If Python is not
found, install Python 3.11 and reopen PowerShell. Do not run commands from the
Downloads folder or select an unrelated Python interpreter in VS Code.

## 2. Install dependencies without requiring script activation

```powershell
if (-not (Test-Path '.venv-swarm\Scripts\python.exe')) { py -3.11 -m venv .venv-swarm }
.\.venv-swarm\Scripts\python.exe -m pip install -r requirements.txt
# Required only for MCP:
.\.venv-swarm\Scripts\python.exe -m pip install -r requirements-mcp.txt
.\.venv-swarm\Scripts\python.exe -m pip check
if (-not (Test-Path '.env')) { Copy-Item .env.example .env }
notepad .env
```

Using the executable directly avoids PowerShell activation-policy problems.
`requirements-openai.txt` is optional and unnecessary for local inference.
The environment already in this workspace was verified; installation is needed
only for a fresh or incomplete environment. This project has version ranges,
not a complete locked deployment environment; run tests after a fresh install.

## 3. Configure local inference

Use these entries in `.env`, retaining other existing entries and private keys:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:latest
OLLAMA_BASE_URL=http://127.0.0.1:11434
ALLOW_PAID_API=false
LOCAL_TEST_MODE=false
PROMPT_VARIANT=selected
CHUNK_TOKENS=2000
OLLAMA_CONTEXT_TOKENS=8192
SUMMARY_CONTEXT_TOKENS=8192
SUMMARY_OUTPUT_TOKENS=256
LLM_MAX_OUTPUT_TOKENS=1200
LLM_TIMEOUT_SECONDS=120
DOCUMENT_TIMEOUT_SECONDS=600
```

Start the Ollama application from the Start menu. Then:

```powershell
ollama list
# Only if the generation model is missing:
ollama pull llama3.2:latest
ollama ps
```

If no server is running, `ollama serve` starts one in that terminal. An address
already in use normally means the tray server already owns the port: do not
launch another copy. A model listed by `ollama list` is installed; `ollama ps`
lists models currently loaded in memory and can be empty before inference.

Leave `OLLAMA_GPU_LAYERS` empty for automatic placement on other computers.
This machine's private configuration may force placement suitable for its GPU;
do not copy that override blindly to another GPU/model. No model is downloaded
automatically by the application.

Environment variables in the shell override `.env`. Inspect non-secret options:

```powershell
Get-Item Env:LLM_PROVIDER,Env:LOCAL_TEST_MODE,Env:PROMPT_VARIANT,Env:CHUNK_TOKENS,Env:OLLAMA_CONTEXT_TOKENS -ErrorAction SilentlyContinue
```

To remove a stale override, use `Remove-Item Env:NAME` for that named option,
then restart the MCP server. Streamlit reads settings when starting an analysis;
restart it after application code updates. Never paste private keys into logs.

## 4. Run Streamlit

```powershell
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

Open the printed localhost URL. Upload a readable research PDF, select FAST or
FULL and click **Start Analysis**. Completed results appear in three tabs with
download controls. Keep the `?run=...` URL to reopen saved progress. Stop the
server with Ctrl+C.

FAST summarizes selected evidence, not the complete paper. FULL maps all
accepted chunks but synthesizes sampled bounded notes; it is still lossy. The
default 32-chunk FULL limit can reject a long paper: use FAST, a shorter paper,
or deliberately adjust `MAX_CHUNKS` within its validated limit. Increasing a
timeout does not increase the amount of source evidence selected.

PDFs with no readable text require OCR, which is not implemented. The ordinary
upload limit is 25 MB/500 pages. Images, formulas and tables are not guaranteed
to extract correctly. OpenAlex searches use the network even with local Ollama.
An outage is reported as a warning while preserving completed stages.

Reports are under `output/<run-id>/`; default corpus data is under `research/`
and `deCitit/`. Back up those two corpus directories together with the app
stopped. Stopping the server does not resume an in-flight model request on its
next start. A new analysis can reuse compatible saved summary steps.

## 5. Run MCP independently

Choose a directory containing PDFs you permit the local MCP client to read:

```powershell
.\.venv-swarm\Scripts\python.exe -m research_swarm.mcp_server --pdf-root 'C:\papers'
```

The server waits for protocol messages on stdin. It does not open a browser or
listen on an HTTP port. A client normally launches this command itself, so do
not manually start a second server for the same client. Python prompts and
ordinary text typed into stdin are not valid MCP messages.

See [MCP_GUIDE.md](MCP_GUIDE.md) for a complete SDK client and desktop-client
configuration. Use the project's absolute Python executable and set the client
working directory to this project. The six tools are `extract_paper_text`,
`summarize_paper`, `find_research_questions`, `search_literature`, `analyze_paper`,
and `get_analysis_result`.

Pass `pdf_path: "paper.pdf"`, relative to the configured PDF root, not
`C:\papers\paper.pdf`. Complete analysis returns a run ID, source pages/checksum,
summary, structured questions/literature, warnings and coverage. Use
`get_analysis_result` with that run ID to reread the saved response.

Configure client read timeout above the document limit (the example uses 700
seconds for a 600-second document budget). The worker retains its lock if a
client disconnects while work continues. One operation runs per server; do not
run multiple Streamlit/MCP processes concurrently on a small GPU. No shared
cross-process lock or multi-user authentication is provided.

## 6. Edit prompts safely

Editable production templates are under `prompts/`. `${limit}`, `${evidence}`
and `${summary}` are strict named variables. Literal dollars require `$$`.
UTF-8 with or without BOM and Windows CRLF are accepted. Keep required variables;
missing/extra variables fail rather than silently generating a broken prompt.

`PROMPT_VARIANT=selected` uses `prompts/selection.json`: fields for summary,
evidence-first questions, baseline for literature. Preserve `baseline/` for
comparisons; edit variants instead. The next agent execution reloads prompts.
Prompt edits invalidate relevant response/journal identities. Missing core
variant templates are errors; shared support templates intentionally inherit
from baseline. Invalid selection JSON produces an error.

## 7. Reproduce experiments

```powershell
.\.venv-swarm\Scripts\python.exe evaluation/prepare.py
$trial = Get-Date -Format 'yyyyMMdd-HHmmss'
.\.venv-swarm\Scripts\python.exe -m evaluation.run --output "evaluation/results/trial-$trial.json"
```

Preparation downloads three fixed public PDF versions if absent. The experiment
performs 27 real calls with the same abstract evidence/model settings across
baseline, fields and evidence-first variants. It disables the application's
response cache and summary journal. Expect several minutes; hardware load can
make it substantially longer. Do not run another analysis simultaneously.
Existing experiment files are never overwritten. A failed operation is saved
and causes a nonzero exit after the run: inspect `valid` and `error` per row.

To reproduce the published scoring without making model calls:

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.score evaluation/results/local-2026-11-17.json evaluation/results/local-2026-11-17-reviews.json --output .runtime/recomputed-metrics.json
```

New outputs need fresh analyst review against `evaluation/rubric.json`. The
review file's `results_sha256` must match the exact result file. Do not rebind
old annotations to different text. `evaluation.compare_repeat` only allows
reuse when every output, evidence hash and model configuration matches exactly.
The existing factual scores are small-sample analyst judgments, not independent
human validation. No prompt strategy solved research-question usefulness or
strict title-only relevance; inspect citations and claims yourself.

## 8. Tests and real integration verification

```powershell
.\.venv-swarm\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.runtime/pytest-user
.\.venv-swarm\Scripts\python.exe -m compileall -q agents research_swarm evaluation app.py config.py llm.py models.py orchestrator.py providers.py
$trial = Get-Date -Format 'yyyyMMdd-HHmmss'
.\.venv-swarm\Scripts\python.exe -m evaluation.mcp_smoke --output "evaluation/results/mcp-$trial.json"
```

Use a dedicated disposable `--basetemp`: pytest may remove its contents. Unit
tests include mocks/offline fixtures; the separate MCP smoke uses a real local
model, real PDF and OpenAlex. Do not treat offline fixtures as research quality.

The optional real-browser check needs isolated Playwright dependencies and its
matching Chromium installation:

```powershell
.\.venv-swarm\Scripts\python.exe -m pip install --target .runtime/browser-deps playwright==1.65.2
.\.venv-swarm\Scripts\python.exe -m pip install --target .runtime/browser-deps playwright==1.65.2
$savedBrowserPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = (Join-Path (Get-Location) '.runtime/browser-deps')
    .\.venv-swarm\Scripts\python.exe -m playwright install chromium
} finally {
    $env:PYTHONPATH = $savedBrowserPythonPath
}
$trial = Get-Date -Format 'yyyyMMdd-HHmmss'
.\.venv-swarm\Scripts\python.exe -m evaluation.verify_application --output "evaluation/results/browser-$trial.json"
```

The browser script uses the verified Playwright 1.65.2 Chromium revision 1255.
It starts/stops its own loopback Streamlit server, uploads Adam, exercises all
stages/tabs and verifies downloaded text (CRLF/LF normalized). It intentionally
uses one question/one literature paper in its subprocess, without modifying
normal application defaults.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `No module named mcp` or missing `MCPServer` | Install `requirements-mcp.txt` into the exact executable used by the client; verified SDK is 2.3.0 |
| Ollama inspection/model error | Start Ollama; run `ollama list`; ensure model tag and loopback URL match `.env` |
| Context-budget error | Restore chunk 2000/context 8192; check shell overrides before increasing memory |
| Model timeout | Try a shorter PDF/FAST, inspect `ollama ps`, close competing inference; deliberately adjust timeout |
| `TEST MODE` output | Set `LOCAL_TEST_MODE=false`; remove any shell override; restart MCP |
| Prompt missing/selection error | Restore the named Markdown file/valid selection map; use UTF-8 and preserve template variables |
| Worker busy | Wait for the current operation; refresh/retry does not cancel a running thread |
| Port 8501 occupied | Use the existing app or choose `--server.port=8502`; avoid unnecessary duplicate inference |
| Saved response invalid | Read the retained reports; retry analysis explicitly rather than editing JSON |
| Permission/OneDrive lock | Ensure the checkout and output directories are writable and synced; close editors locking temporary files |
| VS Code starts missing `main.py` | Use the updated Streamlit/MCP/pytest launch configurations and the `.venv-swarm` interpreter |

Do not publish this local server as a public service without separate deployment
controls. Generated scientific claims still require source review.
