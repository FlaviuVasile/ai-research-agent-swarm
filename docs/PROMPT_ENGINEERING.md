# Prompt engineering

Existing baseline, fields and evidence templates live under [prompts](../prompts/README.md). Production loads Markdown template text through prompt_loader.py. QA adds a short baseline prompt, an evidence-first prompt that can request one follow-up query, a revision prompt, and a separate semantic checker prompt.

Both QA variants receive a question and budgeted excerpts. Their schema requires at most four candidate claims with chunk IDs and quotations. An empty list expresses missing answer evidence. The evidence-first prompt additionally asks for atomic claims, scientific qualifiers and a follow-up query when a gap remains. The LLM cache keys include instructions, evidence, output schema and model identity. QA records a hash of its loaded workflow prompts in the response.
