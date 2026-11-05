import asyncio
from dataclasses import replace
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import time

import pymupdf
import pytest

from research_swarm.agents.summary_agent import SummaryAgent
from research_swarm.budgets import BudgetExceeded,timeboxed
from research_swarm.config import Settings
from research_swarm.llm import LLM,chunks
from research_swarm.summary_work import SummaryJournal,select_corpus_evidence


def test_fast_is_one_bounded_call_and_full_is_map_plus_one_synthesis():
    text="Scheduling evidence and limitations. "*500
    fast=SimpleNamespace(run=AsyncMock(return_value="Evidence is limited."))
    summary,_=asyncio.run(SummaryAgent(fast,Settings(max_chunks=1)).summarize(text))
    assert fast.run.await_count==1 and "selected evidence only" in summary
    assert len(fast.run.await_args.args[2].encode())<=2000
    full=SimpleNamespace(run=AsyncMock(return_value="Evidence is limited."))
    config=Settings(research_mode="FULL_RESEARCH_MODE",max_chunks=99)
    summary,_=asyncio.run(SummaryAgent(full,config).summarize(text))
    assert full.run.await_count==len(chunks(text,2000))+1
    assert all(len(call.args[2].encode())<=2000 for call in full.run.await_args_list)
    assert "FULL_RESEARCH_MODE" in summary


def test_failed_full_run_resumes_from_durable_steps_without_llm_cache(tmp_path):
    config=Settings(research_mode="FULL_RESEARCH_MODE",cache_enabled=False)
    text="Source evidence. "*500
    journal=SummaryJournal(tmp_path/"research"/"corpus.sqlite3")
    first=SimpleNamespace(run=AsyncMock(side_effect=["First note.","Second note.",ValueError("timeout")]))
    with pytest.raises(ValueError,match="timeout"):
        asyncio.run(SummaryAgent(first,config,journal).summarize(text))
    with journal.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM summary_steps").fetchone()[0]==2
    next_llm=SimpleNamespace(run=AsyncMock(return_value="Recovered note."))
    asyncio.run(SummaryAgent(next_llm,config,journal).summarize(text))
    assert next_llm.run.await_count==len(chunks(text,2000))-2+1
    with journal.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM summary_attempts WHERE status='failed'").fetchone()[0]==1


def test_request_budget_cancels_slow_provider():
    provider=SimpleNamespace(authorize=lambda:None,identity=AsyncMock(return_value="local-fixture"),
                            generate=lambda *args:asyncio.sleep(5,result="too late"))
    started=time.monotonic()
    with pytest.raises(BudgetExceeded,match="LLM request"):
        asyncio.run(LLM(settings=Settings(llm_timeout=1,cache_enabled=False),provider=provider).run("Summary Agent","i","e"))
    assert time.monotonic()-started<3


def test_document_budget_keeps_completed_steps(tmp_path):
    journal=SummaryJournal(tmp_path/"research"/"corpus.sqlite3")
    async def slow(*args):
        await asyncio.sleep(.4)
        return "Saved evidence note."
    config=Settings(research_mode="FULL_RESEARCH_MODE",document_timeout=1)
    with pytest.raises(BudgetExceeded):
        asyncio.run(SummaryAgent(SimpleNamespace(run=slow),config,journal).summarize("Evidence. "*800))
    with journal.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM summary_steps").fetchone()[0]>=1


def test_wall_clock_jump_does_not_extend_a_deadline():
    clock=[1000.]
    async def paused_machine():
        await asyncio.sleep(.01)
        clock[0]+=18000
        await asyncio.sleep(.01)
        return "late"
    with patch("research_swarm.budgets.time.time",side_effect=lambda:clock[0]):
        with pytest.raises(BudgetExceeded):
            asyncio.run(timeboxed(paused_machine(),90,"LLM request"))


def test_fast_evidence_reuses_corpus_and_keeps_exact_references(tmp_path):
    with pymupdf.open() as pdf:
        for index in range(3):
            page=pdf.new_page()
            page.insert_text((72,72),f"1 Architecture\nQNX scheduling and functional safety evidence on page {index+1}.")
        data=pdf.tobytes()
    config=Settings(research_db=tmp_path/"research"/"corpus.sqlite3")
    journal=SummaryJournal(config.research_db)
    path=tmp_path/"selection.json"
    first=select_corpus_evidence(data,config,journal,path)
    second=select_corpus_evidence(data,config,journal,path)
    assert first==second and len(first.encode())<=2000
    manifest=json.loads(path.read_text())
    assert manifest["selections"]
    with journal.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]==1
    for selected in manifest["selections"]:
        hit=journal.store.evidence(selected["evidence_id"])
        assert hit["page"]==selected["page"] and hit["sha256"]==selected["sha256"]


@pytest.mark.parametrize("text", ["plain text " * 100, "???? a" * 200, "a????" * 101])
@pytest.mark.parametrize("limit", [4, 5, 7, 31, 2000])
def test_chunk_boundaries_preserve_greedy_utf8_behavior(text, limit):
    expected = []
    current = ""
    for char in text:
        if len((current + char).encode("utf-8")) > limit:
            expected.append(current)
            current = ""
        current += char
    if current:
        expected.append(current)
    assert chunks(text, limit) == expected
