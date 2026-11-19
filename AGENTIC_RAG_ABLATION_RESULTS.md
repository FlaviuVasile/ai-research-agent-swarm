# Agentic RAG ablation results

## Runtime distinction

The corpus QA workflow is bounded and adaptive in limited ways: it can decompose question clauses, retrieve per named paper, select addressable spans, request at most one additional retrieval for a part, synthesize complex answers, check claims, and perform one correction attempt. This does not mean specialist agents are dynamically orchestrated for each question. Existing agents are invoked by the separate fixed analyze-paper workflow; corpus QA currently calls its selector/synthesis/validation roles instead.

## Observed comparison

| Mode / probe | Evidence |
|---|---|
| Fast extractive corpus QA | Streamlit live run processed Adam (15/15 pages), retrieved exact source spans, returned an extractive beta-default answer, and exposed original PDF evidence. No semantic support assessment was claimed for the extractive answer. |
| Bounded adaptive cross-paper QA | Latest MCP SDK run required five model calls (one span selection, two synthesis drafts, two claim-validation calls); it made no additional retrieval. The comparison draft was rejected, so the final response exposed exact excerpts from both papers as `partial_evidence`. |
| Comparison coverage | Live result: evidence selected from both papers; `missing_documents` empty; both papers listed as `unvalidated_documents`; `synthesis_validated=false`. Citations were exact page spans, but this proves provenance rather than a correct comparison. |
| Unanswerable query | Earlier live smoke runs abstained on an unrelated clinical-dropout request; the small pilot reports 1/1 correct abstention, with wide uncertainty. |

This is not a controlled conventional-RAG-versus-Agentic-RAG experiment: the cross-paper probe, prompt, context, and model behavior were not randomized against an identical nonadaptive control. It does not show that multi-step orchestration improves scientific accuracy; it does show added latency and model calls for an unresolved comparison.

## Decision

Preserve the fast path for simple queries. Keep complex-query synthesis and correction bounded. Do not route to specialist agents by default: live evidence does not yet justify their latency cost in corpus QA. Improve retrieval relevance and evaluate usefulness on human-reviewed held-out questions before enabling dynamic specialist selection.

Reproduce the live case using a new corpus/output path:

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.agentic_rag_smoke `
  --case cross_paper `
  --corpus-root .runtime\<new-cross-paper-corpus> `
  --output evaluation\results\<new-cross-paper-run>.json `
  --pdf-root .runtime\evaluation-papers
```

Latest raw output: [`agentic-rag-cross-validation5-20261119.json`](evaluation/results/agentic-rag-cross-validation5-20261119.json). Implementation and contract tests: [`research_swarm/corpus/qa.py`](research_swarm/corpus/qa.py) and [`tests/test_corpus_qa.py`](tests/test_corpus_qa.py).
