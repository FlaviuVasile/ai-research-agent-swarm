# Scientific evaluation

The pilot used three SHA-256-pinned arXiv PDFs and 315 indexed passages. See [source metadata and abstract labels](../evaluation/sources.json). The ranking evaluation uses four answerable queries and one unanswerable query. A chunk is relevant when it matches the manually specified PDF checksum, page and normalized text span. Labels cover the designated passages and may omit equivalent evidence elsewhere in the paper.

| Retrieval | Precision@5 | Recall@5 | MRR@5 | Mean query time |
|---|---:|---:|---:|---:|
| Keyword BM25 | 0.200 | 0.708 | 0.583 | 40 ms |
| Local semantic | 0.150 | 0.500 | 0.313 | 113 ms |
| Hybrid RRF | 0.200 | 0.750 | 0.458 | 170 ms |

Precision divides matched chunks by five. Recall divides matches by labelled relevant chunks. Reciprocal rank is the reciprocal of the first relevant hit's rank, or zero if none appears. Means use the four answerable queries. Times cover retrieval and exclude indexing or generation. Keyword remains the default because the pilot recorded the best first-relevant rank and shortest query latency with a small decrease in recall against hybrid. These metrics describe ranking against narrow annotations. [Raw results](../evaluation/results/corpus-retrieval-live.json)

The QA comparison uses fixed prompts, top-k, corpus, Llama 3.2 and temperature. The conditions are baseline with keyword, evidence-first with keyword, and evidence-first with hybrid. One pass was run per condition. The pre-hardening experiment exposed unsupported values and a confusion between a BLEU score and a clinical dropout percentage, despite a model entailment check. Those failures motivated a separate deterministic numeric consistency check and a stricter verifier prompt. [Pre-hardening outputs](../evaluation/results/corpus-prompts-before-numeric-check.json)

| Condition after numeric hardening | Answerable results | Unanswerable case |
|---|---|---|
| Baseline and keyword | 0 of 2 answered | Timed out |
| Evidence-first and keyword | 0 of 2 answered | Abstained |
| Evidence-first and hybrid | 0 of 2 answered | Timed out |

Answerable results require a returned claim with the expected fact. An explicit insufficient-evidence response counts as abstention for the unanswerable case. The follow-up run above precedes the revision prompt and provides no evidence of a factual-accuracy gain. [Post-hardening outputs](../evaluation/results/corpus-prompts-live.json)

The pilot shares papers and some questions with development. It cannot establish held-out gains, comprehensive annotation recall, inter-rater agreement, or research-question usefulness. Existing specialist prompt experiments are recorded separately. [Prior specialist evaluation](../evaluation/EXECUTION_REPORT.md)
