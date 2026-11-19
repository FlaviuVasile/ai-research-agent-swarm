# Scientific RAG benchmark status

## Dataset status

The current reproducible pilot contains **6 questions over 3 papers** (Adam, *Attention Is All You Need*, and LoRA). It has a small development/held-out question split, with papers shared across the split, one intentionally unanswerable clinical question, and six answerable source targets. The target anchors are encoded in [`evaluation/span_benchmark.py`](evaluation/span_benchmark.py). The retrieval ablation labels explicitly state **human review pending** in [`evaluation/results/retrieval-ablation-20261118.json`](evaluation/results/retrieval-ablation-20261118.json).

This is not the requested frozen 50-question benchmark, is not held out by paper, and must not be treated as independently verified ground truth. The local evaluation directory contains only three source papers. Human review and additional papers are prerequisites for an acceptance benchmark.

## Retrieval results

The table uses the saved five-arm retrieval ablation: six labelled targets, five answerable question cases, top-10 rankings, and query-level means. Bootstrap intervals below are 95% percentile intervals over 10,000 resamples of the five answerable query cases (seed 20261119); this is exploratory and has very low effective sample size. All arms found 6/6 labelled targets, whose two-sided 95% Wilson interval is approximately **61%–100%**.

| Strategy | MRR (95% bootstrap interval) | Precision@10 (95% bootstrap interval) | Recall@10 (95% bootstrap interval) | Mean latency (s, 95% bootstrap interval) |
|---|---:|---:|---:|---:|
| Raw BM25 | 0.677 (0.443–0.910) | 0.240 (0.120–0.360) | 0.933 (0.800–1.000) | 0.0245 (0.0230–0.0257) |
| Normalized BM25 | 0.717 (0.517–0.917) | 0.240 (0.120–0.360) | 0.933 (0.800–1.000) | 0.0312 (0.0283–0.0342) |
| Normalized BM25 + clause splitting | **0.750 (0.550–0.950)** | **0.260 (0.120–0.400)** | **0.967 (0.900–1.000)** | 0.0346 (0.0286–0.0453) |
| Semantic + clause splitting | 0.587 (0.303–0.870) | 0.220 (0.100–0.340) | 0.833 (0.633–1.000) | 0.1269 (0.1046–0.1558) |
| Hybrid RRF + clause splitting | 0.750 (0.550–0.950) | 0.220 (0.100–0.340) | 0.833 (0.633–1.000) | 0.1831 (0.1475–0.2405) |

This pilot supports normalized BM25 with clause splitting as the current low-latency default; it does **not** establish superiority on a sufficiently large, human-reviewed dataset. Semantic and hybrid modes remain available.

## QA and citation observations

- Paired selector prompts each matched **5/6** answer targets; exact two-sided 95% Wilson interval: **44%–97%**. Each correctly abstained on the single unanswerable probe (**1/1**, interval **21%–100%**).
- The held-out questions were only three questions sharing the same papers; both prompt variants matched **2/3** held-out targets (**67%**, Wilson interval **21%–94%**).
- A prior eight-case live SDK release run had **5/7** answerable probes fully correct and **1/1** unanswerable probe correctly abstained; the 95% Wilson intervals are approximately **36%–92%** and **21%–100%**, respectively. All **8/8** citation spans resolved exactly to source page text (interval **68%–100%**). Exact provenance is not semantic support.
- Latest live cross-paper MCP run: **2/2** citations had exact provenance (95% Wilson interval **34%–100%**), but the response remained partial and synthesis was not validated.
- Live Streamlit: the Adam paper was ingested as 15/15 pages and the beta defaults answer displayed as an extractive result with source evidence. This was one demonstration question, not a held-out score.

The pilot does not provide reviewed claim-level labels, so unsupported-claim rate, scientific factual accuracy, incorrect abstention, completeness, evidence relevance, question usefulness, and calibrated latency distributions are **not established**. Do not infer them from citation provenance.

## Reproduction

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.retrieval_ablation `
  --corpus .runtime\<new-complete-three-paper-corpus> `
  --output evaluation\results\<new-retrieval-run>.json
.\.venv-swarm\Scripts\python.exe -m evaluation.span_benchmark --live --embeddings `
  --output evaluation\results\<new-span-run>.json
```

The first command requires an already ingested, isolated corpus with all three complete PDFs. Both runners preserve existing outputs by requiring new destination paths.

Raw evidence: [`retrieval-ablation-20261118.json`](evaluation/results/retrieval-ablation-20261118.json), [`span-benchmark-release.json`](evaluation/results/span-benchmark-release.json), [`span-engineering-release/mcp-acceptance.json`](evaluation/results/span-engineering-release/mcp-acceptance.json), and [`agentic-rag-cross-validation5-20261119.json`](evaluation/results/agentic-rag-cross-validation5-20261119.json).
