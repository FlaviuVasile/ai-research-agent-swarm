# AI Research Agent Swarm audit and repair

> Historical report for the earlier OpenAI architecture. The subsequent local-first migration and current verification are documented in `LOCAL_LLM_REPORT.md` and the README.

Verified on 4 November 2026, using Python 3.11.9 in `.venv-swarm`.

## A. Project status

The general four-stage architecture is preserved. Reviewed all application Python files, both existing test modules, requirements, README, namespace setup, `.env.example`, and ignore rules. No `AGENTS.md` was found in the project. The private `.env` was not read or edited. This folder is not a Git repository (`git status` reports no repository), so tracked-secret status cannot be established; `.gitignore` does exclude `.env`. Nothing was committed or pushed.

Already implemented and verified with mocks: PyMuPDF extraction and page markers; invalid, blank and encrypted PDF rejection; sequential orchestration; bounded chunk summarization and reduction; structured research questions; OpenAlex retrieval and retries; Markdown reports; atomic per-file saves; partial-result preservation; Streamlit initialization. The namespace shim intentionally prevents the local `agents/` folder from shadowing the installed Agents SDK. It does not need an import-path rewrite.

Completed repairs:

| Area | Problem and repair |
| --- | --- |
| OpenAlex parsing | Non-object JSON, non-object records, null authorships and invalid metadata could raise uncaught errors. Validate response/record types, safely handle missing authors, and discard invalid years. Invalid payloads become sanitized `OpenAlexError` failures, which the literature stage records as warnings. |
| Citation links | Prefix-only ID validation permitted malformed Markdown targets. Require canonical numeric OpenAlex work IDs and percent-encode DOI target punctuation/whitespace. |
| SDK errors | Raw SDK `ValueError` text could flow into the orchestrator's user-visible error. Wrap SDK failures in a fixed safe message, retaining the failing stage in the orchestrator. |
| Async lifecycle | The installed SDK shares an HTTP pool by default, whereas Streamlit starts a fresh event loop for each analysis. Explicitly create and close an OpenAI client within each call and supply it through `OpenAIProvider`. |
| Configuration | Reject blank model names and non-positive programmatic PDF limits. Existing chunk, question and paper limits remain in place. |
| Structured responses | Strip field whitespace and reject blank question/relevance fields. Bound the question-kind text. |
| Partial downloads | A filesystem error while reading completed artifacts could crash the error handler. Report unreadable files and retain the readable ones. |
| Setup documentation | Preserve an existing `.env` when following the Windows setup instructions. Add source-only compilation, UI verification boundaries and the automotive roadmap. |

`.env.example` already contains the required names with empty secret values: `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENALEX_API_KEY`, `CHUNK_TOKENS`, `MAX_CHUNKS`, `MAX_QUESTIONS`, and `PAPERS_PER_QUESTION`. It was retained. OpenAlex's current documentation allows basic queries without a key and recommends a verified free key for higher usage; actual account access was not tested. See [OpenAlex authentication](https://help.openalex.org/api/authentication/).

The SDK integration retains `Agent`, typed output and `Runner.run`, consistent with [official OpenAI agent definitions](https://developers.openai.com/api/docs/guides/agents/define-agents). Installed SDK source was also inspected for HTTP-client ownership. Compatibility is verified against installed `openai-agents 0.20.0`, `openai 2.54.0`, and `streamlit 1.66.1`; every version admitted by the broad requirements ranges was not tested.

Remaining limitations: no OCR, no full-text literature validation, no automotive comparison matrix, no live credential/quota verification, no browser automation, no dollar budget or usage telemetry, and no production authentication or resource isolation. Long-document evidence is a lossy summary. Prompt instructions reduce document-injection risk but are not a security guarantee. Per-call clients trade some connection reuse for predictable cleanup. First tiktoken use may need network access to download encoding data. No dependency vulnerability scanner or clean-environment installation was run.

## B. Verification

| Check | Actual result |
| --- | --- |
| Initial `python -m pytest -v` | 8 passed, 8 setup errors caused by Windows temporary-directory permissions. Rerun with permission resolved these errors. |
| Expanded intermediate suite | 33 passed; one pytest cache-write warning. Subsequent runs disabled only the cache plugin. |
| Final `.venv-swarm\Scripts\python.exe -m pytest -v -p no:cacheprovider` | **35 passed in 17.81 seconds**, no failed or skipped tests. External API calls mocked. |
| `.venv-swarm\Scripts\python.exe -m compileall -q .` | Exit 1: pre-existing `TabError`, line 86, in `.runtime/python/cpython-3.11.14-windows-x86_64-none/tcl/tix8.4.3/pref/WmDefault.py`. This is a downloaded third-party runtime file, left unchanged. |
| Source compilation excluding installed environments/runtimes | Passed, exit 0. Exact command below. |
| `.venv-swarm\Scripts\python.exe -m pip check` | Passed: no broken requirements. |
| Headless Streamlit startup on port 8502 | Started successfully. GET `/` returned 200; GET `/_stcore/health` returned 200 with `ok`. Test server stopped afterward. |
| Real browser and live API integration | Not executed. No claim of live API success. |

Tests cover the complete workflow and persisted Markdown; invalid, blank, mixed and encrypted PDFs; missing OpenAI key; long text coverage, reduction and pre-call cost rejection; Unicode; OpenAlex failures, empty results, retries, malformed payloads, metadata and links; invalid text/structured model output; error sanitization; summary preservation after question-stage failure; settings; client cleanup across separate event loops; and Streamlit startup, mocked upload, enabled Start button, progress, tabs, downloads, rerun persistence and failure cleanup. Streamlit's native OS file picker and actual browser download contents were not exercised; the UI tests inject an uploaded byte stream and inspect download controls. Workflow tests independently check actual report contents on disk.

## C. Exact setup and run commands

On Windows, install Python 3.11 if needed, then open PowerShell:

```powershell
Set-Location 'C:\Users\flavi\OneDrive\Documente\neuro'
py -3.11 -m venv .venv-swarm
.\.venv-swarm\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `OPENAI_API_KEY` locally. Keep `OPENAI_MODEL=gpt-4.1-mini` unless selecting another supported accessible model. Optionally set `OPENALEX_API_KEY` from your verified OpenAlex account. Save the file, then:

```powershell
.\.venv-swarm\Scripts\python.exe -m pip check
.\.venv-swarm\Scripts\python.exe -m compileall -q -x '[\\/](\.venv[^\\/]*|\.runtime|\.uv-cache)[\\/]' .
.\.venv-swarm\Scripts\python.exe -m pytest -v -p no:cacheprovider
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

The existing environment already worked during this audit; recreating it is unnecessary if continuing on this machine. `-p no:cacheprovider` avoids the observed cache permission warning without disabling tests. If Windows blocks the pytest temporary directory, correct that directory's permissions or use an explicitly writable, dedicated test directory with `--basetemp`; pytest owns and clears its base directory, so never point that option at valuable data.

Open the URL printed by Streamlit (normally `http://localhost:8501`). Upload a readable scientific PDF, up to 25 MB and 500 pages, then click **Start Analysis**. Review stage progress, the three report tabs and any warnings. Download the reports using the buttons. Files are saved in `output/<unique-run-id>/`; completed stages remain available after a later failure. Press Ctrl+C in PowerShell to stop Streamlit.

## D. Manual actions

You must supply your own accessible, funded OpenAI API account/key and optionally a verified OpenAlex key; confirm network access and model availability. Perform a real PDF upload and download in your browser and verify one small live analysis. Review generated findings and citations against the original papers. Delete sensitive or unneeded output folders according to your own retention needs. Avoid sharing or committing `.env`.

## E. Next development steps

Keep the general workflow and add an automotive research profile for **Automotive-Specific Operating Systems: A Comparative Study** covering AUTOSAR Classic, AUTOSAR Adaptive, QNX, Embedded Linux, Android Automotive OS, and automotive RTOSs. First build a curated corpus and inclusion criteria, then an evidence-linked comparison matrix with platform/version, real-time scheduling, isolation, safety evidence, security, hardware support, licensing and update mechanisms. Include vendor/standards sources in addition to OpenAlex publications. Add page-level citations and human review, abstract/full-text relevance, cross-query deduplication, reproducible search histories and BibTeX/CSV exports. Then add evaluation fixtures, cost telemetry/caching, resumable stages and optional OCR. These are recommendations, not implemented features.
