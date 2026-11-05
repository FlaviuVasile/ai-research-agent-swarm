import asyncio
import json
import sqlite3
import time
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pymupdf
import pytest

from orchestrator import Orchestrator
from research_swarm.cache import ResponseCache
from research_swarm.config import Settings
from research_swarm.llm import LLM
from research_swarm.models import Questions, ResearchQuestion, Relevance
from research_swarm.providers import OllamaProvider, OpenAIProvider, ProviderError


def questions():
    return Questions(questions=[ResearchQuestion(question="How do platforms compare?", why_it_matters="Timing matters.",
        evidence="One synthetic workload.", kind="Inferred research opportunity", search_query="automotive RTOS")])


def document():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Automotive OS timing study. One workload was evaluated. More workloads are needed.")
        return doc.tobytes()


def local_tags(digest="sha256:local-weights"):
    return {"models": [{"name": "llama3.2:latest", "size": 2000000000, "digest": digest,
                         "details": {"format": "gguf"}}]}


def server(responses, *, tags=None, info=None, chat_status=200):
    queue = list(responses)

    async def send(client, request, **kwargs):
        assert request.url.host == "127.0.0.1"  # No remote endpoint, even with real keys present.
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags if tags is not None else local_tags(), request=request)
        if request.url.path == "/api/show":
            return httpx.Response(200, json=info if info is not None else {"details": {"format": "gguf"}}, request=request)
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["stream"] is False and body["options"]["num_ctx"] in (4096,8192)
        content = queue.pop(0)
        return httpx.Response(chat_status, json={"done": True, "message": {"content": content}}, request=request)
    return send


def test_default_is_local_even_with_old_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "paid-model")
    for name in ("LLM_PROVIDER", "ALLOW_PAID_API", "OLLAMA_MODEL", "LOCAL_TEST_MODE", "CHUNK_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    with patch("research_swarm.config.dotenv_values", return_value={}):
        settings = Settings.from_env()
    assert settings.provider == "ollama" and settings.model == "llama3.2:latest"
    assert not settings.allow_paid_api
    assert isinstance(LLM("gpt-4.1-mini").provider, OllamaProvider)


@pytest.mark.parametrize("provider,allowed", [("ollama", False), ("ollama", True), ("openai", False)])
def test_paid_provider_requires_both_opt_ins(provider, allowed):
    settings = Settings(provider=provider, allow_paid_api=allowed)
    with patch("httpx.AsyncClient.send", AsyncMock(side_effect=AssertionError("Network forbidden"))):
        with pytest.raises(ProviderError, match="disabled"):
            asyncio.run(OpenAIProvider(settings).generate("Summary", "Summarize", "text", None))


def test_full_ollama_workflow_without_key_and_cached_rerun(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(cache_dir=tmp_path / "cache")
    literature = SimpleNamespace(search=AsyncMock(return_value=[SimpleNamespace(
        title="Timing evaluation", authors=("Example",), year=2024, doi=None, id="https://openalex.org/W1")]))
    results = ["# Summary\nSynthetic workload study.", questions().model_dump_json(),
               Relevance(explanation="Title-only timing relevance.").model_dump_json()]
    with patch("httpx.AsyncClient.send", autospec=True, side_effect=server(results)) as requests:
        first = asyncio.run(Orchestrator(settings, tmp_path / "first", openalex=literature).run(document()))
        second = asyncio.run(Orchestrator(settings, tmp_path / "second", openalex=literature).run(document()))
    assert len(first.files) == 4 and first.files == second.files
    chat_calls = [call for call in requests.call_args_list if call.args[1].url.path == "/api/chat"]
    assert len(chat_calls) == 3  # Second run uses validated persistent LLM cache.
    inspections = [call for call in requests.call_args_list if call.args[1].url.path == "/api/tags"]
    assert len(inspections) == 2  # One model inspection per controller, including summary overrides.
    assert "Example" in first.files["literature_review.md"]
    assert literature.search.await_count == 2  # Literature remains fresh; no cached fake citations.
    for name, content in first.files.items():
        assert (tmp_path / "first" / name).read_text(encoding="utf-8") == content


def test_free_test_mode_is_fully_offline_and_labelled(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(local_test_mode=True, cache_dir=tmp_path / "cache")
    with patch("httpx.AsyncClient.send", AsyncMock(side_effect=AssertionError("Network forbidden"))):
        forbidden = SimpleNamespace(run=AsyncMock(side_effect=AssertionError("Injected LLM forbidden")),
                                    search=AsyncMock(side_effect=AssertionError("Injected search forbidden")))
        result = asyncio.run(Orchestrator(settings, tmp_path / "reports", llm=forbidden, openalex=forbidden).run(document()))
    assert len(result.files) == 4 and "TEST MODE" in result.warnings[0]
    assert all("TEST MODE" in content for name, content in result.files.items() if name.endswith(".md"))


@pytest.mark.parametrize("url", ["https://ollama.com", "http://example.com", "http://localhost@evil.test", "http://127.0.0.1/path"])
def test_remote_ollama_endpoints_are_rejected(url):
    with pytest.raises(ValueError, match="loopback"):
        Settings(ollama_url=url)


def test_cloud_model_name_is_blocked_without_network():
    with patch("httpx.AsyncClient.send", AsyncMock(side_effect=AssertionError("Network forbidden"))):
        with pytest.raises(ProviderError, match="Cloud"):
            asyncio.run(LLM(settings=Settings(model="example:cloud")).run("Summary", "Summarize", "text"))


@pytest.mark.parametrize("metadata", [{"remote_host": "https://ollama.com"}, {"remote_model": "cloud-name"},
                                      {"size": 0}, {"details": {"format": "remote"}}])
def test_remote_model_metadata_is_blocked(metadata):
    tags = local_tags()
    tags["models"][0].update(metadata)
    with patch("httpx.AsyncClient.send", autospec=True, side_effect=server([], tags=tags)):
        with pytest.raises(ProviderError, match="local GGUF"):
            asyncio.run(OllamaProvider(Settings()).identity())


def test_remote_show_metadata_is_blocked():
    with patch("httpx.AsyncClient.send", autospec=True, side_effect=server([], info={"remote_host": "cloud"})):
        with pytest.raises(ProviderError, match="Remote"):
            asyncio.run(OllamaProvider(Settings()).identity())


def test_missing_model_is_actionable():
    with patch("httpx.AsyncClient.send", autospec=True, side_effect=server([], tags={"models": []})):
        with pytest.raises(ProviderError, match="ollama pull"):
            asyncio.run(OllamaProvider(Settings()).identity())


@pytest.mark.parametrize("content,schema", [("", None), ("not JSON", Questions), ("{}", Questions)])
def test_invalid_ollama_output_is_not_cached(tmp_path, content, schema):
    settings = Settings(cache_dir=tmp_path)
    with patch("httpx.AsyncClient.send", autospec=True, side_effect=server([content])):
        with pytest.raises(ValueError):
            asyncio.run(LLM(settings=settings).run("Summary", "Instructions", "Evidence", schema))
    with sqlite3.connect(tmp_path / "responses.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM responses").fetchone()[0] == 0


def test_cache_keys_cover_prompt_schema_model_and_generation_settings(tmp_path):
    fake = SimpleNamespace(authorize=lambda: None, identity=AsyncMock(return_value="local:digest1"),
                           generate=AsyncMock(return_value="Valid output"))
    settings = Settings(cache_dir=tmp_path)
    llm = LLM(settings=settings, provider=fake)
    for evidence, instruction in [("a", "i"), ("a", "i"), ("b", "i"), ("a", "new")]:
        asyncio.run(llm.run("Summary", instruction, evidence))
    assert fake.generate.await_count == 3
    fake.identity.return_value = "local:digest2"
    asyncio.run(llm.run("Summary", "i", "a"))
    asyncio.run(LLM(settings=replace(settings, max_output_tokens=1500), provider=fake).run("Summary", "i", "a"))
    assert fake.generate.await_count == 5
    fake.generate.return_value = Relevance(explanation="Valid structured output")
    asyncio.run(llm.run("Summary", "i", "a", Relevance))
    assert fake.generate.await_count == 6


def test_cache_disabled_and_corrupt_entries(tmp_path):
    fake = SimpleNamespace(authorize=lambda: None, identity=AsyncMock(return_value="fixture"),
                           generate=AsyncMock(return_value=Relevance(explanation="Valid")))
    settings = Settings(cache_dir=tmp_path)
    llm = LLM(settings=settings, provider=fake)
    asyncio.run(llm.run("Relevance", "i", "e", Relevance))
    with sqlite3.connect(tmp_path / "responses.sqlite3") as db:
        db.execute("UPDATE responses SET output = '{}' ")
    asyncio.run(llm.run("Relevance", "i", "e", Relevance))
    assert fake.generate.await_count == 2
    uncached = LLM(settings=replace(settings, cache_enabled=False), provider=fake)
    asyncio.run(uncached.run("Relevance", "i", "e", Relevance))
    asyncio.run(uncached.run("Relevance", "i", "e", Relevance))
    assert fake.generate.await_count == 4


def test_cache_expiry_and_unavailable_directory(tmp_path):
    cache = ResponseCache(tmp_path, 10)
    cache.put("key", "output")
    assert cache.get("key") == "output"
    with patch("research_swarm.cache.time.time", return_value=time.time() + 20):
        assert cache.get("key") is None
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    cache = ResponseCache(blocked, 10)
    assert cache.get("key") is None
    cache.put("key", "output")  # Cache failure must not destroy successful analysis.


def test_cached_paid_output_cannot_bypass_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake = SimpleNamespace(authorize=lambda: None, identity=AsyncMock(return_value="openai:https://api.openai.com/v1:gpt-4.1-mini"),
                           generate=AsyncMock(return_value="Cached output"))
    settings = Settings(provider="openai", model="gpt-4.1-mini", cache_dir=tmp_path)
    asyncio.run(LLM(settings=settings, provider=fake).run("Summary", "i", "e"))
    with pytest.raises(ProviderError, match="disabled"):
        asyncio.run(LLM(settings=settings).run("Summary", "i", "e"))


@pytest.mark.parametrize("name,value", [("ALLOW_PAID_API", "yes"), ("LLM_PROVIDER", "unknown"),
                                       ("LOCAL_TEST_MODE", "maybe"), ("LLM_CACHE_ENABLED", "1")])
def test_bad_environment_is_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with patch("research_swarm.config.dotenv_values", return_value={}), pytest.raises(ValueError):
        Settings.from_env()


def test_test_mode_blocks_direct_paid_calls():
    settings = Settings(provider="openai", allow_paid_api=True, local_test_mode=True)
    with pytest.raises(ProviderError, match="disabled"):
        asyncio.run(OpenAIProvider(settings).generate("Summary", "i", "e", None))


def test_local_workflow_without_optional_sdk_or_tokenizer(tmp_path):
    script = '''
import sys, importlib.abc, asyncio
from pathlib import Path
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'agents', 'openai', 'tiktoken'}:
            raise ImportError('Optional dependency forbidden in offline test')
sys.meta_path.insert(0, BlockOptional())
import pymupdf
from orchestrator import Orchestrator
from research_swarm.config import Settings
with pymupdf.open() as doc:
    page = doc.new_page()
    page.insert_text((72, 72), 'Synthetic local research workflow test.')
    data = doc.tobytes()
result = asyncio.run(Orchestrator(Settings(local_test_mode=True, cache_enabled=False), Path(sys.argv[1])).run(data))
assert len(result.files) == 4
assert not any(name in sys.modules for name in ('agents', 'openai', 'tiktoken'))
'''
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "offline")],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_ollama_timeout_has_actionable_safe_message():
    provider = OllamaProvider(Settings())
    provider._identity = "installed-local-model"
    with patch("httpx.AsyncClient.post", AsyncMock(side_effect=httpx.ReadTimeout("secret"))):
        with pytest.raises(ProviderError, match="timed out") as exc:
            asyncio.run(provider.generate("Summary", "i", "e", None))
    assert "secret" not in str(exc.value)


def test_truncated_ollama_output_is_rejected():
    provider = OllamaProvider(Settings())
    provider._identity = "installed-local-model"
    response = httpx.Response(200, json={"done": True, "done_reason": "length", "message": {"content": "partial"}},
                              request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"))
    with patch("httpx.AsyncClient.post", AsyncMock(return_value=response)):
        with pytest.raises(ProviderError, match="incomplete"):
            asyncio.run(provider.generate("Summary", "i", "e", None))


def test_ollama_keeps_model_warm_and_reports_prompt_timing():
    from research_swarm.telemetry import observe
    provider = OllamaProvider(Settings())
    provider._identity = "local-model"
    response = httpx.Response(200, json={"done": True, "message": {"content": "Summary"},
        "prompt_eval_duration": 12345}, request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"))
    events = []
    with observe(lambda kind, **fields: events.append((kind, fields))):
        # Nonstreamed HTTP fixture; test metric dispatch independently of observation.
        with patch("research_swarm.providers.observed", return_value=False), patch(
                "httpx.AsyncClient.post", AsyncMock(return_value=response)) as post:
            assert asyncio.run(provider.generate("Summary", "i", "e", None)) == "Summary"
    assert post.await_args.kwargs["json"]["keep_alive"] == "10m"
    assert ("request_metrics", {"prompt_eval_duration": 12345}) in events


@pytest.mark.parametrize("layers", [None, 0, 99])
def test_ollama_gpu_placement_is_optional_and_http_skips_tls_setup(layers):
    provider = OllamaProvider(Settings(ollama_gpu_layers=layers))
    provider._identity = "local-model"
    response = httpx.Response(200, json={"done": True, "message": {"content": "Summary"}},
                              request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"))
    original_client = httpx.AsyncClient
    with patch.object(original_client, "post", AsyncMock(return_value=response)) as post, patch(
            "httpx.AsyncClient", wraps=original_client) as client:
        assert asyncio.run(provider.generate("Summary", "i", "e", None)) == "Summary"
    assert client.call_args.kwargs["verify"] is False
    assert client.call_args.kwargs["trust_env"] is False
    assert client.call_args.kwargs["follow_redirects"] is False
    options = post.await_args.kwargs["json"]["options"]
    if layers is None:
        assert "num_gpu" not in options
    else:
        assert options["num_gpu"] == layers
