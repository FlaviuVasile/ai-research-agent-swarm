import asyncio
from copy import deepcopy
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
import pymupdf
import pytest

from research_swarm.config import Settings
from research_swarm.jobs import ProgressRecord, start_run, snapshot, active, measurements, saved_result
from research_swarm.llm import LLM
from research_swarm.models import Questions, ResearchQuestion
from research_swarm.providers import OllamaProvider
from research_swarm.telemetry import observe, emit
from orchestrator import Orchestrator
from research_swarm.agents.summary_agent import SummaryAgent


def pdf():
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((72,72),"Synthetic automotive scheduling research. Hardware validation is future work.")
        return doc.tobytes()


def wait_done(identifier):
    deadline=time.monotonic()+10
    while active(identifier) and time.monotonic()<deadline:
        time.sleep(.01)
    assert not active(identifier)


def test_real_completed_counts_and_eta_threshold(tmp_path):
    record=ProgressRecord(tmp_path,uuid4().hex)
    record.stage("PDF Master","complete")
    record.stage("Summary Agent","running")
    record.event("summary_plan",total=10)
    for index in range(1,4):
        record.event("chunk_start",index=index)
        record.event("chunk_complete",index=index,seconds=10,cached=False)
    record.event("chunk_start",index=4)
    record.event("request_start",agent="Summary Agent")
    now=record.data["request"]["started_at"]+3
    measured=measurements(record.data,now=now)
    assert measured["completed_stages"]==1
    assert record.data["summary"]["completed"]==3 and record.data["summary"]["current"]==4
    assert measured["chunk_eta"]==pytest.approx(67)
    record.event("reduction_plan",round=1,total=2)
    assert measurements(record.data)["chunk_eta"] is None


def test_eta_waits_for_comparable_non_cached_observations(tmp_path):
    record=ProgressRecord(tmp_path,uuid4().hex)
    record.event("summary_plan",total=10)
    for index,duration in enumerate([1,1],1):
        record.event("chunk_complete",index=index,seconds=duration,cached=False)
    assert measurements(record.data)["chunk_eta"] is None
    record.event("chunk_complete",index=3,seconds=.001,cached=True)
    assert len(record.data["summary"]["durations"])==2
    record.event("chunk_complete",index=4,seconds=100,cached=False)
    assert measurements(record.data)["chunk_eta"] is None


def test_stall_measures_last_actual_response_and_freezes_on_failure(tmp_path):
    record=ProgressRecord(tmp_path,uuid4().hex)
    record.event("request_start",agent="Summary Agent")
    started=record.data["request"]["started_at"]
    assert measurements(record.data,now=started+61)["stalled"]
    with patch("research_swarm.jobs.time.time",return_value=started+60):
        record.event("response",characters=5)
    assert not measurements(record.data,now=started+61)["stalled"]
    assert record.data["request"]["characters"]==5
    record.finish("failed","safe failure")
    assert not measurements(record.data,now=started+1000)["stalled"]
    frozen=measurements(record.data,now=started+1000)["elapsed"]
    assert measurements(record.data,now=started+2000)["elapsed"]==frozen


def test_checkpoint_survives_lost_worker_and_never_claims_completion(tmp_path):
    identifier=uuid4().hex
    directory=tmp_path/"output"/identifier
    record=ProgressRecord(directory,identifier)
    record.stage("PDF Master","complete")
    record.stage("Summary Agent","running")
    record.event("summary_plan",total=40)
    record.event("chunk_complete",index=11,seconds=10,cached=False)
    record.event("chunk_start",index=12)
    state=snapshot(tmp_path,identifier)
    assert state["state"]=="interrupted"
    assert state["summary"]["completed"]==11 and state["summary"]["current"]==12
    assert state["stages"]["Summary Agent"]=="failed"
    assert snapshot(tmp_path,identifier)["finished_at"]==state["finished_at"]
    assert json.loads((directory/"progress.json").read_text())["state"]=="interrupted"


def test_background_slow_llm_does_not_restart_on_attachment(tmp_path):
    started=threading.Event()
    release=threading.Event()
    calls=[]
    class SlowProvider:
        def authorize(self): pass
        async def identity(self): return "local-fixture"
        async def generate(self,name,instructions,evidence,output_type):
            calls.append(name)
            if name=="Summary Agent":
                started.set()
                emit("response",characters=4)
                while not release.is_set():
                    await asyncio.sleep(.01)
                return "# Summary\nSynthetic findings."
            return Questions(questions=[ResearchQuestion(question="What remains untested?",why_it_matters="Validity.",
                evidence="Synthetic fixture.",kind="Inferred research opportunity",search_query="validation")])
    settings=Settings(cache_enabled=False)
    def factory(settings,directory):
        return Orchestrator(settings,directory,llm=LLM(settings=settings,provider=SlowProvider()),
                            openalex=SimpleNamespace(search=lambda *args: asyncio.sleep(0,result=[])))
    identifier=uuid4().hex
    try:
        before=time.monotonic()
        start_run(tmp_path,identifier,settings,pdf(),factory)
        assert time.monotonic()-before<2
        assert started.wait(5)
        first=snapshot(tmp_path,identifier)
        assert first["state"]=="running" and first["summary"]["completed"]==0
        assert first["summary"]["current"]==1
        assert first["request"]["characters"]==4
        start_run(tmp_path,identifier,settings,pdf(),factory)
        assert len(calls)==1
        assert snapshot(tmp_path,identifier)["summary"]["completed"]==0
    finally:
        release.set()
        wait_done(identifier)
    final=snapshot(tmp_path,identifier)
    assert final["state"]=="completed" and final["summary"]["completed"]==1
    assert len(saved_result(tmp_path,identifier).files)==4
    with pytest.raises(ValueError,match="already exists"):
        start_run(tmp_path,identifier,settings,pdf(),factory)


def test_streamed_response_events_arrive_before_request_completion():
    received=[]
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"message":{"content":"Hello "},"done":false}\n'
            assert any(kind=="response" for kind,_ in received)
            yield b'{"message":{"content":"world"},"done":false}\n'
            yield b'{"message":{"content":""},"done":true,"eval_count":2}\n'
    async def send(client,request,**kwargs):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200,stream=Stream(),request=request)
    provider=OllamaProvider(Settings())
    provider._identity="installed-local-model"
    with observe(lambda kind,**fields:received.append((kind,fields))),patch("httpx.AsyncClient.send",send):
        output=asyncio.run(provider.generate("Summary Agent","Summarize","Evidence",None))
    assert output=="Hello world"
    assert sum(fields["characters"] for kind,fields in received if kind=="response")==11


def test_failed_chunk_is_not_counted_as_completed(tmp_path):
    record=ProgressRecord(tmp_path,uuid4().hex)
    class FailingLLM:
        async def run(self,*args):
            raise ValueError("Synthetic model failure")
    with observe(record.event),pytest.raises(ValueError):
        asyncio.run(SummaryAgent(FailingLLM(),Settings()).summarize("PDF evidence"))
    assert record.data["summary"]["total"]==1
    assert record.data["summary"]["completed"]==0
    assert record.data["summary"]["current"]==1


def test_checkpoint_failure_is_visible_without_aborting_analysis(tmp_path):
    record=ProgressRecord(tmp_path,uuid4().hex)
    with patch("research_swarm.jobs.atomic_json",side_effect=PermissionError("write blocked")):
        record.stage("Summary Agent","running")
    assert record.data["stages"]["Summary Agent"]=="running"
    assert "checkpoint_error" in record.data
    record.flush()
    assert "checkpoint_error" not in record.data


def test_eta_never_reports_zero_for_an_unfinished_overdue_chunk(tmp_path):
    record=ProgressRecord(tmp_path,uuid4().hex)
    record.event("summary_plan",total=4)
    for index in range(1,4):
        record.event("chunk_complete",index=index,seconds=10,cached=False)
    record.event("chunk_start",index=4)
    record.event("request_start",agent="Summary Agent")
    assert measurements(record.data,now=record.data["request"]["started_at"]+15)["chunk_eta"] is None
