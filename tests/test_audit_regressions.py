import asyncio
import json
from pathlib import Path

import pytest

from research_swarm.config import Settings
from research_swarm.service import ResearchService
from research_swarm.budgets import BudgetExceeded
from research_swarm.jobs import saved_result


def test_mcp_operation_document_budget(tmp_path):
    service = ResearchService(tmp_path,tmp_path,Settings(document_timeout=1,local_test_mode=True))
    with pytest.raises(BudgetExceeded):
        service._run_async(asyncio.sleep(5))


def test_saved_metadata_is_validated(tmp_path):
    with pytest.raises(ValueError,match="identifier"):
        saved_result(tmp_path,"../outside")
    directory = tmp_path / "output" / ("a"*32)
    directory.mkdir(parents=True)
    (directory / "result.json").write_text(json.dumps({"files":1}),encoding="utf-8")
    with pytest.raises(ValueError,match="metadata"):
        saved_result(tmp_path,"a"*32)


def test_windows_device_and_stream_paths_are_rejected_before_open(tmp_path, monkeypatch):
    service = ResearchService(tmp_path,tmp_path,Settings(local_test_mode=True))
    def forbidden(*args, **kwargs):
        raise AssertionError("A reserved path must not be opened.")
    monkeypatch.setattr(Path,"open",forbidden)
    for name in ("CON.pdf","NUL.pdf","COM1.pdf","paper.txt:stream.pdf"):
        with pytest.raises(ValueError,match="Reserved"):
            service.read_pdf(name)
