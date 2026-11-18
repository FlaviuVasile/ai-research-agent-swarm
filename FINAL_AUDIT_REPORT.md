# Final technical audit and Windows readiness

Verified on 17 November 2026 against the current source, independently of the
earlier execution report. Scope: professor requirements, integration, prompt
loading/caching, experiment integrity, PDF processing, Streamlit, MCP, saved
outputs, Windows operation and focused security fixes. No unrelated application
refactoring or dependency upgrade was performed.

## Findings fixed

| Finding | Fix and evidence |
| --- | --- |
| Editing `schema_instruction.md` could return a response generated with an old schema instruction | Include the rendered schema instruction in structured-response cache identity; regression verifies a miss after editing the wrapper |
| Windows BOM/newline differences could contaminate prompts or fail baseline snapshots | Load UTF-8 with optional BOM; normalize fingerprint paths/newlines and baseline regression hashes. Original raw baseline hashes were verified before migrating snapshots; template wording was not changed |
| Removing a core improved prompt silently fell back to baseline | Missing summary/question/literature variant instructions now fail; only shared support templates inherit baseline |
| Invalid `selection.json` shape caused an attribute error | Validate the selection map and reject invalid families with a clear error |
| Legacy summary instruction was captured at import time | Reload the legacy template at lookup time, preserving the compatibility constant |
| Standalone MCP questions/literature lacked a shared document deadline | Apply the existing document-budget/timebox to complete asynchronous service operations, retaining the worker lock until work ends |
| Completed MCP JSON could be observed partially written | Save to a temporary file then replace atomically |
| Saved-result reads lacked consistent containment/metadata checks | Resolve MCP result paths under the output root; validate Streamlit run IDs and saved-result metadata |
| `CON.pdf`/similar Windows devices could reach file opening | Reject reserved Windows names and alternate data streams before opening a path |
| FULL downstream context falsely described sampled notes as all-chunk evidence | Selected production family now uses a sampled-digest label; historical baseline remains unchanged |
| Experiment CLI returned success after failed operations | Retain partial result rows but raise a terminal error when any operation failed; reject an existing output before inspecting the model |
| Repeated experiment records could collapse under dictionary indexing | Require exactly 27 source and repeat rows before allowing annotation reuse |
| VS Code launch entries referenced nonexistent `main.py` and old tests | Replace obsolete entries with actual Streamlit, MCP module and pytest launch configurations |

Relevant modified modules: `research_swarm/prompt_loader.py`, `llm.py`,
`agents/summary_agent.py`, `research_swarm/service.py`, `research_swarm/jobs.py`,
`config.py`, `research_swarm/corpus/config.py`, `evaluation/run.py`,
`evaluation/compare_repeat.py`, `.vscode/launch.json`. Added production digest
template: `prompts/fields/digest_evidence.md`; selection mapping updated.

## Professor requirement assessment

### External Markdown prompts

Production summary, question, relevance, safety, schema and evidence-wrapper
instructions are loaded from Markdown. Tests verify dynamic variables, unsafe
names, missing files, BOM/CRLF handling, changes between calls on the same agent,
and response-cache invalidation after a schema-wrapper edit. Fingerprints now
use normalized text and POSIX relative paths, so a Windows checkout does not
change a prompt version solely because of line endings. Summary journals include
the prompt fingerprint; ordinary cache keys include actual effective instructions.
Edits to unrelated prompt files can conservatively invalidate summary journals.

Baseline preservation is checked against normalized content hashes. No baseline
instruction wording changed during this audit. Prompt edits affect subsequent
executions; an already executing operation is not a transactional snapshot of
all editable files, so finish a run before editing its prompt set.

### Advanced prompts and experiments

Inspected all three families and the actual inference path. `evaluation.run`
constructs real `LLM` providers, explicitly disables the response cache, and
does not attach a summary journal. It rotates family order over the same three
paper abstracts and retains raw outputs, errors, token usage and elapsed time.
Generation output contracts remain unchanged.

The existing fresh 27-call results were independently inspected and their
hash-bound annotations rescored during this audit. No new 27-call comparison
was run in this audit, and no new scientific improvement is claimed. The new
real UI/MCP executions below use actual local inference after the fixes.

Previously measured reference recall remains baseline 7/18, fields 11/18,
evidence-first 9/18. These are three-abstract analyst scores, not independent
human ground truth. No strategy passed the complete future-research-question
task or strict title-only grounding. No strategy produced a correct resolving
summary page citation. Code/schema validity must not be reported as factual
validity. Scoring requires exact result hashes and source-aligned annotations;
annotation reuse requires exact matching outputs and evidence, not similar text.

Selected families remain fields for summary, evidence-first for questions, and
baseline for literature. The new sampled-digest label corrects coverage metadata
for long FULL runs; its effect on research quality has not been experimentally
measured. It does not affect the previous single-chunk abstract comparisons.

### MCP server

The server is independently executable with the official installed MCP SDK
2.3.0 and imports no Streamlit UI. Its six tools reuse existing specialists or
Orchestrator through `ResearchService`; typed Pydantic return models provide
structured content. PDF paths are relative to an operator-controlled root,
resolved for containment, byte-bounded, and parsed by PDFMaster. Reserved Windows
devices/streams are now rejected. One worker runs per service instance; no shared
Streamlit/MCP process lock is claimed.

The current real stdio SDK client initialized, discovered six tools, extracted
the Adam PDF, invoked all four stages through `analyze_paper`, validated the
returned data, and reloaded the saved response. Physical source pages/checksum
matched independent extraction; four corpus evidence records resolved to exact
stored offsets/checksums. Traversal, missing file, invalid mode and invalid run
ID requests produced tool errors. No fixture output was used for this live test.

## Current execution evidence

| Check | Actual result |
| --- | --- |
| Dependencies | `pip check` passed; application/MCP requirements satisfied without upgrades |
| Ollama | Local `llama3.2:latest` available; model identity recorded in `evaluation/results/final-audit-environment.json` |
| Full regression suite | **161 tests, 0 failures, 0 errors, 0 skips; 54.998 seconds** in JUnit report |
| Targeted Windows/cache/MCP regressions | 13 passed in 6.59 seconds |
| Real MCP analysis | **123.409 seconds**, 15-page Adam PDF, six discovered tools, four source-record checks, no workflow warnings |
| Real browser analysis | **100.537 seconds**, uploaded Adam PDF, all four stages complete, three tabs, four matching text downloads, no browser errors/warnings |
| Compilation / whitespace checks | Source compileall and `git diff --check` passed |

The first targeted run exposed a baseline snapshot mismatch after newline
normalization. All original baseline byte hashes were verified, then the snapshot
hashes were normalized to match runtime text. The later targeted/full runs pass.
No test failure is concealed as a successful initial run.

Live runs use selected prompts, `LOCAL_TEST_MODE=false`, disabled response caches,
fresh corpus/journal locations and one question/one literature result as isolated
verification limits. Ordinary user defaults were not overwritten. They process
the actual complete Adam PDF through the complete FAST pipeline; this is not a
claim that FAST summarizes every page exhaustively.

Artifacts:

- `evaluation/results/final-audit-tests.xml`
- `evaluation/results/final-audit-mcp.json`
- `evaluation/results/final-audit-application.json` and `.png`
- `evaluation/results/final-audit-environment.json`
- `output/1c212296d0a74c259ec03b3d0e769f7c/` — current browser-run reports/checkpoint
- `.runtime/final-audit-metrics.json` — independent rescoring of earlier raw results

## Commands executed for final checks

Working directory is the project root. These commands were actually executed:

```powershell
.\.venv-swarm\Scripts\python.exe -m pip check
ollama list
.\.venv-swarm\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.runtime/pytest-final-audit --junitxml=evaluation/results/final-audit-tests.xml
.\.venv-swarm\Scripts\python.exe -m evaluation.mcp_smoke --output evaluation/results/final-audit-mcp.json
.\.venv-swarm\Scripts\python.exe -m evaluation.verify_application --output evaluation/results/final-audit-application.json
.\.venv-swarm\Scripts\python.exe -m evaluation.score evaluation/results/verification-2026-11-17.json evaluation/results/verification-comparison-2026-11-17-reviews.json --output .runtime/final-audit-metrics.json
.\.venv-swarm\Scripts\python.exe -m evaluation.probe_environment --output evaluation/results/final-audit-environment.json
.\.venv-swarm\Scripts\python.exe -m compileall -q agents research_swarm evaluation app.py config.py llm.py models.py orchestrator.py providers.py
git diff --check
```

The browser helper launches/stops a real loopback Streamlit subprocess. Its JSON
records the exact port/command and downloaded-content hashes. The MCP helper
launches its own stdio server with a fresh output root; its client context owns
that server's lifecycle. Unit/negative tests use mocks where appropriate, but
those are not used as evidence of live inference or improved scientific quality.

## Windows run guide and remaining limits

Follow [WINDOWS_RUN_GUIDE.md](WINDOWS_RUN_GUIDE.md) for installation, environment
settings, Streamlit, independent MCP/client startup, experiments, prompt editing,
tests, VS Code and troubleshooting. [MCP_GUIDE.md](MCP_GUIDE.md) retains the
complete client example. Use the project's interpreter and working directory;
stdio waiting for client input is normal, not an HTTP server failure.

Remaining limits are explicit: no OCR or faithful table/formula guarantee;
partial domain-biased FAST selection and lossy FULL synthesis; weak research-gap
questions, generated citations and title-only relevance; no hard native PDF
memory/time sandbox; no cross-process GPU coordination, public authentication,
new durable scheduler or automatic in-flight request restart. A client cancelling
cannot immediately kill an already running worker thread. Summary fields remain
Markdown inside typed responses. Broad dependency ranges are not a complete
cross-version compatibility certification; the installed environment was tested.

These operational fixes do not establish trustworthy scientific conclusions.
Users must resolve source evidence and review generated research claims.
