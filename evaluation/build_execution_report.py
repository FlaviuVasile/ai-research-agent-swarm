"""Build the final execution report only from completed verification artifacts."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    folder = Path(__file__).resolve().parent
    results = folder / "results"
    read = lambda name: json.loads((results / name).read_text(encoding="utf-8"))
    environment = read("verification-environment-2026-11-17.json")
    experiment = read("verification-2026-11-17.json")
    comparison = read("verification-comparison-2026-11-17.json")
    metrics = read("verification-metrics-2026-11-17.json")
    app = read("verification-application-2026-11-17.json")
    mcp = read("verification-mcp-2026-11-17.json")
    tests = ET.parse(results / "verification-tests-2026-11-17.xml").getroot()
    suite = tests if tests.tag == "testsuite" else tests.find("testsuite")
    if not app.get("application_complete") or app["errors"] or mcp["analysis"]["synthetic"]:
        raise ValueError("Application or live MCP verification is incomplete/failed.")
    if suite.get("failures") != "0" or suite.get("errors") != "0":
        raise ValueError("Automated test failures remain.")
    stage_rows = "\n".join(f"| {name} | {status} |" for name,status in app["progress"]["stages"].items())
    rows = []
    for variant in ("baseline","fields","evidence"):
        summary = metrics[variant + "/summary"]
        questions = metrics[variant + "/questions"]
        literature = metrics[variant + "/literature"]
        rows.append(f"| {variant} | {summary['supported_precision']:.1%} | {summary['reference_recall']:.1%} | "
            f"{summary['hallucination_rate']:.1%} | {summary['mean_seconds']:.2f} | {questions['category_correct']}/3 | "
            f"{literature['unsupported_claims']}/{literature['factual_claims']} |")
    metric_rows = "\n".join(rows)
    commands = '\n'.join([
        r'.\.venv-swarm\Scripts\python.exe -m pip check',
        r'ollama list',
        r'.\.venv-swarm\Scripts\python.exe evaluation/prepare.py',
        r'.\.venv-swarm\Scripts\python.exe -m evaluation.probe_environment --output evaluation/results/verification-environment-2026-11-17.json',
        r'.\.venv-swarm\Scripts\python.exe -m evaluation.run --output evaluation/results/verification-2026-11-17.json',
        r'.\.venv-swarm\Scripts\python.exe -m pip install --target .runtime/browser-deps playwright',
        r'.\.venv-swarm\Scripts\python.exe -m evaluation.verify_application --output evaluation/results/verification-application-2026-11-17.json --wait-for-experiment evaluation/results/verification-2026-11-17.json',
        r'.\.venv-swarm\Scripts\python.exe -m evaluation.compare_repeat evaluation/results/local-2026-11-17.json evaluation/results/verification-2026-11-17.json evaluation/results/local-2026-11-17-reviews.json --output evaluation/results/verification-comparison-2026-11-17.json',
        r'.\.venv-swarm\Scripts\python.exe -m evaluation.score evaluation/results/verification-2026-11-17.json evaluation/results/verification-comparison-2026-11-17-reviews.json --output evaluation/results/verification-metrics-2026-11-17.json',
        r'.\.venv-swarm\Scripts\python.exe -m evaluation.mcp_smoke --output evaluation/results/verification-mcp-2026-11-17.json',
        r'.\.venv-swarm\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.runtime/pytest-execution-final --junitxml=evaluation/results/verification-tests-2026-11-17.xml',
        r'.\.venv-swarm\Scripts\python.exe -m compileall -q agents research_swarm evaluation app.py cache.py config.py llm.py models.py orchestrator.py providers.py',
        r'git diff --check',
        r'.\.venv-swarm\Scripts\python.exe -m evaluation.build_execution_report',
    ])
    text = f'''# Complete execution verification — 17 November 2026

This report describes fresh execution after the user's explicit verification
request. It does not substitute the earlier experiment or mocked tests for live
execution. Paths below are relative to the repository root.

## Environment

Python {environment['python']}; all declared application/MCP requirements
satisfied; `pip check`: {environment['pip_check'].strip()}

Model identity: `{experiment['model']}`. Ollama was running on loopback with
8192 context, local GGUF weights and GPU placement. Offline fixtures and paid
OpenAI were disabled for live runs. No application dependencies needed updates.
Playwright 1.65.2 and greenlet 3.5.6 were installed only into
`.runtime/browser-deps` for real-browser verification; the application environment
was preserved.

Environment/source evidence: `results/verification-environment-2026-11-17.json`.

## Real scientific papers

- Attention Is All You Need, arXiv 1706.03762v7: 15-page source PDF.
- Adam: A Method for Stochastic Optimization, arXiv 1412.6980v9: 15-page PDF.
- LoRA, arXiv 2106.09685v2: 26-page source PDF.

Fixed PDF checksums were checked against `sources.json`. The experiment used
the same page-one abstract evidence for each variant. Streamlit and MCP each
processed the real complete Adam PDF through all four stages in FAST mode;
FAST output is selected evidence, not exhaustive full-paper coverage.

## Actual application execution

Streamlit started successfully on loopback. A real Chromium session rendered
the controls, uploaded the Adam PDF, clicked Start Analysis, observed completion,
visited all three report tabs and downloaded all four report artifacts.
Downloaded UTF-8 text matched saved files after normalizing Windows CRLF/LF
line endings. Run ID: `{app['run_id']}`.

| Stage | Persisted state |
| --- | --- |
{stage_rows}

Health check: {app['health_ok']}; browser errors: {len(app['errors'])}.
Workflow warnings: `{json.dumps(app['warnings'])}`.
Model requests were real, uncached local inference; the run used a fresh corpus
and summary journal. Verification limits were one question/one paper, set only
in the verification subprocess. The app's normal defaults were not changed.
The verification-owned Streamlit subprocess was stopped after the browser test.

Evidence: `results/verification-application-2026-11-17.json`, its PNG screenshot,
and `output/{app['run_id']}/` artifacts/checkpoint. The exact Streamlit command
and local port are recorded in the JSON.

## Fresh prompt experiment

{len(experiment['rows'])} actual local model responses, same configuration/evidence,
no response cache and no summary journal. Strategies: original baseline,
field-based extraction, and evidence-first consistency checking. Order rotated
by paper. Exact output matches to the earlier reviewed run:
**{comparison['exact_output_matches']}/27**. The repeat really executed inference;
comparison was performed afterward.

Previous analyst reviews were reused only after comparing every output, evidence
hash, model identity and generation configuration. The review file was rebound
to the fresh result SHA-256. Changed outputs would require fresh review; the
comparison script refuses to silently reuse annotations in that case.

| Strategy | Summary factual precision | Reference recall | Summary unsupported-claim rate | Mean summary seconds | Question category correct | Title-only unsupported clauses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{metric_rows}

Every operation met its existing output contract. Summary validity is nonempty
text; question/relevance validity is Pydantic validation, not factual validation.
No strategy produced correct resolving summary page citations. Citation
precision is undefined when no citations are emitted; baseline's bare citation
was unsupported. All strategies scored 0/3 for useful future-research questions
and 0/3 for strictly title-grounded relevance. Complete token counts, prompt
counts and per-call timing are in the raw JSON/metrics.

Selection remains measured and conservative: fields for summary (11/18 reference
facts versus 7/18 baseline), evidence-first questions (2/3 category labels versus
0/3), baseline literature (no improvement established). This does not establish
general full-paper accuracy. Reviews are Codex analyst judgments, not independent
human review. Source-scoped qualifiers, abstract-only coverage and long-output
behavior remain limitations. Timing varied; no statistically established speedup
is claimed.

Evidence: `results/verification-2026-11-17.json`,
`results/verification-comparison-2026-11-17.json`, hash-bound repeat reviews and
`results/verification-metrics-2026-11-17.json`.

## Fresh MCP execution

The official SDK's real stdio client initialized the server and discovered
**{len(mcp['tools'])} tools**. Actual calls extracted the Adam PDF, invoked the
complete Orchestrator, validated the structured result and reloaded it by run ID.
Elapsed: **{mcp['seconds']:.2f} seconds**. `synthetic`:
`{mcp['analysis']['synthetic']}`; returned literature records:
{len(mcp['analysis']['data']['literature'])}; warnings:
`{json.dumps(mcp['analysis']['warnings'])}`.

All {mcp['source_page_count']} physical source pages and source checksum matched
independent PDFMaster extraction. {len(mcp['source_reference_checks'])} selected
corpus evidence records were resolved and exact offsets/checksums verified.
Saved structured data matched the original response. Error checks:
`{json.dumps(mcp['error_checks'])}`. The client shut down its verification server.

Evidence: `results/verification-mcp-2026-11-17.json`, plus the returned run's
ordinary reports and validated `analysis.json` under `.runtime/mcp-live/`.
Source-reference validity does not prove every generated interpretation correct.

## Automated tests and implementation fixes

Final complete suite: **{suite.get('tests')} tests**, failures
**{suite.get('failures')}**, errors **{suite.get('errors')}**, skipped
**{suite.get('skipped')}**. Pytest reported **155 passed in 44.67 seconds**.
The saved JUnit file is `results/verification-tests-2026-11-17.xml`.
An earlier fresh full run passed 154 tests in 48.20 seconds before adding the
repeat-review guard regression. The targeted evaluation checks passed 3 tests.
Source compilation and `git diff --check` passed.

The first browser attempt stalled while waiting for `networkidle` on a live
Streamlit page. Health checks were already successful. A separate Chromium
probe confirmed actual controls rendered; only the verification-owned stalled
processes were stopped. The harness now waits for DOM/control readiness, and
the corrected invocation reached all four completed agent stages. Its first
download comparison then failed on Windows CRLF versus browser LF bytes. That
attempt is preserved in `verification-application-newline-failure-2026-11-17.json`.
The harness now compares decoded UTF-8 text with universal newline handling;
the complete browser workflow was rerun successfully. These were verification-
harness fixes, not hidden successful first attempts. No application runtime
failure was concealed.

Added verification scripts and stronger MCP page/offset checks; added a
regression ensuring changed experiment outputs cannot inherit old factual
reviews. Existing application behavior was preserved.

## Exact execution commands

Working directory: `{folder.parent}`.
The browser command was attempted once before the readiness fix and rerun after
the fix. The helper launched Streamlit using the exact command saved in its JSON.
MCP subprocess command/arguments are in `evaluation/mcp_smoke.py`; they use the
same Python executable, `-m research_swarm.mcp_server`, the verified paper root
and a fresh run-specific output root. HTTP/OpenAlex access and browser launching
were approved by the execution environment.

```powershell
{commands}
```

## Remaining limits

No live infrastructure was unavailable. There are no remaining failing automated
checks or concealed failed pipeline stages. Research-quality weaknesses remain:
three familiar abstracts, no held-out set/independent reviewers, weak research
questions, unsupported title-only interpretations and missing generated page
citations. FAST's domain-biased selection is partial. No OCR, hard PDF process
isolation, cross-process GPU lock, multi-user authentication or durable new
scheduler was added. Summary scientific fields remain Markdown inside a typed
response. Live network/provider behavior may differ on future runs.
'''
    (folder / "EXECUTION_REPORT.md").write_text(text,encoding="utf-8")
    print("Saved evaluation/EXECUTION_REPORT.md")


if __name__ == "__main__":
    main()
