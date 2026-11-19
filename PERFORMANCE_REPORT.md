# Performance report

The previous corpus QA flow could use two drafts and four separate model judgments per draft. The current default uses one model call with a 256-token output cap, or zero calls when no candidates survive screening. It resolves citations from SQLite and preserves the existing model cache key based on prompt, evidence, schema, and model identity.

The serial release SDK run recorded a median service-reported QA time of 2.884 s across eight probes, with a maximum of 3.780 s and zero timeouts. A second run during concurrent specialist experiments hit the 45 s model deadline on the Adam methodology case and took 36 s on the architecture case. These are acceptance observations across different workloads and runner states. They do not isolate a production latency distribution.

The final measurements use local Ollama with response caching disabled in the SDK harness. Persistent model state, warm GPU placement, and concurrent jobs can alter latency. No additional models were installed. [Serial timing](evaluation/results/span-engineering-release/mcp-acceptance.json) · [Concurrent timing](evaluation/results/span-engineering-release/mcp-concurrent.json)
