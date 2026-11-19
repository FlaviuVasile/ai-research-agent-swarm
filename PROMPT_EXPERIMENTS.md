# Prompt experiments

Production instructions are loaded from Markdown through `research_swarm/prompt_loader.py`. The stable legacy templates and specialist selection remain available. The new corpus QA templates are `prompts/baseline/corpus_spans.md` and `prompts/evidence/corpus_spans.md`. The latter adds a finite example, scientific scope checks, instructions for false premises, and abstention. The response fingerprints the active instructions, schema and safety template.

## Corpus QA paired comparison

Six questions, one local Llama 3.2 model, one pass per condition, common passages, and disabled response caching. The short selector and the evidence-first selector each matched **5/6 factual targets** and abstained on the clinical question. Median per-request times were 0.408 s and 0.420 s respectively. Both selected a scope-inappropriate excerpt on the LoRA conclusion item. The evidence-first prompt is the default because it specifies the intended scientific scope and output behavior. This pilot did not distinguish their empirical accuracy. [Paired outputs and citations](evaluation/results/span-benchmark-release.json)

## Specialist experiments

The alternative evidence summary separates proposed method from experimental application with a concrete optimizer example. The fields question prompt asks for a measurable follow-up the excerpts do not already answer. They ran alongside existing templates in production classes using pinned abstracts and uncached local inference. The specialist run was stopped after two complete papers and a partial third because concurrent model work was causing deadlines in corpus QA. The raw rows are retained.

For Adam, the fields summary correctly identified adaptive estimates of lower-order moments. The alternative evidence summary also did, but incorrectly described an online convex optimization framework as an evaluation dataset or benchmark. For the Transformer, the revised fields prompt elicited a new resource-constraint question, yet labelled it an explicit limitation unsupported by the abstract. The tested fields prompt also allowed abstention while the existing Questions schema requires at least one item. The evidence prompt instead asked for an architectural distinction already addressed in the abstract. The tested fields prompt was archived and the existing fields prompt restored. The title-only relevance samples also cannot support scientific comparisons. [Raw specialist outputs](evaluation/results/span-specialist-prompt-pilot.json) · [Tested question prompt](evaluation/results/span-specialist-tested-fields-questions.md)

Earlier acceptance measured explicit summary citation coverage of zero and found that advertised structured prompts alone did not prevent unsupported claims. The corpus QA improvement comes from constraining output to source spans and verifying their offsets. Legacy specialist outputs remain subject to independent citation checks. [Acceptance comparison](FINAL_EXPERIMENT_RESULTS.md)
