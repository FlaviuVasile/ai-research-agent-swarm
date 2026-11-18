# Agent prompts

`baseline/` preserves the original production strings, including whitespace,
dynamic question limits, shared safety instructions and evidence wrappers.
`summary_legacy.md` is only for the historical response-cache lookup.
`fields/` requests field-by-field extraction; `evidence/` asks for source-first
extraction and a final consistency check without requesting hidden reasoning.
Shared support templates inherit baseline; missing core summary/question/
literature variant instructions are errors. UTF-8 BOM and CRLF are supported.

Prompts are UTF-8 Markdown text, not executable code. `${limit}`, `${evidence}`
and `${summary}` use strict single-pass substitution. A literal dollar sign
must be written `$$`. Variables inside document text are not substituted again.
Do not add YAML metadata or Markdown headings unless intended for the model.

`research_swarm.prompt_loader.load_prompt()` resolves paths from the project,
reloads files on each call and rejects missing/extra variables or unsafe names.
The summary journal includes a prompt-directory fingerprint, so prompt edits
cannot silently reuse an older journal entry. Response cache identity already
includes rendered instructions and evidence. Baseline files have regression
hashes in `tests/baseline_prompt_hashes.json`; add new variants instead of
rewriting the baseline. No prompt-loader package is required.

Set `PROMPT_VARIANT=baseline`, `fields`, or `evidence` to choose a complete
experimental family. The default `selected` uses `selection.json`: fields for
summary, evidence for questions, baseline for literature. The production selection and measured limitations are
documented in `evaluation/REPORT.md`. Shared safety and generated schema
instructions stay common across comparisons. Citation labels and JSON schemas
are generated from real source metadata and Pydantic models, not copied into
editable prose.
