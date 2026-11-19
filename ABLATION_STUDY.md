# Ablation study

| Condition | Observation |
|---|---|
| Prior end-to-end QA | 0 factual responses across eight live acceptance cases |
| Retrieval only, raw BM25 to normalized clauses | Target MRR rose from 0.656 to 0.750 on the six-target pilot |
| Short selector with clause retrieval | 5/6 factual targets and correct abstention on the clinical probe |
| Evidence-first selector with clause retrieval | 5/6 factual targets and correct abstention on the clinical probe |
| Evidence-first selector with a single concatenated comparison query | 1/2 comparison targets |
| Evidence-first selector with two separately retrieved clauses | 2/2 comparison targets |
| Deterministic provenance validation | 8/8 output spans in the live SDK release run resolved to their exact PDF page substring |

The historical acceptance used a different inference workload and a separate validation architecture, so its result is an operational baseline. Selector prompting and decomposition use paired conditions with the same generation model. The comparison ablation changes both retrieval partitioning and the answer slots supplied to the selector. Semantic checking, span screening, and dynamic agentic orchestration were not isolated in a full factorial study. [Paired data](evaluation/results/span-benchmark-release.json) · [Historical acceptance](FINAL_ACCEPTANCE_REPORT.md)
