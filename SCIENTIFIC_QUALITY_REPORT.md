# Scientific quality report

The final live SDK run recovered correct source excerpts for Transformer architecture, the WMT 2014 BLEU result, Adam's moment estimates, both clauses of a Transformer/LoRA comparison, and the optimizer in the injection fixture. The clinical question abstained. The limitation answer selected a related future-work passage and the misleading-premise answer did not explicitly correct the premise. The result is five of seven answerable probes fully answered and one of one unanswerable probes correctly abstained. All eight returned citations matched the original PDF page substring. Two were incomplete or off-target responses despite exact provenance. The hostile fixture's instruction did not appear in the returned answer.

The paired benchmark matched five of six factual targets. In its held-out set, the selector returned material about a different adapter's latency for the LoRA conclusion question. This is an observed scientific scope error. The developer-run annotation is a pilot and cannot substantiate the 95% accuracy, 1% unsupported-claim, or broad cross-paper quality targets.

The QA output is extractive. Statements are attributable to their source excerpts and still need contextual interpretation. The original specialist analyses remain useful for exploration. They do not share the new exact-span validator. Current literature discovery still depends on OpenAlex and supplies metadata-level context.

The full Windows suite recorded 164 passed, 0 failed, and 0 skipped in 58.30 s. Chromium uploaded and indexed Adam, displayed a PDF page result, ran QA and downloaded an answer JSON containing the supported abstract excerpt. The earlier two-upload browser failure has no fresh end-to-end two-upload verification. [JUnit](evaluation/results/span-engineering-release/pytest.xml) · [Browser trace](evaluation/results/span-engineering-final/streamlit-corpus.json)

[SDK release outputs](evaluation/results/span-engineering-release/mcp-acceptance.json) · [Case-by-case scientific review](evaluation/results/span-engineering-release/review.json) · [Paired benchmark](evaluation/results/span-benchmark-release.json)
