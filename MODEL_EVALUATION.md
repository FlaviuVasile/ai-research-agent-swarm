# Local model evaluation

## Live environment snapshot

Values below were queried locally on 2026-11-19; no credentials or secret environment values were printed.

| Resource / setting | Live observation |
|---|---|
| CPU | AMD Ryzen 7 5800H, 8 cores / 16 logical processors |
| RAM | 15.41 GiB total; 1.98 GiB free at probe time |
| GPU | NVIDIA GeForce RTX 3050 Ti Laptop GPU; 4,096 MiB total, 2,997 MiB in use, 0% utilization at probe time |
| Ollama placement | `llama3.2:latest` reported 100% GPU, context 8,192 |
| Installed models | `llama3.2:latest` (2.0 GB), `all-minilm:latest` (45 MB) |
| Effective provider/model | Ollama / `llama3.2:latest` |
| Context / output | 8,192 context; 1,200-token general output limit; corpus QA defaults to a separate smaller cap |
| Timeout | 90 s per LLM call; 600 s document operation |
| Other controls | Temperature 0; cache enabled; paid API disabled; local test mode disabled |
| Embeddings | `all-minilm:latest`, context 512 |

These are a point-in-time workstation snapshot, not a stable performance guarantee.

## Quality evidence

The only installed generation model is Llama 3.2. A constrained span-selection pilot matched **5/6** labelled factual targets (95% Wilson interval 44%–97%); the two tested selector prompts tied. The previous live SDK set fully answered **5/7** answerable probes, while one cross-paper check required five model calls and still returned partial evidence. These failures cannot be attributed solely to model size: retrieval selection, context applicability, and verifier false decisions are also observed constraints.

No alternative generation model was downloaded or tested. There is no controlled cross-model comparison, quantization comparison, or hardware-performance curve. The user authorized no model downloads; none were performed.

## Recommendation

Keep Llama 3.2 as the baseline. Do not download a replacement until the user approves a shortlist and the same reviewed test set, prompt, retrieval context, output budget, and repeated-run protocol are available. First reduce irrelevant candidates and improve paper-specific evidence selection; this is cheaper and can be evaluated without changing the model.

Probe source: sanitized `Settings.from_env()` and `CorpusConfig.from_env()` values, Windows CIM, `nvidia-smi`, `ollama list`, and `ollama ps`. No `.env` secrets were emitted.
