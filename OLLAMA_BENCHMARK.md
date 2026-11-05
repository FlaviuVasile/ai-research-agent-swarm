# Live Ollama latency benchmark ? 4 November 2026

Benchmarked the complete Orchestrator using the installed llama3.2:latest (3.2B Q4_K_M), a generated one-page synthetic research PDF, one question and one real OpenAlex result. All three LLM stages used real local inference. Response caching was disabled and each run used a new corpus/journal database. All three runs below generated all four report artifacts without warnings. Application question/paper limits were not changed; the smaller limits apply only to the benchmark.

| Run | End-to-end seconds | Model loading seconds | Token generation seconds | Generated tokens |
| --- | ---: | ---: | ---: | ---: |
| before-warm | 44.56 | 25.003 | 14.24 | 301 |
| after-warm | 25.78 | 0.036 | 17.28 | 303 |
| after-cold | 30.20 | 11.961 | 12.35 | 241 |

The baseline started with the model already resident at 8192 context, but summary requested 4096 and questions requested 8192. Those two switches incurred 12.59 + 12.40 seconds of model loading. The optimized warm run kept all requests at 8192: 44.56 ? 25.78 seconds (42.2% lower latency). Total loading fell from 25.003 to 0.036 seconds. First response text for summary/questions fell from 13.33/13.76 seconds to 1.12/1.19 seconds.

The optimized cold run explicitly unloaded the model before starting. It completed in 30.20 seconds, including 11.94 seconds of initial loading; subsequent stages took only 0.025 seconds of loading combined. The original cold probe took 37.41 seconds but OpenAlex was unavailable in its sandbox, so it is not a valid full-workflow comparator.

These are single runs, not statistical averages. Generated text, output lengths, OpenAlex results and external timing can vary; warm token generation actually took longer despite nearly identical token counts. The measured gain comes from removing model reloads, not from claiming faster decoding. PDF extraction took about 0.02 seconds. In the optimized warm run, prompt evaluation totaled 1.08 seconds versus 17.28 seconds generating tokens. Generation is now the main measured inference cost; reducing output quality, paper coverage or switching models was avoided. Local ps reported partial GPU placement at 8192 context; forcing additional GPU layers was not attempted.

Changes:

- Summary context now defaults to the main configured context, capped at its supported 8192 maximum. Explicit SUMMARY_CONTEXT_TOKENS overrides remain honored. The standalone Settings default is 8192. This avoids the default 4096/8192 switch without increasing the existing main allocation.
- Chat requests explicitly keep the model resident for 10 minutes to reduce loading between nearby analyses. This retains model memory longer; it does not eliminate a true cold load or prevent eviction by another model.
- Added prompt_eval_duration to existing request telemetry so prompt processing can be separated from generation and loading.
- Added tools/benchmark_ollama.py. Use a new label for every run, e.g. `.venv-swarm/Scripts/python.exe tools/benchmark_ollama.py trial-1`; append `--cold` to unload this model first. It writes timings.json and generated artifacts under output/ollama-latency-benchmark/<label>/ and makes real OpenAlex requests. It never enables paid providers.

Timing field units and residency semantics follow the [official Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md).

Verification: full suite 134 passed in 65.28 seconds; after adding two targeted regressions, configuration/provider checks 44 passed in 24.56 seconds. Live runs also validated the streamed responses and structured questions/relevance outputs through the existing pipeline.

Restart the Streamlit process to load the code changes. If SUMMARY_CONTEXT_TOKENS was explicitly set to 4096 in another environment, that override remains in effect.


## Further reduction below 10 seconds

The follow-up used the same installed model, 8192 context, prompts, evidence selection, output limits and bounded one-question/one-paper workflow. Application limits and features were preserved. Response caching remained disabled; each run had an independent corpus/journal database and actual OpenAlex retrieval.

| Run | End-to-end seconds | Generated tokens | Generation tokens/second | Prompt evaluation seconds |
| --- | ---: | ---: | ---: | ---: |
| after-warm | 25.78 | 303 | 17.5 | 1.076 |
| gpu-all-warm | 11.15 | 277 | 65.3 | 0.408 |
| gpu-http-warm-1 | 8.22 | 277 | 62.3 | 0.372 |
| gpu-http-warm-2 | 7.79 | 277 | 61.1 | 0.353 |

The two final warm runs averaged **8.00 seconds**, versus the preceding 25.78 seconds: approximately **69% lower latency**, or **3.2x faster**. Both generated all four artifacts without warnings. Full-GPU-only and both final runs produced byte-for-byte identical text artifacts and identical generated token counts; the isolated HTTP improvement was 11.15 ? 8.22 seconds. These are small-sample real timings, not a guarantee for larger documents or more questions/papers. The 25.78-second historical run produced 303 tokens versus 277 here, so it is not an equal-token microbenchmark.

Measured bottlenecks and fixes:

1. **CPU/GPU splitting.** Ollama previously reported 33% CPU / 67% GPU placement. Explicit GPU layer placement now fits the complete llama3.2 model and 8192 context on this laptop: ps reports 100% GPU, about 3.0 GB model allocation; nvidia-smi reported about 2995 MiB used out of 4096 MiB. Generation throughput increased from about 17.5 tokens/second in the earlier warm run to about 61 tokens/second. A first run after changing placement still spent 11.49 seconds loading; cold starts are not covered by the sub-10-second claim.
2. **Repeated unused certificate setup.** Three local /api/ps probes with normal certificate initialization took 0.824/0.716/0.615 seconds; without it they took 0.007/0.004/0.004 seconds. Ollama URLs are validated as loopback plain HTTP and redirects/proxies remain disabled. The provider now skips TLS certificate initialization for those HTTP clients, including model inspection; local embedding clients use the same optimization after their existing endpoint guard. Remote OpenAlex and OpenAI retain certificate verification.
3. **Remaining critical path.** On the second final run, actual model generation totaled 4.53 seconds, prompt evaluation 0.35 seconds, and PDF extraction 0.02 seconds. The rest includes live external retrieval, corpus checkpoints, inspection and request/stream overhead. For this one-question workload, questions require the summary and relevance requires the generated question plus retrieved title. Those dependencies were preserved; simultaneous GPU inference was unnecessary to reach the target.

Added an optional application setting, OLLAMA_GPU_LAYERS, forwarded to Ollama as num_gpu. Empty/unset retains automatic placement on other machines; 0 supports CPU placement. This project's private .env now sets 99 for the verified local model/hardware; existing configuration entries were retained. This is an application setting, not an Ollama server environment setting. Reassess the override if changing to a larger model/context or a different GPU. Prompts, temperature, output limits, evidence coverage, model weights, citation validation and report formatting were not changed. No formal answer-quality benchmark was introduced; existing validations and inspected artifacts remain the quality checks.

GPU placement semantics and CPU transfer overhead are documented in the [official Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx) and [Ollama source discussion of num_gpu](https://github.com/ollama/ollama/issues/8447).

Reproduce using a fresh label:

```powershell
.venv-swarm/Scripts/python.exe tools/benchmark_ollama.py fresh-label
```

The benchmark also supports --gpu-layers for temporary per-run placement comparisons. Restart Streamlit so the running provider loads these code changes.

Final verification: **144 tests passed in 60.66 seconds**, including GPU option validation, automatic/CPU/GPU payload selection, local HTTP client settings, and the complete workflow/UI suite.
