# Local-first LLM migration

## Subsequent configuration repair — 4 November 2026

Investigated the reported context error. The current project `.env` loads successfully in a fresh process with chunk 2000, context 8192, default output 1200, Ollama and paid APIs disabled. No conflicting budget variables were present in the inspected tool process. The old loader's stale-value behavior was reproduced with regression tests: `load_dotenv()` promoted file settings into process variables that then overrode later file edits. The existing IDE/Streamlit process's environment was not directly inspected, so stale values there remain an inferred explanation for the reported error.

Replaced global mutation with `dotenv_values()` plus explicit process-environment precedence. Repeated reads now pick up file edits without persisting file settings in `os.environ`. Optional credentials remain private settings fields; the OpenAI key is excluded from settings repr, and the paid opt-in guards remain intact. No private `.env` values were changed. Only the named non-secret settings were displayed during investigation.

The static validation formula is unchanged: `2 * 2000 + 1200 + 1500 = 6700`, which fits 8192. Raising memory allocation was unnecessary. A stale chunk 6000 instead requires 14700. Errors now show effective budget values and identify process overrides. Added a per-request guard for complete system/schema/evidence UTF-8 bytes, plus a 256-unit chat-template allowance and the output reserve. These are conservative estimates, not an exact Llama tokenizer; schemas are counted once in the system prompt. Chunking preserves Unicode and all input content within its byte bounds.

Verification after the repair:

- **78 tests passed in 38.05 seconds**, including fresh/repeated config reads, working-directory independence, stale-file correction, explicit environment precedence and diagnostics, private optional credential handling, Unicode chunks, actual request context/schema, and oversized-request rejection. Existing workflow/provider/UI tests passed.
- Source compilation passed with installed environments and downloaded runtimes excluded.
- Live, uncached Ollama analysis of a generated real PDF containing a short synthetic automotive research example completed all four pipeline stages and generated four report files in **29.99 seconds**. The model was explicitly `llama3.2`, chunk 2000, context 8192, output 1200 and paid APIs disabled. A local empty search fixture was used; this verification did not contact OpenAlex or any paid provider.
- Intercepted actual local HTTP requests confirmed **`num_ctx=8192` and `num_predict=1200`**. Ollama reported prompt counts **219 / 665** and generated counts **180 / 96** for summary/questions respectively. Cache was disabled, so both calls performed actual inference.
- `ollama ps` confirmed **8192 context**, about **3.4 GB loaded**, and partial CPU/GPU execution. Context and memory settings were not increased.
- Live artifacts are under `output/context-verification-2236faf2/`, including the generated input PDF. The audit-only script is under ignored `.runtime/verify_context_fix.py`. No user research PDF was supplied or benchmarked; native browser interactions were not retested.

Restart an old Streamlit process once to discard values previously injected by `load_dotenv()`. If shell budget overrides are intentional, adjust them there; otherwise clear them using the README's narrowly scoped PowerShell commands. The existing `.env` model `llama3.2:latest` is equivalent to the requested `llama3.2` alias, which was tested live. No paid configuration was enabled, no secrets displayed, and no changes committed.

The following sections retain the original migration verification history.

Verified on 4 November 2026. This report supersedes the OpenAI-specific setup and architecture notes in the historical `AUDIT_REPORT.md`.

## Result

The existing Streamlit interface, orchestrator, four specialists, OpenAlex integration, saved Markdown and partial-result handling are preserved. The default LLM is now local Ollama. No OpenAI key or OpenAI Python package is required for local analysis.

Implemented:

- A provider protocol and factory in `providers.py`: local Ollama, explicitly authorized OpenAI, and deterministic offline test fixtures.
- The unchanged agent-facing `LLM.run(...)` contract, with centralized output validation and caching.
- Configurable local model, loopback endpoint, context, output limit and timeout. Ollama requests use native chat and structured JSON schemas; Pydantic validates structured responses.
- OpenAI disabled by default. Both `LLM_PROVIDER=openai` and `ALLOW_PAID_API=true`, plus a key, are required. Authorization occurs before cache access, imports and generation. Installing packages, retaining an old key or specifying a model name alone cannot enable OpenAI. There is no automatic fallback.
- Loopback-only Ollama access, no HTTP proxies or redirects for Ollama, and checks for installed local GGUF weights. Cloud names and remote-model metadata are rejected. No automatic model downloads. Operators should also disable cloud features in the Ollama server, as documented in the README.
- A persistent SQLite cache of validated outputs, keyed by provider/endpoint/model identity, local weight digest, complete prompt, evidence, schema and generation settings. Cache entries expire after 30 days by default; corrupt entries are misses, and filesystem/cache errors do not discard successful analysis. API keys and raw input prompts are not stored as cache columns, but generated cached text can contain sensitive document information.
- `LOCAL_TEST_MODE=true`: all four stages run offline with clearly marked synthetic reports. It overrides even injected LLM/search clients and never calls Ollama, OpenAI or OpenAlex.
- OpenAI dependencies moved to `requirements-openai.txt` and lazily imported. Core execution no longer needs tiktoken or its encoding download. Chunking now uses a conservative UTF-8 byte budget under the legacy `CHUNK_TOKENS` name.
- Shorter summary prompts and an eight-round reduction ceiling to limit repeated processing.
- Updated Windows installation, hardware checks, provider settings, cache controls, testing instructions, migration notes and remaining research roadmap in the README. `.env.example` contains only empty secret values. `.env` and default cache storage are ignored; the private `.env` was not read, modified or overwritten.

## Hardware checked before implementation

Read-only CIM checks initially needed permission; the permitted queries established:

| Resource | Observed |
| --- | --- |
| CPU | AMD Ryzen 7 5800H, 8 cores / 16 logical processors |
| Physical RAM | 16,541,622,272 bytes, about 15.4 GiB |
| Discrete GPU | NVIDIA GeForce RTX 3050 Ti Laptop GPU, about 4 GB VRAM |
| Integrated GPU | AMD Radeon Graphics |
| C: free disk | About 339 GiB |
| Ollama | Installed and running, version 0.40.13 |
| Installed model | `llama3.2:latest`, 3.2B Q4_K_M, about 2 GB weights |

This is sufficient for the tested small-model workload. After inference, `ollama ps` reported about 3.4 GB loaded, an 8,192-token context and 33% CPU / 67% GPU placement. It does not establish performance for larger models or long research PDFs. Task Manager → Performance, `ollama list`, `ollama ps`, and the README's read-only PowerShell queries can check another machine.

## Verification

| Check | Actual result |
| --- | --- |
| Complete final suite | **68 passed in 31.55 seconds**, no failed or skipped tests |
| Command | `.\.venv-swarm\Scripts\python.exe -m pytest -v -p no:cacheprovider --basetemp=.runtime/pytest-local-release` |
| Source compilation | Passed with installed environments/runtimes excluded, exact command in README |
| Dependency consistency | `pip check`: no broken requirements |
| Optional-dependency isolation | A subprocess blocked imports of `agents`, `openai` and `tiktoken`; the complete offline workflow still generated all four files |
| Streamlit | AppTest verifies initialization, upload enablement, progress, downloads, reruns, errors, and the real orchestrator in offline mode |
| Live local inference and cache | Synthetic automotive PDF, no OpenAI key, empty injected literature search: first initial-model run 35.91 seconds / 2 local calls; after final summary prompt changes, 13.55 seconds / 2 local calls. Latest cached rerun: **0.73 seconds / 0 local calls**, four identical report artifacts |
| Live local inference plus real OpenAlex | Synthetic automotive PDF; one question, one paper; installed Ollama and anonymous OpenAlex, no OpenAI/OpenAlex API keys: all four stages completed, four files, **zero warnings**, an actual OpenAlex citation present, 8.16 seconds. This run reused cached summary/question responses from its preceding attempt and generated local title relevance for the returned paper. |
| Network restriction | Initial live OpenAlex attempt could not connect inside the sandbox; all completed local outputs were retained and the literature report recorded a warning. A permitted rerun succeeded. |
| Paid integration | OpenAI calls were mocked only; no live paid API request was made |

New tests cover local defaults despite an old OpenAI key, both paid opt-ins, cache consent checks, the full mocked Ollama workflow without a key, persistent cached reruns, model/prompt/schema/settings changes, expiry, corruption, unavailable cache storage, offline-mode isolation, cloud/remote model blocking, missing models, invalid structured output, timeouts and truncated responses. Existing PDF, workflow, OpenAlex and SDK tests remain. SDK-specific tests skip if optional dependencies are absent; the full installed-environment suite had all dependencies and no skips.

The audit smoke scripts and synthetic reports were written under ignored `.runtime/` and `output/local-*` paths. They are verification artifacts, not research findings. A native browser file picker/download interaction and a clean-environment package installation were not performed. The pre-existing third-party Tcl/Tix `WmDefault.py` indentation error remains outside application source, as recorded in the earlier audit.

## Run on this Windows computer

Ollama and the default model are already installed. In this project's PowerShell terminal:

```powershell
.\.venv-swarm\Scripts\python.exe -m pip install -r requirements.txt
notepad .env
```

Add or update these non-secret settings while preserving any private keys:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:latest
ALLOW_PAID_API=false
LOCAL_TEST_MODE=false
CHUNK_TOKENS=2000
OLLAMA_CONTEXT_TOKENS=8192
```

The old `CHUNK_TOKENS=6000` configuration needs this change to fit the local 8K context. Startup analysis reports an actionable error rather than silently truncating oversized inputs. Existing shell environment values take precedence over `.env`; stop and restart Streamlit after configuration changes.

```powershell
ollama list
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

Upload a readable PDF and click **Start Analysis**. Output remains in `output/<run-id>/`; default cache storage is `.cache/llm/responses.sqlite3`. For offline plumbing tests set `LOCAL_TEST_MODE=true`. For another Windows machine or deliberate OpenAI opt-in, follow the full README.

## Remaining limitations

- Small local models can hallucinate, omit details, misjudge relevance or produce invalid JSON. Schema validation checks structure, not academic truth. There is no measured research-quality evaluation yet.
- Only the installed `llama3.2:latest` model was tested live. Other model tags, context sizes, Windows GPU drivers and larger PDFs need separate validation. Timeout and invalid-output errors are explicit; no cloud fallback occurs.
- Byte-budget chunking is deliberately conservative, not model-specific tokenization. The default 32 chunks admit roughly 64 KB of UTF-8 source text; long PDFs can require a higher `MAX_CHUNKS`. Hierarchical evidence remains lossy and reduction may stop if compression fails.
- Context and schema overhead vary by model; tune chunk, context and output limits together. Longer contexts consume more memory. Local execution consumes time and electricity.
- Normal OpenAlex search still requires internet and has service/account rate limits. The app does not enable paid OpenAlex billing; account owners remain responsible for any independently configured subscriptions or billing. Offline mode uses no literature service and generates no real citations.
- Cache outputs are local plaintext, need retention/access controls, and can become stale. Ollama must be reachable to inspect its model identity even when outputs are cached. Concurrent identical misses may repeat inference. Custom cache paths need their own Git ignore rules.
- OCR, full-text literature review, a systematic automotive comparison matrix, resumable stages, production authentication and usage telemetry remain future work. The pipeline is an autonomous fixed research sequence, not an open-ended browsing/planning agent.
- Real browser upload/download behavior and live OpenAI access were not tested in this migration. No changes were committed or pushed.

Implementation references: [Ollama native chat API](https://docs.ollama.com/api/chat), [structured JSON schemas](https://docs.ollama.com/capabilities/structured-outputs), [Windows setup](https://docs.ollama.com/windows), and [local-only server configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).
