from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio

import pytest

from research_swarm.prompt_loader import load_prompt, prompt_fingerprint
from research_swarm.agents.questions_agent import QuestionsAgent
from research_swarm.models import Questions, ResearchQuestion


def test_baseline_and_strict_single_pass_substitution(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert load_prompt("summary_full") == "Summarize this source chunk."
    assert load_prompt("questions", limit=3).startswith("Identify 1 to 3 concrete")
    value = "${summary} {untrusted}"
    assert value in load_prompt("questions_input", evidence=value, summary="done")
    for kwargs in ({}, {"limit": 3, "extra": 1}):
        with pytest.raises(ValueError):
            load_prompt("questions", **kwargs)
    with pytest.raises(ValueError):
        load_prompt("../safety")
    with pytest.raises(FileNotFoundError):
        load_prompt("missing")


def test_prompt_edit_is_loaded_and_fingerprinted(monkeypatch, tmp_path):
    import research_swarm.prompt_loader as loader
    (tmp_path / "baseline").mkdir()
    path = tmp_path / "baseline" / "sample.md"
    path.write_text("First ${value}", encoding="utf-8")
    monkeypatch.setattr(loader, "PROMPTS", tmp_path)
    before = prompt_fingerprint()
    assert load_prompt("sample", value="one") == "First one"
    path.write_text("Second ${value}", encoding="utf-8")
    assert load_prompt("sample", value="two") == "Second two"
    assert prompt_fingerprint() != before


def test_agent_reloads_prompt_and_schema_wrapper_invalidates_cache(monkeypatch, tmp_path):
    import shutil
    import research_swarm.prompt_loader as loader
    from research_swarm.llm import LLM
    from research_swarm.config import Settings
    from research_swarm.models import Relevance
    shutil.copytree(loader.PROMPTS,tmp_path / "prompts")
    monkeypatch.setattr(loader,"PROMPTS",tmp_path / "prompts")
    provider = SimpleNamespace(authorize=lambda:None,identity=AsyncMock(return_value="fixed"),
        generate=AsyncMock(return_value=Relevance(explanation="assessed")))
    llm = LLM(settings=Settings(cache_dir=tmp_path / "cache"),provider=provider)
    async def invoke():
        return await llm.run("Literature","instruction","title",Relevance)
    asyncio.run(invoke())
    asyncio.run(invoke())
    assert provider.generate.await_count == 1
    schema = tmp_path / "prompts" / "baseline" / "schema_instruction.md"
    schema.write_text(" Return precisely this JSON schema: ",encoding="utf-8")
    asyncio.run(invoke())
    assert provider.generate.await_count == 2
    questions = Questions(questions=[ResearchQuestion(question="Q",why_it_matters="W",evidence="E",
        kind="Inferred research opportunity",search_query="query")])
    fake = SimpleNamespace(run=AsyncMock(return_value=questions))
    agent = QuestionsAgent(fake,1)
    asyncio.run(agent.find("source","summary"))
    path = tmp_path / "prompts" / "baseline" / "questions.md"
    path.write_text("Changed instruction: return ${limit} question.",encoding="utf-8-sig")
    asyncio.run(agent.find("source","summary"))
    assert fake.run.await_args.args[1] == "Changed instruction: return 1 question."


def test_question_agent_uses_external_prompt():
    result = Questions(questions=[ResearchQuestion(question="Q", why_it_matters="W", evidence="E",
        kind="Explicit limitation", search_query="query")])
    llm = SimpleNamespace(run=AsyncMock(return_value=result))
    assert asyncio.run(QuestionsAgent(llm, 2).find("source", "summary")) == result
    args = llm.run.await_args.args
    assert args[1] == load_prompt("questions", limit=2)
    assert args[2] == load_prompt("questions_input", evidence="source", summary="summary")


def test_variants_are_distinct_and_keep_dynamic_contract():
    assert len({load_prompt("summary_common",variant=v) for v in ("baseline","fields","evidence")}) == 3
    for variant in ("baseline","fields","evidence"):
        assert "2" in load_prompt("questions",variant=variant,limit=2)
        assert load_prompt("safety",variant=variant) == load_prompt("safety")
    assert load_prompt("summary_common",variant="selected") == load_prompt("summary_common",variant="fields")
    assert load_prompt("questions",variant="selected",limit=2) == load_prompt("questions",variant="evidence",limit=2)


def test_baseline_files_match_preserved_hashes():
    import hashlib
    import json
    from research_swarm.prompt_loader import PROMPTS
    expected = json.loads(Path(__file__).with_name("baseline_prompt_hashes.json").read_text())
    for name, digest in expected.items():
        assert hashlib.sha256((PROMPTS / "baseline" / name).read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest() == digest


def test_windows_encoding_missing_variant_and_invalid_selection(monkeypatch, tmp_path):
    import research_swarm.prompt_loader as loader
    (tmp_path / "baseline").mkdir()
    (tmp_path / "fields").mkdir()
    monkeypatch.setattr(loader, "PROMPTS", tmp_path)
    path = tmp_path / "baseline" / "summary_common.md"
    path.write_bytes(b"\xef\xbb\xbfFirst\r\n${value}")
    assert load_prompt("summary_common",value="next") == "First\nnext"
    before = prompt_fingerprint()
    path.write_bytes(b"First\n${value}")
    assert prompt_fingerprint() == before
    with pytest.raises(FileNotFoundError):
        load_prompt("summary_common",variant="fields",value="next")
    (tmp_path / "selection.json").write_text('[]',encoding="utf-8")
    with pytest.raises(ValueError,match="selection"):
        load_prompt("summary_common",variant="selected",value="next")
