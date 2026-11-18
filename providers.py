"""Provider boundary: local Ollama by default, explicitly authorized OpenAI only."""
from research_swarm.prompt_loader import load_prompt
import asyncio
import json
import os
import logging
from typing import Protocol

import httpx
from pydantic import BaseModel

from research_swarm.config import Settings
from research_swarm.models import Questions, ResearchQuestion, Relevance
from research_swarm.telemetry import observed, emit

logger = logging.getLogger(__name__)


class ProviderError(ValueError):
    """Fixed, user-safe provider failure; never include raw API errors."""


class Provider(Protocol):
    def authorize(self) -> None: ...
    async def identity(self) -> str: ...
    async def generate(self, name: str, instructions: str, evidence: str,
                       output_type: type[BaseModel] | None) -> str | BaseModel: ...


class OllamaProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._identity: str | None = None

    def authorize(self) -> None:
        if "cloud" in self.settings.model.lower():
            raise ProviderError("Cloud Ollama models are disabled. Select downloaded local weights.")

    async def identity(self) -> str:
        self.authorize()
        if self._identity is not None:
            return self._identity
        try:
            # Settings enforce loopback HTTP and redirects are disabled; no TLS CA bundle is needed.
            async with httpx.AsyncClient(base_url=self.settings.ollama_url,
                                         timeout=10, trust_env=False, follow_redirects=False, verify=False) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                models = response.json()["models"]
                target = self.settings.model
                if ":" not in target:
                    target += ":latest"
                model = next((m for m in models if m.get("name") == target), None)
                if model is None:
                    raise ProviderError("Ollama model is not installed. Run ollama pull for OLLAMA_MODEL.")
                if (model.get("remote_host") or model.get("remote_model")
                        or model.get("details", {}).get("format") != "gguf"
                        or not isinstance(model.get("size"), int) or model["size"] <= 0
                        or not isinstance(model.get("digest"), str) or not model["digest"]):
                    raise ProviderError("Ollama requires downloaded local GGUF weights; remote models are disabled.")
                response = await client.post("/api/show", json={"model": self.settings.model})
                response.raise_for_status()
                info = response.json()
                if info.get("remote_host") or info.get("remote_model"):
                    raise ProviderError("Remote Ollama models are disabled.")
                self._identity = f"ollama:{self.settings.ollama_url}:{target}:{model['digest']}"
                return self._identity
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError("Could not inspect local Ollama. Start Ollama and check OLLAMA_BASE_URL/model.") from None

    async def generate(self, name, instructions, evidence, output_type):
        await self.identity()
        system = instructions
        payload = {"model": self.settings.model, "stream": observed(), "keep_alive": "10m",
                   "options": {"temperature": 0, "num_ctx": self.settings.context_tokens,
                               "num_predict": self.settings.max_output_tokens}}
        if self.settings.ollama_gpu_layers is not None:
            payload["options"]["num_gpu"] = self.settings.ollama_gpu_layers
        if output_type:
            schema = output_type.model_json_schema()
            payload["format"] = schema
            system += load_prompt("schema_instruction") + json.dumps(schema)
        payload["messages"] = [{"role": "system", "content": system},
                               {"role": "user", "content": evidence}]
        # Count the actual system/schema/evidence once, not just the PDF chunk.
        # UTF-8 bytes conservatively approximate tokens for the tested Llama model;
        # the extra reserve covers chat-template markers, not a tokenizer download.
        prompt_budget = len(system.encode("utf-8")) + len(evidence.encode("utf-8")) + 256
        required = prompt_budget + self.settings.max_output_tokens
        if required > self.settings.context_tokens:
            raise ProviderError(f"Ollama request exceeds the conservative context budget: {prompt_budget} "
                                f"prompt units + {self.settings.max_output_tokens} output tokens > "
                                f"{self.settings.context_tokens} context. Lower CHUNK_TOKENS or shorten the input.")
        try:
            # Settings enforce loopback HTTP and redirects are disabled; no TLS CA bundle is needed.
            async with httpx.AsyncClient(base_url=self.settings.ollama_url, timeout=self.settings.llm_timeout,
                                         trust_env=False, follow_redirects=False, verify=False) as client:
                if payload["stream"]:
                    async with asyncio.timeout(self.settings.llm_timeout):
                        async with client.stream("POST","/api/chat",json=payload) as response:
                            response.raise_for_status()
                            parts = []
                            characters = 0
                            data = {}
                            async for line in response.aiter_lines():
                                if not line:
                                    continue
                                frame = json.loads(line)
                                fragment = frame.get("message",{}).get("content","")
                                if not isinstance(fragment,str) or frame.get("error"):
                                    raise ValueError("Invalid streamed response")
                                characters += len(fragment)
                                if characters > self.settings.max_output_tokens * 32 + 16384:
                                    raise ValueError("Streamed response exceeds output safety limit")
                                parts.append(fragment)
                                emit("response",characters=len(fragment))
                                if frame.get("done"):
                                    data = frame
                                    break
                            data["message"] = {"content":"".join(parts)}
                else:
                    response = await client.post("/api/chat", json=payload)
                    response.raise_for_status()
                    data = response.json()
                logger.info("Ollama context=%d, conservative_prompt_budget=%d, prompt_eval_count=%s, eval_count=%s",
                            self.settings.context_tokens, prompt_budget,
                            data.get("prompt_eval_count"), data.get("eval_count"))
                emit("request_metrics",**{key:data[key] for key in (
                    "prompt_eval_count","eval_count","load_duration","prompt_eval_duration","eval_duration","total_duration")
                    if type(data.get(key)) is int})
                if data.get("done") is not True or data.get("done_reason") == "length":
                    raise ProviderError("Ollama output was incomplete. Raise LLM_MAX_OUTPUT_TOKENS or use a shorter input.")
                content = data["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ProviderError("Ollama returned an empty response.")
                return output_type.model_validate_json(content) if output_type else content
        except ProviderError:
            raise
        except (httpx.TimeoutException,TimeoutError):
            raise ProviderError("Ollama timed out. Use a smaller model/input or raise LLM_TIMEOUT_SECONDS.") from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError("Ollama request failed or returned invalid output. Check the model and local server.") from None


class OpenAIProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def authorize(self) -> None:
        if self.settings.local_test_mode or self.settings.provider != "openai" or not self.settings.allow_paid_api:
            raise ProviderError("OpenAI is disabled. Explicitly set LLM_PROVIDER=openai and ALLOW_PAID_API=true.")
        if not (self.settings.openai_key or os.getenv("OPENAI_API_KEY", "")).strip():
            raise ProviderError("Set OPENAI_API_KEY before opting into OpenAI.")

    async def identity(self) -> str:
        self.authorize()
        return "openai:https://api.openai.com/v1:" + self.settings.model

    async def generate(self, name, instructions, evidence, output_type):
        self.authorize()  # Also guard direct calls, independently of cache/factory.
        try:
            from agents import Agent, ModelSettings, Runner, RunConfig
            from agents.models.openai_provider import OpenAIProvider as SDKProvider
            from openai import AsyncOpenAI
        except ImportError:
            raise ProviderError("Install requirements-openai.txt to use the optional OpenAI provider.") from None
        agent = Agent(name=name, instructions=instructions, model=self.settings.model, output_type=output_type,
                      model_settings=ModelSettings(max_tokens=self.settings.max_output_tokens, temperature=0))
        try:
            async with AsyncOpenAI(api_key=self.settings.openai_key or os.getenv("OPENAI_API_KEY"), base_url="https://api.openai.com/v1",
                                   max_retries=2) as client:
                result = await asyncio.wait_for(Runner.run(agent, evidence, max_turns=1,
                    run_config=RunConfig(tracing_disabled=True, model_provider=SDKProvider(openai_client=client))),
                    timeout=self.settings.llm_timeout)
        except Exception:
            raise ProviderError("OpenAI request failed; check credentials, quota, connectivity and model access.") from None
        return result.final_output


class TestProvider:
    """Deterministic fixtures for plumbing checks, not academic analysis."""
    def authorize(self) -> None:
        pass

    async def identity(self) -> str:
        return "offline-test-fixtures-v1"

    async def generate(self, name, instructions, evidence, output_type):
        if output_type is Questions:
            return Questions(questions=[ResearchQuestion(
                question="TEST MODE: What evidence would support a platform comparison?",
                why_it_matters="Synthetic question for testing only.", evidence="No research assessment performed.",
                kind="Inferred research opportunity", search_query="automotive operating systems comparison")])
        if output_type is Relevance:
            return Relevance(explanation="TEST MODE: Synthetic relevance; no paper was assessed.")
        if output_type is not None:
            raise ProviderError("Unsupported offline test schema.")
        return "# TEST MODE — Synthetic summary\n\nNo AI research analysis was performed."


def create_provider(settings: Settings) -> Provider:
    if settings.local_test_mode:
        return TestProvider()
    return OllamaProvider(settings) if settings.provider == "ollama" else OpenAIProvider(settings)
