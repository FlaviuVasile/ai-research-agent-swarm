import asyncio
import json
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from research_swarm.config import Settings
from research_swarm.llm import chunks, SAFETY
from research_swarm.models import Questions
from research_swarm.providers import OllamaProvider, OpenAIProvider, ProviderError


NAMES = ("LLM_PROVIDER", "OLLAMA_MODEL", "CHUNK_TOKENS", "OLLAMA_CONTEXT_TOKENS",
         "LLM_MAX_OUTPUT_TOKENS", "ALLOW_PAID_API", "LOCAL_TEST_MODE", "OPENAI_API_KEY")


@pytest.fixture
def project_env(tmp_path, monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("research_swarm.config.ROOT", tmp_path)
    path = tmp_path / ".env"
    path.write_text("LLM_PROVIDER=ollama\nOLLAMA_MODEL=llama3.2\nCHUNK_TOKENS=2000\n"
                    "OLLAMA_CONTEXT_TOKENS=8192\nALLOW_PAID_API=false\n", encoding="utf-8")
    return path


def test_intended_configuration_and_project_relative_loading(project_env, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    settings = Settings.from_env()
    assert (settings.provider, settings.model, settings.chunk_tokens, settings.context_tokens) == (
        "ollama", "llama3.2", 2000, 8192)
    assert settings.max_output_tokens == 1200 and not settings.allow_paid_api
    assert all(name not in os.environ for name in NAMES)


def test_file_edits_are_read_without_stale_process_values(project_env):
    original = project_env.read_text()
    project_env.write_text(original.replace("2000", "1000"))
    assert Settings.from_env().chunk_tokens == 1000
    project_env.write_text(original)
    assert Settings.from_env().chunk_tokens == 2000
    assert "CHUNK_TOKENS" not in os.environ


def test_invalid_old_file_can_be_corrected_in_same_process(project_env):
    intended = project_env.read_text()
    project_env.write_text(intended.replace("2000", "6000"))
    with pytest.raises(ValueError, match="14700"):
        Settings.from_env()
    project_env.write_text(intended)
    assert Settings.from_env().chunk_tokens == 2000


def test_real_environment_overrides_file_and_error_identifies_source(project_env, monkeypatch):
    monkeypatch.setenv("CHUNK_TOKENS", "6000")
    with pytest.raises(ValueError) as exc:
        Settings.from_env()
    message = str(exc.value)
    assert "CHUNK_TOKENS=6000" in message and "14700" in message
    assert "Process environment overrides .env for: CHUNK_TOKENS" in message
    monkeypatch.delenv("CHUNK_TOKENS")
    assert Settings.from_env().chunk_tokens == 2000


def test_valid_environment_override_is_respected(project_env, monkeypatch):
    monkeypatch.setenv("CHUNK_TOKENS", "1000")
    assert Settings.from_env().chunk_tokens == 1000


def test_optional_key_stays_in_settings_without_enabling_paid_provider(project_env):
    with project_env.open("a") as stream:
        stream.write("OPENAI_API_KEY=synthetic-secret-fixture\n")
    settings = Settings.from_env()
    assert settings.openai_key == "synthetic-secret-fixture"
    assert "synthetic-secret-fixture" not in repr(settings)
    assert "OPENAI_API_KEY" not in os.environ
    with pytest.raises(ProviderError, match="disabled"):
        OpenAIProvider(settings).authorize()


def test_explicit_optional_provider_can_use_file_key_without_global_mutation(project_env):
    project_env.write_text("LLM_PROVIDER=openai\nALLOW_PAID_API=true\nOPENAI_API_KEY=synthetic-key\n")
    settings = Settings.from_env()
    OpenAIProvider(settings).authorize()  # No imports, API client or network calls.
    assert "OPENAI_API_KEY" not in os.environ


def test_utf8_chunk_budget_preserves_all_text():
    text = "Automotive România 研究 🧠\n" * 300
    parts = chunks(text, 2000)
    assert "".join(parts) == text
    assert all(0 < len(part.encode("utf-8")) <= 2000 for part in parts)


def test_ollama_receives_exact_context_and_schema_once():
    settings = Settings(model="llama3.2", context_tokens=8192, chunk_tokens=2000)
    provider = OllamaProvider(settings)
    provider._identity = "local-model"
    output = {"questions": [{"question": "Why?", "why_it_matters": "Timing.", "evidence": "Page 1.",
                            "kind": "Inferred research opportunity", "search_query": "automotive timing"}]}
    response = httpx.Response(200, json={"done": True, "message": {"content": json.dumps(output)}},
                              request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"))
    with patch("httpx.AsyncClient.post", AsyncMock(return_value=response)) as post:
        result = asyncio.run(provider.generate("Questions", SAFETY + "Find questions.", "Evidence", Questions))
    payload = post.await_args.kwargs["json"]
    assert payload["model"] == "llama3.2"
    assert payload["options"]["num_ctx"] == 8192
    assert payload["options"]["num_predict"] == 1200
    assert payload["messages"][0]["content"].count('"$defs"') == 1
    assert isinstance(result, Questions)


def test_actual_prompt_and_schema_are_checked_before_generation():
    provider = OllamaProvider(Settings())
    provider._identity = "local-model"
    with patch("httpx.AsyncClient.post", AsyncMock()) as post:
        with pytest.raises(ProviderError, match="conservative context budget"):
            asyncio.run(provider.generate("Questions", "x" * 6000, "y" * 1000, Questions))
    post.assert_not_awaited()


def test_default_summary_context_matches_main_context(project_env, monkeypatch):
    monkeypatch.delenv("SUMMARY_CONTEXT_TOKENS", raising=False)
    settings = Settings.from_env()
    assert settings.summary_context_tokens == settings.context_tokens == 8192
    with project_env.open("a", encoding="utf-8") as file:
        file.write("SUMMARY_CONTEXT_TOKENS=4096\n")
    assert Settings.from_env().summary_context_tokens == 4096


@pytest.mark.parametrize("layers", [-2, 1000, True, "99"])
def test_invalid_gpu_placement_is_rejected(layers):
    with pytest.raises(ValueError, match="OLLAMA_GPU_LAYERS"):
        Settings(ollama_gpu_layers=layers)


def test_gpu_placement_can_be_configured_or_left_automatic(project_env, monkeypatch):
    monkeypatch.delenv("OLLAMA_GPU_LAYERS", raising=False)
    assert Settings.from_env().ollama_gpu_layers is None
    monkeypatch.setenv("OLLAMA_GPU_LAYERS", "99")
    assert Settings.from_env().ollama_gpu_layers == 99
    monkeypatch.setenv("OLLAMA_GPU_LAYERS", "")
    assert Settings.from_env().ollama_gpu_layers is None
