# Prompt experiments — 17 November 2026

## Workload and controls

Twenty-seven real local model calls compared baseline, field-by-field, and
evidence-first/consistency-check prompts: three variants × three real paper
abstracts × summary, questions and title-only literature assessment.

Sources are fixed arXiv versions:

- Vaswani et al., *Attention Is All You Need*, 1706.03762v7, physical page 1.
- Kingma and Ba, *Adam: A Method for Stochastic Optimization*, 1412.6980v9, page 1.
- Hu et al., *LoRA: Low-Rank Adaptation of Large Language Models*, 2106.09685v2, page 1.

`sources.json` records URLs, original PDF SHA-256 checksums, normalization and
the exact shared evidence. PDFs remain under `.runtime/evaluation-papers/`.
The experiment uses abstract evidence, not the entire papers. It intentionally
bypasses FAST domain selection so every variant receives identical evidence.
Line hyphenation is joined and whitespace normalized; e.g. `English-to-German`
has an extraction artifact in one source. The frozen evidence records that
artifact instead of silently changing it between variants.

Model: locally installed `llama3.2:latest`, digest recorded in the raw results.
Temperature 0, main/summary context 8192, summary output 256, other output 1200,
chunk bytes 2000, GPU layers 99. Response caching and summary journals are
disabled. Question count is one. Questions receive a fixed summary placeholder,
not a different upstream model-generated summary. Literature receives the same
fixed efficiency question and each real title; no live search results confound
the prompt comparison. Variant order rotates between papers. No paid API runs.

## Review methodology

The reference checklist contains six facts per paper (`rubric.json`). Codex
reviewed raw outputs against the supplied evidence and recorded per-output
counts and explanations in `review_rows.json` and the hash-bound reviews file.
These are analyst judgments, **not independent human annotations**. Counts of
distinct factual clauses are sensitive to segmentation. The raw outputs and
notes permit reassessment; no LLM-as-judge score is presented as ground truth.

Factual precision = supported clauses / factual clauses. Hallucination rate is
unsupported clauses / factual clauses, relative to the actual input: facts
known from elsewhere still count as unsupported. Reference recall credits
complete checklist facts; missing score/language or GPT-3 comparator details
lose credit. Generic rationale in question importance is not scored as a
paper finding. Citation correctness requires a resolving supporting reference.

Schema validity measures the existing Pydantic contract for questions and
relevance. Summary validity means a nonempty string, not semantic validity.
Question task checks require a concrete future research question with faithful
evidence and a correct explicit/inferred label. Literature checks require
title-only scope disclosure and no unsupported findings or methods.

## Measured results

| Summary strategy | Supported-clause precision | Reference recall | Unsupported clauses | Mean seconds | Generated tokens, total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 22/23 (95.7%) | 7/18 (38.9%) | 1 | 18.26 | 255 |
| Fields | 19/19 (100%) | 11/18 (61.1%) | 0 | 13.53 | 321 |
| Evidence | 21/21 (100%) | 9/18 (50.0%) | 0 | 17.65 | 253 |

Fields retained more checklist facts in this sample and consistently included
named fields/missing-limitations handling. It still omitted important details
and sometimes exceeded the requested 70 words. No summary produced a correct
resolving page citation. Baseline's bare `[1]` is not a valid source citation.
Zero citations means citation precision is undefined, not 100%.

| Question strategy | Category correct | Complete research-question task pass | Mean seconds | Generated tokens, total |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 0/3 | 0/3 | 36.33 | 639 |
| Fields | 0/3 | 0/3 | 37.10 | 819 |
| Evidence | 2/3 | 0/3 | 20.92 | 291 |

All question outputs were schema-valid, but they mostly asked already-answered
descriptive questions. Evidence-first reduced category errors on two papers;
it did **not** establish good research-gap discovery. The baseline even returned
the combined category string `Explicit limitation or inferred research
opportunity`, which the existing unconstrained string field accepts.

| Title relevance strategy | Unsupported clauses | Title-only task pass | Mean seconds | Generated tokens, total |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 16/17 | 0/3 | 10.92 | 201 |
| Fields | 29/30 | 0/3 | 17.81 | 347 |
| Evidence | 19/20 | 0/3 | 15.51 | 251 |

All relevance outputs were schema-valid. All strategies introduced unsupported
methods or benefits and failed the strict title-only task check. Some LoRA
outputs asserted faster inference, which is not established by the title.
The longer prompts did not solve this problem.

## Production selection

`PROMPT_VARIANT=selected` is now the default. `prompts/selection.json` chooses:

- **Fields summary:** highest observed reference recall, no unsupported clause
  identified in this sample. The measured advantage is 22.2 percentage points
  of checklist recall over baseline, not a general full-paper accuracy claim.
- **Evidence questions:** fewer category errors and fewer generated tokens;
  research novelty and usefulness still require review.
- **Baseline literature:** none passed; keep the least costly baseline instead
  of claiming an unmeasured improvement. Existing title-only report warnings
  remain. No relevance output should be treated as verified paper findings.

`PROMPT_VARIANT=baseline`, `fields`, or `evidence` reproduces a whole family.
Runtime-selected prompts preserve the existing Markdown/Pydantic contracts.

## Limitations and cost interpretation

This is one paired pass on three familiar ML abstracts, with no held-out set,
independent reviewers, repeated trials or confidence intervals. Familiar titles
may trigger memorized claims, which is particularly visible in relevance
outputs. Temperature 0 does not guarantee identical reruns. Timing includes
changing local hardware load/model residency; do not interpret the mean times
as a statistically established speedup. Prompt/evaluation token counts and
Ollama durations are preserved in raw JSON. Monetary API cost was zero; local
electricity and compute were not priced. Citation grounding remains unresolved.

## Reproduce

```powershell
.\.venv-swarm\Scripts\python.exe evaluation/prepare.py
.\.venv-swarm\Scripts\python.exe -m evaluation.run --output evaluation/results/new-run.json
.\.venv-swarm\Scripts\python.exe -m evaluation.score evaluation/results/local-2026-11-17.json evaluation/results/local-2026-11-17-reviews.json --output evaluation/results/recomputed-metrics.json
```

`prepare.py` downloads only the listed public versions; normal app/MCP analysis
does not download PDFs. Review each new run independently: `score.py` rejects
reviews whose result-file hash does not match. The score script also validates
review/result identities, count bounds and reference-fact indices.

Raw evidence: `results/local-2026-11-17.json`; analyst review:
`results/local-2026-11-17-reviews.json`; aggregates:
`results/local-2026-11-17-metrics.json`. The prompt fingerprint in the experiment
predates adding `selection.json`; no tested variant Markdown changed afterward.
