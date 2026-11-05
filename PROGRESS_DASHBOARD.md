# Research progress dashboard

The original Streamlit button used `asyncio.run(...)` on the script thread. It reported four stage transitions but blocked the UI during model requests. The replacement launches one background analysis worker, with a read-only Streamlit fragment that refreshes once a second. All Streamlit calls stay on the UI thread. The existing orchestrator, four specialists, cache, local provider settings and corpus workspace are retained.

## What is measured

| Indicator | Actual measurement and interpretation |
| --- | --- |
| Overall progress | Number of agents whose stages completed, divided by four. Values are real milestones, not estimates of elapsed work, cost or time remaining. A slow Summary Agent can leave this at 25% for a long time. |
| Summary input progress | Validated input-chunk responses completed, divided by the number of input chunks actually planned after PDF extraction and cost-limit validation. The active chunk is displayed separately and is not counted complete. |
| Summary synthesis | Actual groups completed within the currently known reduction pass. Further passes may be necessary; the UI does not invent their number or total duration. A 100% input-chunk bar does not mean synthesis or the agent is finished. |
| Elapsed time | Current server wall-clock time minus the run start. It is frozen at the recorded finish on success/failure. After a server interruption it freezes at the last persisted update, rather than counting server downtime as processing. |
| Active request time | Wall-clock time since the uncached provider generation call began. Model-identity checks and cache lookup happen before that point. It is elapsed time, not a request completion percentage. |
| Response activity | Real NDJSON messages received from Ollama and the Unicode characters in their content fields. These are neither model token counts nor percentages. The final message can have zero content characters. Partial generated text is not rendered or stored in the progress checkpoint. |
| Input-chunk ETA | Estimated remaining input-chunk processing time from completed uncached chunk durations. Requires at least three comparable observations, an average over 0.05 seconds, and coefficient of variation at most 0.5. The rolling window contains at most six timings; when over three are available, its oldest timing is excluded to reduce warm-up effects. The active request's elapsed time is deducted. Estimates are approximate and rounded up for display. |
| ETA unavailable | Shows “Estimating...” with too few/comparably unstable samples, on a stalled or overdue active request, or while synthesis work is not predictable. Cache hits never train the duration estimate. Input ETA becomes zero only once all input chunks actually finish. |
| Total workflow ETA | Remains “Estimating...” while future synthesis, questions and literature work have unknown counts/timings. The implementation does not infer their speed from unrelated summary chunks. On workflow completion it is zero; stopped runs are labeled stopped. |
| Stage status | Waiting, running, completed or failed. A lost worker gives the overall run an interrupted status and labels its formerly running stage failed, preserving the last completed counts. |

The existing `CHUNK_TOKENS` name still means a conservative UTF-8 byte budget; the dashboard counts those actual chunks, not pages or guessed model tokens. No token/context limits were raised for this change.

## Live requests, warnings and failures

When a progress observer is attached, Ollama uses native streamed chat. Each real response message updates an in-memory activity timestamp and character/message counts; the worker heartbeat persists these at roughly one-second intervals. Non-dashboard calls retain the existing non-streamed behavior. Both paths preserve structured-output validation. A chunk completes only after its final response validates and the LLM facade returns.

If an active generation call has received no response data for 60 seconds, the UI warns that the model may be loading or stalled. The warning neither increments progress nor proves the backend is dead. Response data clears the inactivity warning. The existing request timeout remains authoritative; streamed calls also enforce the configured total deadline, even if occasional packets keep arriving. A failed request or invalid final output never becomes a completed chunk.

Transient Windows checkpoint replacement failures receive short bounded retries. Persistent checkpoint failure is shown as a warning: live counters can continue, but restart recovery cannot be guaranteed. It does not abort otherwise valid research processing. Report/output failures still fail the run and leave previously completed files available.

## Reruns and interruptions

- Only **Start Analysis** launches a worker. One generation workflow is allowed per application process, protecting the existing local GPU budget. Reattaching to the same active run is idempotent. Completed/interrupted run identifiers cannot silently be reused for execution.
- The browser URL retains `?run=<run-id>`. Session state and that URL reconnect the UI to a worker; full reruns or reopening the URL do not start another analysis. Keep that URL to reopen the same local run. There is no global “latest user's run” fallback.
- One full rerun follows launch to disable Start. A single terminal transition refresh loads report downloads and turns off periodic fragment polling. Intermediate refreshes rerender only the dashboard; the analysis is not relaunched.
- Closing or refreshing the browser does not stop a worker while the same Python server process remains alive. No Streamlit session objects are passed to worker threads.
- Each run stores `output/<run-id>/progress.json` atomically, plus the existing reports. `result.json` records completed output names and warnings. Credentials, raw prompts and partial generated content are not stored in dashboard checkpoints. Reports and extracted text retain their existing sensitivity.
- **A server/process restart stops the in-flight single-PDF workflow.** Its saved counters and earlier reports survive when writes succeeded. On reopening the run URL, the checkpoint is marked interrupted, and the active chunk is explicitly labeled unfinished. The in-flight HTTP/model operation is not restored or replayed automatically.
- To process that PDF again after a server interruption, explicitly upload it and start a new run. The existing LLM cache can reuse validated completed operations if enabled; the current dashboard does not implement exact in-place workflow resumption. The separate corpus ingestion pipeline keeps its existing page-checkpoint resume behavior.
- This worker registry targets a single local Streamlit process. It is not a distributed queue, multi-process worker coordinator, cancellation interface, hard resource sandbox or authenticated multi-user recovery service.

## Verification — 4 November 2026

Mocked slow-call tests check that the page returns while a request is blocked, the Start button is disabled, repeated reruns and a fresh UI attached through the run URL do not duplicate calls, and response activity appears while the completed count is still zero. Additional tests cover ETA sample thresholds, cache exclusion, variable speeds, overdue requests, stall timing, frozen elapsed time, failed-chunk accounting, persistent interruption state, checkpoint failure visibility and incremental streamed responses. Existing report-download, corpus, provider and workflow tests remain.

An initial full run found a transient Windows checkpoint-write permission failure. After bounded retries and a nonfatal durability warning were added, the complete suite passed **112 tests in 143.36 seconds**. The final post-review full run passed **112 tests in 139.42 seconds**, with no failures or skips. These tests use mocks, fixtures and actual local PDF extraction; they do not make paid requests.

A separate **real, uncached local Ollama run** on a generated three-page synthetic automotive PDF completed **two input chunks, one reduction group and four streamed model calls** in **184.27 seconds**. Every generation request sent `stream=true` and `num_ctx=8192`; partial response characters were observed while the active input chunk was still unfinished. Completed counts advanced 0 → 1 → 2. Final status and counts were recovered from the saved JSON checkpoint. Paid APIs were disabled, credentials were removed from the smoke-test settings, and literature search used an empty local fixture; OpenAlex was not exercised in this dashboard smoke test. With only two map-chunk timings, the honest input ETA remained “Estimating...” until the map work completed; numerical ETA behavior was verified with controlled test timings.

Live artifacts: `output/868ff04a9e844678903418f283605495/`; verification script: ignored `.runtime/verify_dashboard.py`. These synthetic fixtures are not publications or research conclusions. The elapsed time is an observation on this machine during testing, not a performance guarantee. A physical browser tab-close/server-restart experiment was not performed; recovery state and fresh-UI attachment were exercised through checkpoint and Streamlit AppTest tests. No commits or pushes were made.

Implementation references: [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment), [Ollama chat and streaming](https://docs.ollama.com/api/chat).
