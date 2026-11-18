# Agentic RAG gap analysis

## Runtime classification

Conventional RAG conditions generation on evidence fetched at runtime from a retrievable source. The FAST Orchestrator meets that definition through FTS5 and selected PDF passages. FULL and standalone FAST summary/questions are source-conditioned processing without ranked corpus retrieval. The literature stage is a narrower retrieval-augmented metadata task: model-generated search strings drive OpenAlex queries, then titles condition relevance assessments. [Orchestrator](../orchestrator.py), [selector](../research_swarm/summary_work.py), [service](../research_swarm/service.py), [literature agent](../agents/literature_agent.py)

For this project's Agentic RAG acceptance criterion, a model-informed decision based on the current evidence or a validation result must be able to change what the system retrieves next. The trace should show an identified gap, a scoped follow-up request, new evidence and a revised or explicitly unresolved outcome. The current orchestrator has no such return path. Several specialists, static reranking, transport tools and generated search queries establish useful prerequisites. The literature search runs after question generation and returns its own report. [Orchestrator](../orchestrator.py), [MCP server](../research_swarm/mcp_server.py)

| Gap | Consequence | Proposed acceptance evidence |
| --- | --- | --- |
| Fixed FAST query emphasizes automotive/system terms | Relevant methods, numerical results and limitations can miss the candidate pool, especially on other topics. The magnitude is unmeasured. | Replay the shipped selector and compare field-aware lexical, semantic and hybrid at matched budgets on labelled spans. |
| Publication ranking precedes document filtering | Other PDF versions under the same publication can consume top slots before filtering. | Identical-title or version fixture demonstrates filtering at source before ranking and limiting. |
| Retrieval labels and model claims have separate lifetimes | A valid excerpt manifest can coexist with fabricated, incomplete or misattributed claims. | Exercise wrong page, offsets, units, direction, and missing qualifiers. Resolve citations against the actual prompt and source. |
| No evidence sufficiency decision or revision | Retrieval gaps persist into summaries or questions, even when another passage could resolve them. | Show sufficient-input, recoverable-gap and unanswerable traces with bounded calls and explicit outcomes. |
| FAST differs across MCP entry points | Clients can receive variable coverage under the same mode label. | Preserve existing contracts and test any opt-in indexed capability via real stdio and saved-result reload. |
| Limited outcome evaluation | Prior abstract scores cannot establish the value of retrieval or correction. | Paired full-paper evaluation with held-out labels, reviewer agreement and item-level error analysis. |

## Should agents retrieve independently?

Let existing specialists independently identify a missing field or unsupported claim and propose a follow-up query. Keep the actual retrieval and budgets in the shared controller. A summary may request the comparison baseline for a reported improvement, and the questions agent may request the limitations section before labelling a gap explicit. Use typed requests with field/claim ID, reason and query. Resolve the authorized document scope on the controller side. Batch and deduplicate requests across specialists, record attempted queries and enforce shared deadlines. Keep OpenAlex discovery separate from manuscript verification because titles cannot resolve manuscript findings.

Adopt the follow-up path only if the correction ablation recovers correctly supported evidence with acceptable cost. Terminate on sufficient evidence, no new hits, repeated queries, exhausted budgets or errors, and persist unresolved fields. See the [target design](TARGET_ARCHITECTURE.md) and [experiment](RAG_EVALUATION_PLAN.md).
