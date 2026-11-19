from research_swarm.corpus.spans import query_terms, ranked_spans


def _row(page, title, text, identifier):
    return {
        "id": identifier,
        "document_id": "paper",
        "page": page,
        "start_char": 0,
        "title": title,
        "text": text,
    }


def test_query_terms_normalize_scientific_morphology_and_hyphenation():
    assert query_terms("recurrent convolutional fine-tuning") == query_terms(
        "recurrence convolutions fine tuned"
    )


def test_false_premise_prefers_explicit_correction_over_related_comparison():
    question = "Why did the Transformer use recurrent layers to achieve its WMT results?"
    related = _row(
        10,
        "Attention Is All You Need",
        "For translation tasks, the Transformer can be trained significantly faster "
        "than architectures based on recurrent or convolutional layers.",
        10,
    )
    correction = _row(
        1,
        "Attention Is All You Need",
        "We propose a new simple network architecture, the Transformer, based solely "
        "on attention mechanisms, dispensing with recurrence and convolutions entirely.",
        1,
    )

    ranked = ranked_spans(question, [related, correction])

    assert ranked
    assert ranked[0][0]["page"] == 1
    assert "dispensing with recurrence" in ranked[0][0]["text"][ranked[0][1] : ranked[0][2]]


def test_motivation_question_prefers_stated_feasibility_issue_over_future_work():
    question = "What difficulty with full fine-tuning motivates LoRA?"
    future_work = _row(
        12,
        "LoRA: Low-Rank Adaptation of Large Language Models",
        "The mechanism behind fine-tuning or LoRA is far from clear.",
        12,
    )
    motivation = _row(
        1,
        "LoRA: Low-Rank Adaptation of Large Language Models",
        "As we pre-train larger models, full fine-tuning, which retrains all model "
        "parameters, becomes less feasible.",
        1,
    )

    ranked = ranked_spans(question, [future_work, motivation])

    assert ranked
    assert ranked[0][0]["page"] == 1
    assert "becomes less feasible" in ranked[0][0]["text"][ranked[0][1] : ranked[0][2]]
