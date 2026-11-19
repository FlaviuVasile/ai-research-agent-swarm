# Retrieval experiments

The pilot used the same persisted passages for each ranking mode. Top-ten recall counts factual targets with at least one labelled passage in the returned ten positions. Reciprocal rank is calculated per target and averaged. Timing is the observed median of six retrieval calls. Candidate passages may have alternate valid support outside the labelled anchors.

| Configuration | Targets in top ten | Mean reciprocal rank | Median |
|---|---:|---:|---:|
| Existing BM25 | 6/6 | 0.656 | 42 ms |
| Normalized BM25 | 6/6 | 0.694 | 38 ms |
| Normalized BM25 with clause splitting | 6/6 | 0.750 | 31 ms |
| Local semantic | 6/6 | 0.547 | 125 ms |
| Hybrid reciprocal rank fusion | 6/6 | 0.708 | 158 ms |

The LoRA source for the cross-paper question moved from rank 10 to rank 2 after query normalization and clause splitting. Keyword remains the default on this hardware and pilot. Semantic and hybrid remain available. This run did not compare fixed-size and section-aware reindexing. It used existing section-aware chunks and sentence excerpts within parent passages, without adding a second index. [Rankings](evaluation/results/span-benchmark-release.json)
