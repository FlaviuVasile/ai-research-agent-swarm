# Local model suitability

The installed generation model is Llama 3.2 3.2B Q4_K_M. All-MiniLM is the dedicated embedding model, using 384-dimensional vectors and its 512-token model context. It was tested for semantic retrieval and hybrid fusion. The workstation reported 15.4 GiB RAM and 4 GiB VRAM on an RTX 3050 Ti Laptop GPU. The active generation runner reported 100% GPU placement at 8,192 context.

| Model and task | Observed outcome |
|---|---|
| Llama 3.2, unconstrained claim writing and quote reproduction | Previous acceptance returned no factual answers in eight SDK QA cases. |
| Llama 3.2, constrained span selection | Five of six factual targets matched in the paired benchmark. One question selected an excerpt about adapter latency that did not answer the LoRA claim in the conclusion. |
| All-MiniLM, semantic retrieval | Six of six pilot targets appeared in the top ten. Its first matching passage ranked lower on average than normalized BM25 with clause splitting. |

The workstation has one installed generation model. No cross-model quality or quantization comparison was measured. The same benchmark can compare a second compact local model once its weights are available. No new weights were downloaded. [Raw pilot](evaluation/results/span-benchmark-release.json) · [Hardware and runner probe](evaluation/results/span-engineering-release/hardware.txt)
