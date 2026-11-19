# Retrieval ablation results

## Setup

The saved experiment indexes the same three PDF corpus and compares raw BM25, normalized BM25, normalized BM25 with question-clause splitting, semantic retrieval, and hybrid reciprocal-rank fusion. Each arm uses top 10 and the same six source-anchored factual targets. The labels are a **pilot with human review pending**. Bootstrap intervals use 10,000 query-level resamples of five answerable questions and seed 20261119; they should not be read as population-level confidence.

| Arm | MRR (95% bootstrap interval) | Precision@10 (95% bootstrap interval) | Recall@10 (95% bootstrap interval) | Mean retrieval latency (ms, 95% interval) |
|---|---:|---:|---:|---:|
| BM25, raw | 0.677 (0.443–0.910) | 0.240 (0.120–0.360) | 0.933 (0.800–1.000) | 24.5 (23.0–25.7) |
| BM25, normalized | 0.717 (0.517–0.917) | 0.240 (0.120–0.360) | 0.933 (0.800–1.000) | 31.2 (28.3–34.2) |
| BM25, normalized + clause split | **0.750 (0.550–0.950)** | **0.260 (0.120–0.400)** | **0.967 (0.900–1.000)** | **34.6 (28.6–45.3)** |
| Semantic + clause split | 0.587 (0.303–0.870) | 0.220 (0.100–0.340) | 0.833 (0.633–1.000) | 126.9 (104.6–155.8) |
| Hybrid RRF + clause split | 0.750 (0.550–0.950) | 0.220 (0.100–0.340) | 0.833 (0.633–1.000) | 183.1 (147.5–240.5) |

All five arms found **6/6** targets at top 10 (target-level 95% Wilson interval 61%–100%). Normalized BM25 plus clause splitting ranks the target evidence well with a lower observed cost than hybrid; the sample is too small to conclude that hybrid is generally worse.

## Engineering decision and limitations

Keep SQLite/FTS5 and BM25 as the default. Keep embeddings optional and local; no vector database or external service is warranted by these results. The experiment does not isolate section-aware indexing, cross-paper answer correctness, reranking quality, or relevance judgments across a broad corpus. The production per-paper comparison path and candidate selection are separate implementation safeguards, not independently benchmarked retrieval arms.

## Reproduction

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.retrieval_ablation `
  --corpus .runtime\<new-complete-three-paper-corpus> `
  --output evaluation\results\<new-retrieval-run>.json
```

Add `--index-embeddings` only when measuring embedding construction as part of the run. The runner requires complete documents and refuses to overwrite an existing result.

Source and raw data: [`evaluation/retrieval_ablation.py`](evaluation/retrieval_ablation.py), [`retrieval-ablation-20261118.json`](evaluation/results/retrieval-ablation-20261118.json), and [`span-benchmark-release.json`](evaluation/results/span-benchmark-release.json).
