# Scientific Agentic RAG acceptance

Tests were run against the current working tree on 18 November 2026. Application code was left unchanged. The prior implementation report recorded partial completion. This acceptance uses new results in [the evidence directory](evaluation/results/final-acceptance/).

| Test | Status | Execution evidence and source |
|---|---|---|
| 1. Markdown prompts | PARTIAL | Runtime file-open events verify production Summary, Questions and Corpus QA templates. Live OpenAlex discovery did not reach the LiteratureAgent relevance template branch. The real title-only model pilot loaded both literature templates directly. See the exact paths below. |
| 2. Advanced prompting | PARTIAL | Six live outputs across baseline and fields, with higher extraction completeness in this sample and no accuracy or research-question usefulness improvement. Citation correctness could not be measured because no explicit pages were emitted. [Experiment results](FINAL_EXPERIMENT_RESULTS.md) |
| 3. Persistent RAG | PARTIAL | Three pinned scientific PDFs plus a synthetic canary were indexed. A fresh server recovered all IDs. All 22 retrieved spans matched the PDF text at the stated page and offsets. QA built scoped context and attempted generation. The first cross-paper question hit the inference deadline. [SDK responses](evaluation/results/final-acceptance/mcp-acceptance.json) · `research_swarm/corpus/ingest.py`, `store.py`, `retrieval.py`, `qa.py` in the corpus package |
| 4. Scientific reliability | FAIL | The first QA pass returned zero factual answers across eight cases. The injection recheck withheld the canary output but also withheld the correct answer. One Adam specialist summary misattributed an experimental CNN application to the proposed method. [Source-labelled outcomes and review](FINAL_EXPERIMENT_RESULTS.md) · `research_swarm/corpus/qa.py`, `agents/summary_agent.py` |
| 5. Agentic behavior | PARTIAL | The browser showed a fixed stage order. Live QA traces showed retrieval, supplied context, rejection and one revision. Dynamic specialist selection and live follow-up retrieval were not demonstrated. [SDK traces](evaluation/results/final-acceptance/mcp-acceptance.json) · `orchestrator.py`, `research_swarm/corpus/qa.py`, `tests/test_corpus_qa.py` |
| 6. External MCP client | PARTIAL | The official SDK discovered 11 stdio tools. Ingestion, restart, search, inspection, errors, specialist execution and saved-result reloading worked. Scientific QA returned abstentions or deadlines in the first pass. [Corpus](evaluation/results/final-acceptance/mcp-acceptance.json) · [Specialists](evaluation/results/final-acceptance/mcp-specialists.json) · `research_swarm/mcp_server.py`, `research_swarm/service.py` |
| 7. Streamlit | PARTIAL | Chromium completed original Adam analysis in 92.25 s, showed three report tabs, and downloaded four files matching saved text after newline normalization. OpenAlex was unreachable after three attempts. Corpus upload, indexing and page evidence worked for Adam. The answer button surfaced an LLM deadline with no answer export. The two-upload attempt timed out waiting for a second register confirmation. [Specialists](evaluation/results/final-acceptance/streamlit-specialists.json) · [Corpus](evaluation/results/final-acceptance/streamlit-corpus.json) · [Two-upload attempt](evaluation/results/final-acceptance/streamlit-corpus-two-upload-attempt.json) · `app.py`, `research_swarm/corpus/ui.py` |
| 8. Regression | PASS | 163 total, 163 passed, 0 failed, 0 skipped, 0 errors in 54.89 s. Compilation and dependency checks exited 0. See the notes below. [Pytest](evaluation/results/final-acceptance/pytest.log) · [JUnit](evaluation/results/final-acceptance/pytest.xml) · [Environment checks](evaluation/results/final-acceptance/environment-checks.log) |
| 9. Google Agentic Engineering | PARTIAL | Context and harness mechanisms have live evidence. Scientific quality, feedback effectiveness and full observability remain incomplete. See the capability table below. |

The automated regression suite includes deterministic tests, mocked HTTP/model outputs, a real MCP subprocess using offline fixtures, and Streamlit AppTest coverage. The pytest results supply zero live model-inference verifications. Live Ollama evidence is in the separate acceptance artifacts. The suite does not label all substitute-backed cases individually, so no mocked-case total was inferred.

## Runtime prompt paths

The test client adds a Python file-open audit hook to its real server subprocess. It records file paths, call stacks and subprocess IDs. The following paths were observed outside the fingerprint inventory scan. [JSONL runtime log](evaluation/results/final-acceptance/prompt-opens.jsonl)

| Runtime path | Files opened | Status |
|---|---|---|
| FAST SummaryAgent through MCP orchestration | `prompts/baseline/selected_evidence.md`, `prompts/fields/summary_common.md`, `prompts/baseline/summary_fast.md`. `prompts/baseline/summary_legacy.md` also opened on import. | PASS for observed FAST path |
| QuestionsAgent through MCP orchestration | `prompts/evidence/questions.md`, `prompts/baseline/questions_input.md` | PASS |
| Corpus QA | `prompts/evidence/corpus_qa.md`, `prompts/baseline/corpus_verify.md`, `prompts/baseline/corpus_revision.md`, `prompts/baseline/safety.md`, `prompts/baseline/schema_instruction.md`. Read events alone only prove loading. Returned traces also show actual revision and semantic rejection. | PASS |
| LiteratureAgent relevance | `prompts/baseline/literature.md` is selected by production configuration, and `prompts/fields/literature.md` ran in the title-only pilot. OpenAlex returned no usable live discovery results to exercise the production relevance call. | NOT TESTED for the production relevance branch |

Exact loader and call sites are in `research_swarm/prompt_loader.py`, `agents/summary_agent.py`, `agents/questions_agent.py`, `agents/literature_agent.py`, and `research_swarm/corpus/qa.py`.

## MCP and control-flow details

- **PASS** for startup, discovery, persistent ingestion, PDF scope, chunk inspection and structured responses. Error probes rejected a root escape, top-k zero and unknown chunk ID. The second SDK client also rejected missing files, invalid mode and malformed saved-run IDs.
- **PASS** for live invocation of the original specialist workflow under its larger time budget. The SDK reloaded the result exactly and independently matched all 15 page texts and four selected evidence spans. Under the shorter harness budget, the separate combined workflow failed at **Open Questions Finder** with `BudgetExceeded`.
- **PASS** for bounded correction and safe termination in the observed trace. The architecture probe supplied chunk IDs 3, 9 and 7, rejected a draft on provenance, retried with those same excerpts and terminated after another rejection. The no-hit request terminated with an empty evidence list and no factual claims. [No-hit control](evaluation/results/final-acceptance/mcp-no_hit-recheck.json)
- **NOT TESTED** for dynamic specialist selection or successful additional live retrieval. The observed specialist dispatch came from the requested tool or fixed workflow. No completed acceptance trace recorded a distinct model-requested follow-up query. The regression test with a substituted model covers that branch.
- **PARTIAL** for injection handling. The higher-budget recheck supplied canary chunk 316, rejected four claims and one revision claim on semantic checks, and returned an abstention. The injected string did not appear as an answer. Correct extraction of Adam from the same paragraph failed. [Canary recheck](evaluation/results/final-acceptance/mcp-injection-recheck.json)

## Targeted fixes

1. Generate source span identifiers or offsets and reconstruct quotations server-side. Require an exact span plus an applicable source passage before accepting a claim. Re-run the architecture and quantitative cases to evaluate answer recovery and attribution.
2. Record deadline failures with per-attempt traces, including model-call duration and candidate rejection category. Benchmark serially with the default provider budget and cap the verifier's per-answer work.
3. Gate specialist prose on method-versus-experiment attribution. Use the Adam CNN error as a regression case. Validate a dedicated cross-paper answer against two independently cited claims.
4. Reproduce the second-upload event with a browser-level trace of the uploader state and registration response. Re-run live literature verification when OpenAlex is reachable and require a nonempty discovered record before scoring relevance.

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

## Final compliance

| Requirement | Status | Basis |
|---|---|---|
| External Markdown production prompts | PARTIAL | Runtime proof for Summary, Questions and corpus QA. Live literature relevance execution remains unverified. |
| Advanced prompt experiments and improved extraction | PARTIAL | Fresh paired comparison improved reference coverage from 2/6 to 4/6 on one abstract. Supported-claim share fell from 5/6 to 4/5, and neither follow-up question was useful under the rubric. |
| MCP invokes existing agents and exposes scientific-paper data | PASS | The independent external SDK run invoked the original analysis workflow and reloaded its structured data. Ingestion, retrieval and source inspection passed. Live literature discovery and dependable scientific QA remain separate gaps. |
| Confirmed scientific Agentic RAG objective | FAIL | Three pinned PDFs yielded 315 persistent chunks. Exact source retrieval passed, but the cross-paper query retrieved only Transformer chunks and deadline/abstention outcomes prevented a grounded answer. The isolated quantitative recheck reproduced abstention despite receiving the correct passage. [Corpus counts](evaluation/results/final-acceptance/corpus-checks.txt) · [Quantitative trace](evaluation/results/final-acceptance/mcp-quantity-recheck.json) |

**Verdict — NOT READY.** The verified indexing and source-inspection demonstration is reproducible. The required live scientific answer and cross-paper workflow did not pass acceptance.
