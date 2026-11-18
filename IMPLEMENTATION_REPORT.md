# Professor feedback implementation report

For the subsequent fresh execution verification (real Chromium upload/download,
27 new local-model calls, real MCP client and 155 passing automated tests), see
[evaluation/EXECUTION_REPORT.md](evaluation/EXECUTION_REPORT.md).

Implemented and verified on 17 November 2026. The existing Streamlit workflow,
four specialists, provider consent rules and Markdown report contracts remain.
No dependencies were installed or updated: the optional official MCP SDK 2.3.0
was already available in `.venv-swarm`. Its version is now explicitly recorded
in `requirements-mcp.txt` for reproducible installation.

## Requirement 1: external Markdown prompts

**Implemented.** Production instructions now load from `prompts/baseline/*.md`.
The original safety instruction, summary/map/synthesis instructions, question
template, relevance instruction, schema wrapper and evidence wrappers are
preserved. `summary_legacy.md` preserves the historical cache-lookup instruction.
Generated JSON schemas and real source labels remain generated from code/data.

Files:

- New `research_swarm/prompt_loader.py`: project-relative UTF-8 loading,
  restricted names, strict single-pass named substitution, variant fallback,
  selected-per-agent configuration and content fingerprinting.
- Updated `agents/summary_agent.py`, `agents/questions_agent.py`,
  `agents/literature_agent.py`, `llm.py`, `providers.py`,
  `research_swarm/summary_work.py`: agents actually consume external templates.
- Updated `config.py`, `.env.example`: `PROMPT_VARIANT` selection.
- New `tests/test_prompts.py`, `tests/baseline_prompt_hashes.json`: missing and
  extra variable rejection, unsafe-name rejection, working-directory independence,
  single-pass treatment of untrusted text, reload after edit, agent integration,
  baseline hash regression and selected-template checks.

Phase verification: 60 prompt/performance/provider tests passed after baseline
externalization. Another 24 prompt/performance checks passed after variants were
added. The response cache hashes effective instructions; summary journal identity
now includes prompt contents and selection, preventing stale reuse after edits.
Legacy summary import is limited to explicit baseline mode.

Existing output files and specialist return contracts remain. `Extraction.pages`
and `AnalysisResult.structured` are additive fields with defaults. A shared output
directory now clears stale chunk notes/selection files before a new analysis.

## Requirement 2: improved variants and actual experiments

**Implemented and run.** `prompts/fields/` introduces field-by-field extraction
and explicit missing/ambiguous handling. `prompts/evidence/` adds source-first
extraction, citation instructions and a final evidence consistency check without
requesting private reasoning. Baseline instructions remain available unchanged.

Experiment files:

- `evaluation/prepare.py`: fixed-version public PDF acquisition and deterministic
  abstract extraction/normalization.
- `evaluation/sources.json`: source URLs, PDF checksums, page/evidence and exact
  normalization policy.
- `evaluation/run.py`: actual uncached local model calls through existing
  SummaryAgent/QuestionsAgent and the relevance prompt/provider path.
- `evaluation/rubric.json`, `evaluation/review_rows.json`: reference facts and
  inspectable analyst annotations.
- `evaluation/score.py`: hash-bound review validation and metric aggregation.
- `evaluation/results/local-2026-11-17*.json`: raw 27 responses, model identity,
  generation configuration, latency/token usage, reviews and aggregate metrics.
- `evaluation/REPORT.md`: complete methodology, measured comparisons, selection
  and limitations.
- `tests/test_evaluation.py`: result/review integrity and reproducible scoring.

Three real scientific papers were compared: Attention Is All You Need v7,
Adam v9 and LoRA v2. All three strategies received identical abstract evidence
and model/generation settings. Each paper had summary, question and title-only
relevance operations: 27 responses total. Cache and summary journals were disabled.
Question evaluation used a fixed summary input to avoid upstream-output confounds.

Measured summary checklist recall was baseline **7/18**, fields **11/18**,
evidence **9/18**. Analyst review found one unsupported baseline summary clause
and none in the two variant summary sets. This is a small-sample finding, not
proof of general scientific extraction accuracy. There were no correct resolving
summary page citations. No question set passed the complete future-research task,
and no relevance set passed strict title-only grounding.

`prompts/selection.json` selects fields for summary, evidence-first for questions
(2/3 category labels correct versus 0/3 baseline), and baseline for literature
(neither longer alternative improved grounding). Selection is transparent and
reversible with `PROMPT_VARIANT`. Do not claim that all agents became reliable.

## Requirement 3: functional official-SDK MCP server

**Implemented and verified through real stdio clients.**

Files:

- `research_swarm/service.py`: shared bounded access to existing agents and
  Orchestrator, operator-controlled PDF root, size/path validation, saved results.
- `research_swarm/mcp_server.py`: official SDK `MCPServer`, stdio entry point,
  typed tool signatures, safe tool failures and no Streamlit dependency.
- `models.py`: validated source, summary, questions, literature, scientific data
  and full-analysis response models.
- `agents/pdf_master.py`: physical page text metadata, obtained directly during
  extraction rather than trusting page-like strings inside a document.
- `agents/literature_agent.py`: retains validated title-assessment records alongside
  the existing Markdown output.
- `orchestrator.py`: returns additive structured stage results without parsing
  generated Markdown back into data.
- `requirements-mcp.txt`, `MCP_GUIDE.md`: optional pinned installation, command,
  schemas, security boundaries, timeouts, client configuration and Python example.
- `tests/test_mcp.py`: real SDK client/server subprocess integration, all six tools,
  offline Orchestrator execution, saved-result equality, invalid requests, corrupt
  PDFs, traversal rejection, worker contention and physical-page provenance.
- `evaluation/mcp_smoke.py`: reproducible real-model/full-pipeline client test.

Tools exposed:

1. `extract_paper_text`
2. `summarize_paper`
3. `find_research_questions`
4. `search_literature`
5. `analyze_paper`
6. `get_analysis_result`

The complete result includes source SHA-256 and physical pages; generated summary;
validated questions; structured OpenAlex metadata and relevance; coverage,
warnings, provider/model, selected prompt family, fingerprint and synthetic flag.
Summary scientific fields remain Markdown. No unimplemented field-extraction
agent or claim-validation capability is advertised.

### Live evidence

`evaluation/results/mcp-live-2026-11-17.json` records the initial live baseline
integration. `evaluation/results/mcp-selected-live-2026-11-17.json` records the
final production selection through a real SDK stdio client:

- Real 15-page Adam PDF, matching checksum
  `eab9c73ae2ceda884b94830bda99312254bac4806f6c9f045cbab90721ecda31`.
- Real local `llama3.2:latest` inference; `synthetic: false`.
- Existing FAST Orchestrator completed all four stages.
- One question and one real OpenAlex metadata/relevance record returned.
- No workflow warnings; saved result matched the original structured result.
- Invalid path rejected.
- Elapsed time **86.575 seconds**; not a throughput guarantee.

This verifies actual tool execution and data delivery, not factual correctness
of every generated claim. The complete raw result is preserved for inspection.

## Automated validation

The final full suite passed: **154 tests in 38.12 seconds**. Earlier checks:
71 workflow/provider/prompt tests passed after structured-result integration;
the real stdio integration tests passed; the evaluation integrity tests passed.

Reproduce the complete suite:

```powershell
.\.venv-swarm\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.runtime/pytest-professor-verification
```

After a final legacy safety-prompt reload fix, 28 targeted prompt/performance/
evaluation tests passed. Source compilation and
`git diff --check` passed. No live paid OpenAI request was made. Local inference
and normal OpenAlex discovery were used for the documented live integration.

## Remaining limitations

- Three familiar ML abstracts, one pass, analyst review: no independent human
  validation, held-out assessment or confidence intervals.
- Prompted evidence checks are not enforced factual validation. Question novelty,
  classification, citation completeness and title-only grounding remain weak.
- The full-paper smoke exposed FAST selection's domain bias toward generic
  optimization/CNN passages rather than an exhaustive Adam-method account.
- FULL final synthesis still samples bounded notes; FAST is explicitly partial.
  The historical baseline evidence-digest wording remains preserved in its file.
- The default prompt selection does not add fully typed objective/method/finding
  extraction; those fields are readable Markdown. Existing typed questions and
  literature records are returned directly to MCP consumers.
- No OCR, hard native-memory isolation, multi-user authentication or remote HTTP
  transport. Source pages may make responses large.
- One operation per MCP server; no shared Streamlit/MCP process lock. A cancelled
  client request can leave its bounded worker running until completion/timeout.
- No new durable job scheduler or automatic in-flight restart. Summary/page
  checkpoints retain existing behavior; saved completed JSON is reloadable.

All three requested software capabilities are implemented. The research-quality
limitations above remain explicitly unclaimed, and the raw experiments are
included rather than replaced with invented success metrics.
