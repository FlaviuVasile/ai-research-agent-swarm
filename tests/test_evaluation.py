import hashlib
import json
from pathlib import Path

import pytest

from evaluation.score import score
from evaluation.compare_repeat import compare


def test_failed_experiments_persist_results_and_raise(tmp_path,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import evaluation.run as experiment
    from research_swarm.config import Settings
    fake = SimpleNamespace(provider=SimpleNamespace(identity=AsyncMock(return_value="test-identity")),
        run=AsyncMock(side_effect=ValueError("deliberate failure")))
    monkeypatch.setattr(experiment,"LLM",lambda **kwargs:fake)
    monkeypatch.setattr(Settings,"from_env",classmethod(lambda cls:Settings()))
    output=tmp_path / "failed.json"
    with pytest.raises(RuntimeError,match="27 experiment operations failed"):
        asyncio.run(experiment.run(output))
    rows=json.loads(output.read_text(encoding="utf-8"))["rows"]
    assert len(rows)==27 and all(not row["valid"] for row in rows)


def test_scoring_rejects_reviews_for_different_outputs(tmp_path):
    results = tmp_path / "results.json"
    results.write_text('{}')
    with pytest.raises(ValueError,match="exact experiment"):
        score(results,{"results_sha256":"wrong"},{})


def test_saved_experiment_is_paired_and_metrics_reproduce():
    folder = Path(__file__).resolve().parents[1] / "evaluation"
    results = folder / "results" / "local-2026-11-17.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    assert len(data["rows"]) == 27
    assert not data["cache_enabled"] and not data["journal_enabled"]
    for paper in {row["paper"] for row in data["rows"]}:
        assert len({row["evidence_sha256"] for row in data["rows"] if row["paper"] == paper}) == 1
    metrics = score(results,
        json.loads((folder / "results" / "local-2026-11-17-reviews.json").read_text()),
        json.loads((folder / "rubric.json").read_text()))
    assert metrics == json.loads((folder / "results" / "local-2026-11-17-metrics.json").read_text())
    assert metrics["fields/summary"]["reference_recall"] == 11/18
    assert metrics["evidence/questions"]["category_correct"] == 2


def test_repeat_review_requires_exact_output_equality(tmp_path):
    rows = [dict(paper=str(paper),variant=variant,operation=operation,evidence_sha256="same",
        valid=True,output="reviewed output") for paper in range(3) for variant in ("baseline","fields","evidence")
        for operation in ("summary","questions","literature")]
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    previous.write_text(json.dumps(dict(model="fixed",configuration={},rows=rows)))
    current.write_bytes(previous.read_bytes())
    reviews = tmp_path / "reviews.json"
    reviews.write_text(json.dumps(dict(results_sha256=hashlib.sha256(previous.read_bytes()).hexdigest(),rows=[])))
    output = tmp_path / "comparison.json"
    compare(previous,current,reviews,output)
    assert json.loads(output.read_text())["exact_output_matches"] == 27
    (tmp_path / "comparison-reviews.json").unlink()
    rows[0]["output"] = "different output needing fresh review"
    current.write_text(json.dumps(dict(model="fixed",configuration={},rows=rows)))
    with pytest.raises(ValueError,match="new factual review"):
        compare(previous,current,reviews,output)
    assert not (tmp_path / "comparison-reviews.json").exists()
