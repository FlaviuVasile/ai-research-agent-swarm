# RAG implementation roadmap

Application changes begin after roadmap approval. Each stage should preserve the existing agents, local Ollama path and MCP stdio contracts.

| Stage | Work | Exit evidence |
| --- | --- | --- |
| 0. Freeze the baseline | Archive current FAST/FULL and standalone MCP behavior, active prompts and existing verification artifacts. Finalize dataset, labels and evaluation thresholds with the supervisor. | Reproducible baseline configuration and frozen paper/task manifest. |
| 1. Strengthen lexical and provenance | Add document-scoped queries inside the index layer and field-oriented retrieval with deterministic packing. Trace candidates and excerpts. Keep the shipped selection configurable for comparisons. | Scope regression covers multiple versions, citations round-trip to page slices, and matched-budget retrieval scores identify remaining gaps. |
| 2. Test semantic and hybrid | Reuse the local embedding client, model-versioned SQLite vectors and exact scan. Compare semantic and rank fusion to improved lexical retrieval. | Adopt the simplest strategy that meets held-out relevance and latency gates. Leave hybrid optional when it fails to earn its cost. |
| 3. Improve prompts and outputs | Keep strategy variants in Markdown. Add claim-level structured extraction and span references, with explicit unknown values and controlled examples. Test prompts on identical evidence. | Reproducible field-completeness and factual-support measurements with stable reports and legacy MCP results. |
| 4. Validate and correct | Add deterministic citation checks, claim support judgments and a bounded gap-driven request path. Evaluate checks alone, revision alone and retrieval plus revision. | Corrupt references and unsupported values are detected. Tests cover no-gap, recoverable, unanswerable, repeated-query and timeout paths. Held-out traces and quality/cost results show whether to enable the loop. |
| 5. Verify integration | Run the existing suite plus targeted regressions for new behavior. Run real Streamlit and MCP smoke checks with the same pinned PDF, compare source hashes and replay saved outputs. Document chosen modes and publish evaluation results. | Evidence chain from query to shipped result is reproducible, and the six existing MCP tool contracts still work. |

Reuse [prior execution evidence](../evaluation/EXECUTION_REPORT.md) for historical comparisons and [the evaluation plan](RAG_EVALUATION_PLAN.md) for new measurements. Defer OCR, specialized table parsing or broader infrastructure until measured evidence gaps warrant them.

## Final verdict

1. **Already RAG?** Yes for the full FAST workflow. The existing orchestrator performs indexed lexical retrieval before the Summary and Questions agents generate output. FULL and standalone FAST summary/questions use different context paths. [Assessment](RAG_ARCHITECTURE_ASSESSMENT.md)
2. **Already Agentic RAG?** No under the evidence-driven criterion. The model generates literature queries, but neither source gaps nor validation outcomes trigger further manuscript retrieval or revision. [Gap analysis](AGENTIC_RAG_GAP_ANALYSIS.md)
3. **What is missing?** Task-aware retrieval in the analysis path, claim-level citations and scientific validation, bounded gap-driven retrieval, and held-out measurements. Semantic retrieval already exists separately. Hybrid remains an experimental candidate. [Target architecture](TARGET_ARCHITECTURE.md)
4. **What comes next?** Freeze the evaluation baseline, then implement document-scoped lexical retrieval and traceable context packing after approval. Use measured retrieval gaps to decide whether to adopt the existing semantic capability or hybrid ranking.
5. **How do we demonstrate improvement?** Compare paired full-paper arms with fixed documents, models and budgets, blind adjudication, and separate retrieval, prompting and correction ablations. Report effect sizes, uncertainty, exact citation resolution and support, latency and traces for resolved and unresolved gaps. [Evaluation plan](RAG_EVALUATION_PLAN.md)
