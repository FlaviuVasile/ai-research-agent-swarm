# AI Research Agent Swarm

For setup and reliable Windows commands, start with
[WINDOWS_RUN_GUIDE.md](WINDOWS_RUN_GUIDE.md). The latest code audit, fixes and
fresh browser/MCP verification are in [FINAL_AUDIT_REPORT.md](FINAL_AUDIT_REPORT.md).

## Professor feedback implementation

Agent instructions now live in editable `prompts/` Markdown files. The default
`PROMPT_VARIANT=selected` uses measured per-agent choices; `baseline`, `fields`,
and `evidence` remain available. The three-paper, 27-response experiment found
better summary checklist recall for field-based prompts, but did not establish
reliable research-gap discovery or title-only relevance. See
[evaluation/REPORT.md](evaluation/REPORT.md) for raw results, metrics and limits.

An optional local stdio MCP server exposes real extraction, summary, questions,
literature and complete-analysis operations with validated structured results
and physical source pages. See [MCP_GUIDE.md](MCP_GUIDE.md) for the pinned SDK,
installation and a real-client example. Existing Streamlit usage is preserved.
The requirement-to-file mapping is in
[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md).

Fresh real-browser, local-model, prompt-repeat and MCP execution evidence,
including exact commands and the latest 155-test result, is in
[evaluation/EXECUTION_REPORT.md](evaluation/EXECUTION_REPORT.md).

A Python 3.11+ university project: PDF → PDF Master → Summary Agent → Open Questions Finder → Literature Search Agent → downloadable results. **Ollama is the default local LLM provider. No OpenAI key or paid AI API is required.**

## Install and run

On Windows, install Python 3.11+ and [Ollama for Windows](https://ollama.com/download/windows). Start Ollama from the Start menu, then open PowerShell in this project directory:

```powershell
py -3.11 -m venv .venv-swarm
.\.venv-swarm\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
ollama pull llama3.2:latest
ollama list
notepad .env
```

Use these settings in `.env`; an existing private file is never overwritten by the setup command. If migrating from the earlier OpenAI setup, **change the old `CHUNK_TOKENS=6000` to `2000`** so inputs fit the default local context. Existing `OPENAI_API_KEY`/`OPENAI_MODEL` values do not enable OpenAI.

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:latest
OLLAMA_BASE_URL=http://127.0.0.1:11434
ALLOW_PAID_API=false
LOCAL_TEST_MODE=false
CHUNK_TOKENS=2000
OLLAMA_CONTEXT_TOKENS=8192
LLM_MAX_OUTPUT_TOKENS=1200
LLM_TIMEOUT_SECONDS=300
LLM_CACHE_ENABLED=true
```

Ollama serves locally on port 11434. If the tray application is not running, use `ollama serve` in another terminal. Do not start a second server when the tray application already owns that port. Model downloads require internet and disk space; inference then runs locally. No model is automatically downloaded by this application. To switch models, run `ollama pull <local-model-tag>` and set `OLLAMA_MODEL` to that installed tag. Choose a local model supporting structured JSON outputs.

The app accepts only loopback Ollama endpoints, disables HTTP proxies/redirects for Ollama calls, checks installed GGUF weights and rejects cloud/remote model metadata. It never falls back to OpenAI. For an additional server-level safeguard, set the Windows user environment variable `OLLAMA_NO_CLOUD=1` and restart the Ollama tray application; merely putting this variable in the project's `.env` does not reconfigure an already-running Ollama server. See [Ollama local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).

OpenAlex remains the normal online literature source. `OPENALEX_API_KEY` is optional for basic requests; a verified free key offers higher quota. The project does not subscribe to or automatically enable paid OpenAlex billing. Check your account limits when supplying a key.

```powershell
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

Open the local URL printed by Streamlit (normally http://localhost:8501), upload a text-based PDF, and click **Start Analysis**.

The analysis now runs in a bounded background worker while a live dashboard refreshes independently once a second. It shows completed-agent milestones, actual completed summary chunks, the active chunk, separate synthesis progress, elapsed/request time and real streamed Ollama response activity. It warns after 60 seconds without response data. No percentage increases merely because time passes. Input-chunk ETA appears only after enough comparable uncached observations; total workflow ETA remains unknown while later work is unplanned. See [PROGRESS_DASHBOARD.md](PROGRESS_DASHBOARD.md) for precise measurement and persistence semantics.

Keep the `?run=...` URL to reopen the current run. UI reruns do not replay the analysis. If the Python server stops, the saved progress and completed reports remain, but the in-flight request does not resume automatically: the old run is labeled interrupted. Explicitly start a new analysis to reuse completed cached operations where available. The corpus pipeline's page-based resume is unchanged. Only one single-PDF analysis worker runs per process, and local model/context settings and paid opt-in rules are unchanged.

Dashboard verification: **112 tests passed in 139.42 seconds**. A separate uncached local Ollama run completed two input chunks and four streamed model calls; real partial response activity was observed before chunk completion. This verifies local operation and progress accounting, not research quality or a guaranteed processing speed. Detailed results and interruption limits are in `PROGRESS_DASHBOARD.md`.

### Configuration reload and context errors

Settings are read from this project's `.env` on every analysis, independently of the terminal's working directory. The loader reads the file without copying its values into the process environment, so subsequent file edits are picked up. Explicit shell/process environment variables still override `.env`. Restart an already-running Streamlit process once after upgrading from the old loader: values it previously copied into that process cannot be distinguished safely from intentional overrides.

The default budget check is conservative: `2 * CHUNK_TOKENS + LLM_MAX_OUTPUT_TOKENS + 1500`. With chunk 2000, output 1200 and context 8192, the reserve is **6700**, so the intended configuration passes without a memory increase. A stale chunk value of 6000 requires 14700 and triggers the error. Errors now display the effective non-secret budget values and identify process environment overrides.

To let `.env` control these settings, stop Streamlit with Ctrl+C and inspect/clear only these PowerShell overrides, then start again:

```powershell
Get-Item Env:CHUNK_TOKENS,Env:OLLAMA_CONTEXT_TOKENS,Env:LLM_MAX_OUTPUT_TOKENS -ErrorAction SilentlyContinue
Remove-Item Env:CHUNK_TOKENS,Env:OLLAMA_CONTEXT_TOKENS,Env:LLM_MAX_OUTPUT_TOKENS -ErrorAction SilentlyContinue
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

`CHUNK_TOKENS` is a legacy name for a UTF-8 **byte** budget, not an exact Llama tokenizer count. Before each Ollama generation, the app also counts the actual system instructions, embedded schema and evidence once, adds 256 units for template overhead and reserves the configured output limit. This is a conservative estimate; Ollama's `prompt_eval_count` provides server-reported token usage after inference. Numeric usage and configured context are logged without prompt text. Every request explicitly sends `options.num_ctx=OLLAMA_CONTEXT_TOKENS`; no automatic context increase occurs. The aliases `llama3.2` and `llama3.2:latest` resolve to the same installed latest tag.

### Hardware check

This computer was inspected before implementation: Ryzen 7 5800H (8 cores/16 threads), about 16 GB RAM, RTX 3050 Ti Laptop GPU (about 4 GB VRAM), and about 339 GiB free on C:. Ollama was already running with `llama3.2:latest` (3.2B, Q4_K_M, about 2 GB weights). This is a reasonable small-model starting point; available RAM/VRAM, context length and other applications affect performance. Larger models may use CPU/RAM and be slower. `ollama ps` shows actual CPU/GPU placement. Local inference still consumes electricity and compute time.

To check another Windows computer, open Task Manager → Performance → CPU, Memory, GPU, and use these read-only commands (CIM queries may be restricted by policy):

```powershell
Get-CimInstance Win32_ComputerSystem | Format-List TotalPhysicalMemory
Get-CimInstance Win32_Processor | Format-List Name,NumberOfCores,NumberOfLogicalProcessors
Get-CimInstance Win32_VideoController | Format-List Name,AdapterRAM
Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Format-List DeviceID,FreeSpace
ollama list
ollama ps
```

GPU `AdapterRAM` can be inaccurate for large cards; Task Manager or `nvidia-smi` provides a better VRAM check. Start with a small quantized model and measure your own workload.

### Free offline testing mode

Set `LOCAL_TEST_MODE=true` in `.env`, or for one PowerShell session:

```powershell
$env:LOCAL_TEST_MODE = 'true'
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

Upload a readable PDF and click **Start Analysis**. All four stages execute using deterministic local fixtures, with no Ollama, OpenAI, OpenAlex or tokenizer download. Reports and UI warnings prominently identify synthetic test output. This verifies plumbing, not research quality. To return to real local inference, stop Streamlit, run `Remove-Item Env:LOCAL_TEST_MODE`, ensure `.env` contains `LOCAL_TEST_MODE=false`, and restart.

### Optional OpenAI provider — explicit paid opt-in

Only if you deliberately want paid OpenAI analysis:

```powershell
.\.venv-swarm\Scripts\python.exe -m pip install -r requirements-openai.txt
```

Then set **both** `LLM_PROVIDER=openai` and `ALLOW_PAID_API=true`, plus your private `OPENAI_API_KEY` and `OPENAI_MODEL=gpt-4.1-mini`. Restart Streamlit after changing configuration. Without both opt-ins, OpenAI calls fail before SDK initialization or cache lookup. Test mode takes priority and never calls paid services. Selecting a model name or installing OpenAI dependencies alone does not opt in. No OpenAI key should be committed or shared. Environment variables already set in PowerShell take precedence over `.env` values.

## Architecture

The central Python `Orchestrator` controls the existing fixed sequence. PDF Master extracts text locally; Summary Agent summarizes chunks; Open Questions Finder produces Pydantic-validated questions; Literature Search Agent retrieves OpenAlex metadata and asks the LLM for title-based relevance. All AI specialists call the same `LLM.run(...)` facade. Its provider protocol exposes authorization, cache identity and generation; provider-specific HTTP/SDK details stay in `providers.py`. Ollama uses native `/api/chat` and JSON schemas. The optional OpenAI implementation uses Agents SDK `Agent`/`Runner.run()` with tracing disabled. The fixture provider handles offline testing. OpenAI packages are lazily imported only after explicit consent.

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit upload, live status, results, downloads |
| `orchestrator.py` | Stage sequencing, persistence, progress, safe failures |
| `agents/pdf_master.py` | PyMuPDF validation and page-marked extraction |
| `agents/summary_agent.py` | Chunked academic summaries and recursive reduction |
| `agents/questions_agent.py` | Structured evidence-backed research questions |
| `agents/literature_agent.py` | Verified metadata and title-based relevance |
| `tools/openalex.py` | Async OpenAlex HTTP client, retries, metadata parsing |
| `llm.py` | Provider-neutral facade, validation, cache keys, conservative chunk splitting |
| `providers.py` | Local Ollama, guarded optional OpenAI, deterministic offline fixtures |
| `cache.py` | Persistent local SQLite response cache |
| `models.py`, `config.py` | Typed data and environment settings |
| `tests/test_workflow.py` | Real PDF extraction plus mocked external APIs |

The `research_swarm` namespace exposes these local modules without naming a local regular package `agents`, which would shadow the OpenAI Agents SDK. Do **not** add `agents/__init__.py` or import local specialists as `from agents...`; use `research_swarm.agents...`.

## Outputs and programmatic use

The Streamlit app creates `output/<unique-run-id>/` for each analysis. Each folder contains `extracted_text.txt`, `summary.md`, `open_questions.md`, and `literature_review.md`. Session-specific downloads read that run's in-memory results. Files survive application restarts; results are not automatically reloaded into the UI. Delete unneeded generated run folders yourself.

For the exact flat `output/` filenames, use the orchestrator directly:

```python
import asyncio
from pathlib import Path
from orchestrator import Orchestrator

result = asyncio.run(Orchestrator().run(Path("paper.pdf").read_bytes()))
print(result.output_dir)
```

Use a distinct `output_dir` per concurrent programmatic run. A new run in the same directory replaces this application's four named artifacts; unrelated files are preserved. Completed stages remain on disk after a later failure. The UI offers downloads of completed partial results.

## Long documents, evidence, and cost

All readable text is extracted and saved with page markers. All accepted chunks are summarized; there is no silent truncation. The legacy `CHUNK_TOKENS` setting now uses a conservative UTF-8 byte budget (2,000 by default) to avoid tokenizer dependencies/downloads. This usually overestimates token counts and creates more chunks; it is not an exact local-model tokenizer. Above 32 chunks, analysis stops before generation; increase `MAX_CHUNKS` deliberately or use a shorter PDF. Uploads remain limited to 25 MB and 500 pages. Context settings reserve space for evidence, summary, instructions, schema and output; custom tokenizers/context limits still need validation.

For short PDFs, the questions specialist receives verbatim text plus the summary. For long PDFs, it receives a bounded hierarchical evidence digest covering all chunks plus the summary. This is lossy: an omitted detail can cause a missed research question. Page references are preserved where possible, not independently validated. The model separates explicit limitations from inferred opportunities; inferred questions are not proof of a novel or globally unsolved problem.

One short-paper run normally uses one summary call, one question call, and up to 15 title-relevance calls (5 questions × 3 papers). Long papers add chunk summaries and reduction calls. Responses default to 1,200 output tokens with 300-second request deadlines. Summary reduction is bounded to eight rounds and fails clearly if compression does not converge. Calls run sequentially. Reduce `MAX_QUESTIONS` and `PAPERS_PER_QUESTION` to reduce compute time; one or two questions are sensible for initial small-model tests. Local inference has no AI API charge; explicitly opted-in OpenAI calls and SDK retries can incur charges. These controls are not a dollar budget.

### Local response cache

Validated LLM outputs are stored in `.cache/llm/responses.sqlite3` by default. Keys hash the provider, endpoint, model identity/digest, agent, complete instructions/evidence, output schema and generation settings. Across runs, identical processing reuses the output; different models, prompts and local model digests invalidate it. Cached structured responses are validated again. Ollama must be reachable to resolve the installed model identity even on a cache hit. OpenAlex searches remain live, so repeated reports can contain different literature results.

Set `LLM_CACHE_ENABLED=false` to bypass reads/writes; `LLM_CACHE_DIR` changes storage; `LLM_CACHE_TTL_SECONDS` defaults to 2,592,000 (30 days). Expired entries are ignored and removed on a subsequent cache write. To reset, stop the app and delete only the cache database with `Remove-Item -LiteralPath '.cache/llm/responses.sqlite3'`. Cached generated outputs can contain sensitive document information: they are local plaintext, excluded from Git at the default path, and need the same retention/access controls as reports. Custom cache directories need their own ignore rules. SQLite handles concurrent writes; identical concurrent cache misses can still duplicate inference. Cache failure logs a warning and permits analysis to continue.

OpenAlex receives one keyword search per question, with at most three results by default. Citation titles, authors, years, DOI links and OpenAlex links come directly from returned records, never from generated citations. Missing metadata is labeled unavailable. Relevance is generated from the returned **title only**, so it is preliminary and cannot establish a paper's methods, findings, or whether it answers the question. This is a discovery aid, not a systematic review. Verify papers before citing them. No matching results and API outages are explicitly reported; an OpenAlex outage produces a completed literature report with warnings rather than losing the summary.

## Validation

```powershell
.\.venv-swarm\Scripts\python.exe -m compileall -q -x '[\\/](\.venv[^\\/]*|\.runtime|\.uv-cache)[\\/]' .
.\.venv-swarm\Scripts\python.exe -m pytest -v -p no:cacheprovider --basetemp=.runtime/pytest-local
```

Tests create PDFs in memory and mock model calls and OpenAlex HTTP responses. No paid requests or real credentials are used. Coverage includes the full Ollama/no-key workflow, cached reruns, paid consent guards, remote/cloud model blocking, offline fixtures, cache invalidation/expiry/corruption/failure, malformed output, existing PDF/workflow behavior and Streamlit. Optional SDK-specific tests skip if OpenAI dependencies are absent. `--basetemp` points pytest at a dedicated disposable directory; do not point it at valuable files.

The compile command excludes installed environments and downloaded runtimes. The literal `python -m compileall -q .` also compiles those third-party files; the bundled Tcl/Tix `WmDefault.py` contains a pre-existing indentation error. `AUDIT_REPORT.md` records the earlier OpenAI architecture audit; see `LOCAL_LLM_REPORT.md` for this migration's current verification. HTTP clients are explicitly closed within their event loop.

Streamlit AppTest covers startup, mocked upload/analysis, progress, report tabs, download controls, rerun persistence, and failure cleanup. It does not replace a real browser upload/download test or a funded live API smoke test.

## Automotive research roadmap

The general workflow can analyze readable papers about AUTOSAR Classic, AUTOSAR Adaptive, QNX, Embedded Linux, Android Automotive OS, and automotive RTOSs. It does not yet compare these platforms systematically. For **Automotive-Specific Operating Systems: A Comparative Study**, add:

- A curated corpus with platform/version, publication date, source type, DOI, and inclusion/exclusion decisions; include vendor and standards documentation beyond OpenAlex.
- An evidence-linked comparison matrix for scheduling, real-time behavior, isolation, safety certification evidence, security, hardware support, licensing, update mechanisms, and AUTOSAR interoperability.
- Page-level quotations and human-reviewed citations for every comparison claim; distinguish measured findings from vendor claims and inferred gaps.
- Abstract/full-text relevance review, cross-query deduplication, export to BibTeX/CSV, and reproducible search histories.
- Domain evaluation papers and expected answers, then usage/compute telemetry, optional OCR, and resumable runs. LLM response caching is already implemented.

## Operational limits

Scanned/image-only PDFs are rejected with an OCR explanation. Mixed PDFs warn about pages with no extractable text; images and diagrams are not analyzed. Password-protected PDFs are rejected. Extraction preserves readable text, but complex table/column order and formulas may be imperfect. PDF text and retrieved metadata are treated as untrusted evidence in prompts. Generated Markdown is displayed with Streamlit's default HTML safety settings.

With the default provider, PDF text stays on this computer for LLM inference; normal literature queries are sent to OpenAlex. If you explicitly opt into OpenAI, document evidence is sent to OpenAI. Offline test mode sends neither. SDK tracing is disabled. Local models can hallucinate or return invalid JSON; validate all research claims and citations. Timeouts, context exhaustion, long-document cost limits and non-converging reductions are reported without discarding earlier completed stages. No automatic cloud fallback is attempted. Do not deploy publicly without authentication, retention policies, resource isolation and per-user quotas.

Official references: [Ollama Windows](https://docs.ollama.com/windows), [Ollama chat API](https://docs.ollama.com/api/chat), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents-sdk/), [OpenAlex authentication](https://help.openalex.org/api/authentication/).

## Persistent corpus foundation

The corpus workspace supports scientific QA over one indexed PDF or the full corpus. Responses include quotations with PDF page and character offsets, validation outcomes and a bounded retrieval trace. The MCP server exposes the same query and evidence search through stdio. See the [pipeline](docs/RAG_PIPELINE.md), [MCP workflow](docs/MCP_GUIDE.md), and [Windows demonstration](docs/WINDOWS_RUN_GUIDE.md).

The first scalable research increment is available alongside the original four-agent PDF analysis. See [RESEARCH_PLATFORM_PLAN.md](RESEARCH_PLATFORM_PLAN.md) for the phased plan, verification results and remaining work. This increment stores publications, processes PDFs in resumable bounded batches, and retrieves exact source evidence. Discovery providers and comparative research reports are later phases; no placeholder academic reports are generated.

Start Streamlit as usual, expand **Research corpus — persistent evidence library**, and enable the workspace. Enter a real publication title and optional DOI, import a lawfully held PDF, then click **Process / resume next batch**. Repeat until the document table shows completion. Search using **Keyword**, or install the optional local embedding model and index batches before choosing **Local semantic**. Progress is per document/page. Each click runs a bounded slice; there is no invisible background worker. For hundreds of local papers, use the CLI to register verified metadata and schedule ingestion without retaining uploaded files in Streamlit's memory.

### Windows CLI

Run from the project directory using the existing environment. Replace the PDF path and title below with your own actual publication; the command does not infer citation metadata:

```powershell
.\.venv-swarm\Scripts\python.exe -m research_swarm.corpus add 'C:\papers\paper.pdf' --title 'Actual publication title'
.\.venv-swarm\Scripts\python.exe -m research_swarm.corpus list
.\.venv-swarm\Scripts\python.exe -m research_swarm.corpus ingest
.\.venv-swarm\Scripts\python.exe -m research_swarm.corpus search 'automotive real-time scheduling' --limit 5
```

Repeat `ingest` for the next bounded slice; inspect any failed records and correct the cause before retrying. `add` also supports `--doi`, repeatable `--author`, and `--year`, all taken from the real paper or verified metadata. The DOI is normalized; complete title/year/first-author identities are conservatively deduplicated. Incomplete title-only metadata stays separate to avoid false merges. Reimporting the identical PDF under a different publication is rejected pending metadata reconciliation.

For optional local semantic retrieval:

```powershell
ollama pull all-minilm:latest
.\.venv-swarm\Scripts\python.exe -m research_swarm.corpus index
.\.venv-swarm\Scripts\python.exe -m research_swarm.corpus search 'vehicle controller task scheduling' --semantic --limit 5
```

Repeat `index` to compute the next batch. `all-minilm:latest` is a small local embedding model; it was installed and tested during this implementation. Only loopback Ollama is accepted, with the existing local-weight/cloud-model checks. Generation-provider selection does not redirect embeddings to OpenAI. Application code never downloads a model automatically. Embedding requests use `truncate=false`: oversized passages fail instead of silently losing evidence. The default embedding context is 512; difficult mathematical/multilingual passages may need a smaller `CORPUS_PASSAGE_CHARS` or another local embedding model.

Keyword search requires neither Ollama nor a network connection. The corpus `ingest` command makes **no LLM calls** and is independent of the original PDF workflow's `MAX_CHUNKS`. No new pip dependencies are needed; the Python SQLite build must include FTS5.

### Storage and traceability

- `research/corpus.sqlite3`: versioned SQLite metadata, document states, exact page text, passages, FTS5 index, vectors and retrieval-query history.
- `deCitit/<sha256>.pdf`: streamed local PDF copies, named by content hash.
- Each hit includes publication ID, document ID, physical PDF page, evidence ID, character offsets, source checksum, recorded DOI and exact passage. Use `python -m research_swarm.corpus evidence <ID>` to resolve an evidence record.
- Retrieval history records queries and returned evidence IDs. External discovery-search history, downloaded-source/license provenance and generated claim-to-evidence records belong to phases 2–3 and are not implemented yet.

Page text, passages, FTS entries and the last completed page commit together. Reopening the application resumes from that checkpoint without re-extracting committed pages. A fresh worker cannot steal an active document lease; after an abrupt kill, wait 120 seconds before resuming. Extraction profile changes require an explicit rebuild:

```powershell
.\.venv-swarm\Scripts\python.exe -m research_swarm.corpus reset DOCUMENT_ID
.\.venv-swarm\Scripts\python.exe -m research_swarm.corpus ingest
```

`reset` discards that document's derived text/passages/vectors and invalidates its old evidence IDs; its metadata/PDF remain. Never reset evidence already used in a published report without retaining/versioning that corpus. Full claim/report versioning is planned. Back up `research/` and `deCitit/` together with the app stopped. Both are excluded from Git at the default paths and can contain sensitive documents. A custom `CORPUS_ROOT` (or CLI `--root PATH`, before the subcommand) needs its own access controls, backup and ignore rules.

### Bounded work and limits

Defaults in `.env.example` include 20 pages / 5 documents per ingestion slice, a 30-second soft time limit, 50 MB / 2,000 pages per PDF, 100,000 extracted characters per page, 1,200-character passages with 120 overlap, 32 embeddings per slice, 10 retrieval hits and at most 50,000 vectors scanned per semantic query. A smaller embedding batch holds at most eight passages; vector search streams 128 vectors at a time and retains only the requested top hits. Model identity/digest keys prevent reuse across changed embedding weights. Existing vectors cache intermediate semantic processing persistently.

These are application work bounds, not a hard process memory sandbox. PyMuPDF may allocate native memory before the page text limit is checked, and a deadline does not interrupt an in-flight page extraction or HTTP call. OCR and production worker isolation are not present. Section boundaries are heuristic, and page numbers refer to PDF positions, not printed pagination. Exact vector scanning is maintainable for an initial corpus but is not an ANN service; an exceeded scan cap produces an error, and publication-filtered CLI search can narrow the corpus. Synthetic tests do not establish academic relevance or throughput for hundreds of real papers.

Run the complete suite, including the new corpus tests:

```powershell
.\.venv-swarm\Scripts\python.exe -m pytest -v -p no:cacheprovider --basetemp=.runtime/pytest-corpus
```

Latest verification: **102 tests passed in 47.82 seconds**, including all 78 previous tests. New coverage includes persistent deduplication, collection, invalid/encrypted/truncated PDFs, exact evidence offsets, page transactions, resume/lease recovery, checksum changes, long-document work limits, keyword retrieval history, vector persistence/invalidation, local-only embedding calls and the Streamlit corpus flow. A separate live local embedding smoke test passed. Discovery pagination/downloads and comparative report generation are not implemented, so tests of those future features are not claimed. Implementation references: [SQLite FTS5](https://sqlite.org/fts5.html), [Ollama embedding API](https://docs.ollama.com/api/embed), [all-minilm model](https://ollama.com/library/all-minilm).
