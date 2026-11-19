import pytest

from evaluation.retrieval_ablation import retrieval_metrics


def test_retrieval_metrics_cover_multi_paper_targets():
    result = retrieval_metrics(
        [10, 11, 12, 13],
        [{10, 20}, {13}],
        cutoff=4,
    )

    assert result["target_ranks"] == [1, 4]
    assert result["target_recall"] == 1
    assert result["precision_at_k"] == pytest.approx(0.5)
    assert result["recall_at_k"] == pytest.approx(2 / 3)
    assert result["mrr_targets"] == pytest.approx(0.625)


def test_retrieval_metrics_do_not_count_unanswerable_questions_as_zero_recall():
    result = retrieval_metrics([10, 11], [], cutoff=2)

    assert result["target_ranks"] == []
    assert result["precision_at_k"] is None
    assert result["recall_at_k"] is None
    assert result["mrr_targets"] is None
