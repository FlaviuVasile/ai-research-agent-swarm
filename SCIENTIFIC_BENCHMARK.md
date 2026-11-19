# Scientific benchmark

The reproducible pilot uses three pinned scientific PDFs from [sources.json](evaluation/sources.json). The release benchmark records six questions and six factual targets. Two development queries cover the Transformer result and a Transformer/LoRA comparison. A third development query deliberately asks about a nonexistent clinical result. The three held-out pilot queries cover AdaMax, the Transformer abstract's French score, and inference latency in the LoRA conclusion. These are held-out questions over shared papers and the sample has no independent annotator.

Reference fragments and page numbers in [span_benchmark.py](evaluation/span_benchmark.py) are manually checkable against the pinned PDFs. Exact offsets and applicability were also checked in eight live SDK probes, including a fabricated injection fixture. Target-match counts use page, paper and normalized text fragments. An exact match of character offsets measures provenance only. Source relevance and scientific attribution need a separate check.

```powershell
.\.venv-swarm\Scripts\python.exe -m evaluation.corpus_rag_demo --evidence-only
.\.venv-swarm\Scripts\python.exe -m evaluation.span_benchmark --live --embeddings --output evaluation/results/reproduced-span-benchmark.json
```

[Release measurements](evaluation/results/span-benchmark-release.json) · [Live SDK probes](evaluation/results/span-engineering-release/mcp-acceptance.json)
