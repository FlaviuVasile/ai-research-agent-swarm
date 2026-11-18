# Scientific Agentic RAG acceptance

Tests were run against the current working tree on 18 November 2026. Application code was left unchanged. The prior implementation report recorded partial completion. This acceptance uses new results in [the evidence directory](evaluation/results/final-acceptance/).

| Test | Status | Execution evidence and source |
|---|---|---|
| 1. Markdown prompts | PENDING | Runtime file-open traces are collected by the acceptance SDK client. |
| 2. Advanced prompting | PENDING | Fresh paired Ollama experiment. |
| 3. Persistent RAG | PENDING | SDK ingestion and search against three pinned scientific PDFs, restart and direct PDF-offset checks. |
| 4. Scientific reliability | PENDING | Eight SDK questions and manually checkable source targets. |
| 5. Agentic behavior | PENDING | Runtime trace records supplied evidence, rejections, revision and requested follow-ups. |
| 6. External MCP client | PENDING | Official Python MCP SDK as an out-of-process stdio client. |
| 7. Streamlit | PARTIAL | Chromium completed the original Adam analysis in 92.25 s, displayed all three report tabs, and downloaded four byte-equivalent files after newline normalization. OpenAlex was unreachable after three attempts. The first corpus browser run indexed Adam, then timed out waiting for the register confirmation after attempting a second upload. [Specialists](evaluation/results/final-acceptance/streamlit-specialists.json) · [Two-upload attempt](evaluation/results/final-acceptance/streamlit-corpus-two-upload-attempt.json) · `app.py`, `research_swarm/corpus/ui.py` |
| 8. Regression | PASS | 163 total, 163 passed, 0 failed, 0 skipped, 0 errors in 54.89 s. Compilation and dependency checks exited 0. See the notes below. [Pytest](evaluation/results/final-acceptance/pytest.log) · [JUnit](evaluation/results/final-acceptance/pytest.xml) · [Environment checks](evaluation/results/final-acceptance/environment-checks.log) |
| 9. Google Agentic Engineering | PENDING | Acceptance checks context, harness, orchestration, guardrails, feedback, evaluation and observability. |

The automated regression suite includes deterministic tests, mocked HTTP/model outputs, a real MCP subprocess using offline fixtures, and Streamlit AppTest coverage. The pytest results supply zero live model-inference verifications. Live Ollama evidence is in the separate acceptance artifacts. The suite does not label all substitute-backed cases individually, so no mocked-case total was inferred.

## Alignment with Agentic Engineering

| Capability | Status | Evidence and limits |
|---|---|---|
| Context engineering | PASS | Live QA traces distinguish retrieved, supplied and omitted passage IDs. Prompt opens verify static Markdown loaders. See `research_swarm/corpus/qa.py` and `research_swarm/prompt_loader.py`. |
| Harness engineering | PASS | SDK tools ran in a subprocess, corpus state survived restart, and pytest and dependency checks completed. See `research_swarm/mcp_server.py`, `research_swarm/service.py`, and `tests/test_mcp.py`. |
| Orchestration | PARTIAL | Original workflow reached Summary, Questions and Literature stages in Chromium. Caller-selected QA ran independently. Dynamic specialist selection was not demonstrated. See `orchestrator.py` and `research_swarm/corpus/qa.py`. |
| Guardrails | PARTIAL | Probes cover path rejection, evidence checks, timeouts and one embedded instruction. The scientific quality gate did not pass. See `research_swarm/service.py`, `research_swarm/corpus/qa.py`, and `research_swarm/budgets.py`. |
| Scientific evaluations | PARTIAL | Paired live prompt outputs and source-labelled questions were reviewed. Held-out accuracy, independent reviewers and repeated-trial reliability remain untested. See [experiment results](FINAL_EXPERIMENT_RESULTS.md). |
| Feedback loops | PARTIAL | Live revision was triggered by failed provenance. A corrected factual answer and dynamic specialist routing require further proof. See `research_swarm/corpus/qa.py`. |
| Observability | PARTIAL | Successful QA calls expose evidence IDs, rejection counts, prompt version and latency. Error responses lose that per-attempt trace. Browser and prompt experiment logs provide supplemental observations. |

The alignment review uses the whitepaper's context, harness, evaluation and feedback categories. It describes verified mechanisms and their observed limits. [Google's The New SDLC With Vibe Coding](https://reu.techconf.org/document/06-Reading-materials/The-New-SDLC.pdf)

Reproduction commands and the professor walkthrough are in the [demonstration guide](PROFESSOR_DEMO_GUIDE.md).
