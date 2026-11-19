# Prompt ablation results

## Controlled corpus-QA comparison

The saved paired pilot used the same three scientific PDFs, Llama 3.2, uncached inference, and the same retrieval setup for the short selector and evidence-first selector. Six questions represented five answerable questions (six factual targets) and one unanswerable question.

| Prompt | Target matches | Answerable question coverage | Unanswerable abstention | Median latency |
|---|---:|---:|---:|---:|
| Short baseline selector | 5/6 (83%; 95% Wilson 44%–97%) | 4/5 fully covered (80%; 38%–96%) | 1/1 (100%; 21%–100%) | 0.408 s |
| Evidence-first selector | 5/6 (83%; 95% Wilson 44%–97%) | 4/5 fully covered (80%; 38%–96%) | 1/1 (100%; 21%–100%) | 0.420 s |

The paired difference in target coverage is **0/6**. Both prompts missed the same LoRA conclusion target; the evidence-first variant is retained for clearer source scope and response instructions, not for demonstrated quality improvement. The held-out subset is only three questions over papers also used during development.

## Other prompt experiments

The prior specialist pilot compared existing fields prompts with evidence-oriented alternatives using local Llama 3.2 and pinned paper inputs. It revealed concrete failure modes rather than a validated win: Adam's online-convex-optimization framework was misdescribed as a dataset/benchmark; a Transformer resource constraint was labeled an explicit limitation without abstract support; and the revised question prompt elicited a question about an issue the source did not establish as unresolved. One alternative was restored rather than promoted.

No controlled, human-scored comparison of few-shot prompting, structured synthesis, correction prompts, or every production agent has been completed. Numerical fidelity, research-question usefulness, unsupported-claim rate, and held-out extraction quality are not established.

## Decision

Keep the evidence-first corpus prompt and existing agent-specific Markdown prompts, but treat the prompt choice as a conservative design decision, not a proven accuracy increase. Do not select more elaborate prompt variants until a blinded, reviewed dataset shows a measurable held-out benefit at an acceptable latency cost.

Raw comparisons: [`span-benchmark-release.json`](evaluation/results/span-benchmark-release.json), [`span-specialist-prompt-pilot.json`](evaluation/results/span-specialist-prompt-pilot.json), and [`span-specialist-tested-fields-questions.md`](evaluation/results/span-specialist-tested-fields-questions.md). The source is [`evaluation/span_benchmark.py`](evaluation/span_benchmark.py); production instructions are under [`prompts/`](prompts/).
