"""Validated runtime settings, loaded without exposing secrets."""
from dataclasses import dataclass, field
from pathlib import Path
import os
from urllib.parse import urlsplit
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent

@dataclass(frozen=True)
class Settings:
    model: str = "llama3.2:latest"
    provider: str = "ollama"
    allow_paid_api: bool = False
    openai_key: str = field(default="", repr=False)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_gpu_layers: int | None = None
    local_test_mode: bool = False
    cache_enabled: bool = True
    cache_dir: Path = ROOT / ".cache" / "llm"
    cache_ttl_seconds: int = 30 * 24 * 3600
    llm_timeout: int = 90
    document_timeout: int = 600
    research_mode: str = "FAST_RESEARCH_MODE"
    summary_output_tokens: int = 256
    summary_context_tokens: int = 8192
    _single_prompt: bool = field(default=False,repr=False,compare=False)
    fast_evidence_limit: int = 4
    research_db: Path | None = None
    context_tokens: int = 8192
    max_output_tokens: int = 1200
    chunk_tokens: int = 2000
    max_chunks: int = 32
    max_questions: int = 5
    papers_per_question: int = 3
    max_pdf_bytes: int = 25 * 1024 * 1024
    max_pages: int = 500
    openalex_key: str = ""

    def __post_init__(self) -> None:
        if self.research_mode not in {"FAST_RESEARCH_MODE","FULL_RESEARCH_MODE"}:
            raise ValueError("RESEARCH_MODE must be FAST_RESEARCH_MODE or FULL_RESEARCH_MODE.")
        if not 1 <= self.document_timeout <= 3600 or not 256 <= self.summary_output_tokens <= 512:
            raise ValueError("Document budget must be 1–3600 seconds; summary output must be 256–512 tokens.")
        if not 1 <= self.fast_evidence_limit <= 8:
            raise ValueError("FAST_EVIDENCE_LIMIT must be 1–8.")
        if not 4096 <= self.summary_context_tokens <= 8192:
            raise ValueError("SUMMARY_CONTEXT_TOKENS must be 4096–8192.")
        if self.ollama_gpu_layers is not None and (
                type(self.ollama_gpu_layers) is not int or not -1 <= self.ollama_gpu_layers <= 999):
            raise ValueError("OLLAMA_GPU_LAYERS must be an integer from -1 to 999, or empty for automatic placement.")
        if not self.model.strip():
            raise ValueError("The configured model must not be empty.")
        if self.provider not in {"ollama", "openai"}:
            raise ValueError("LLM_PROVIDER must be ollama or openai.")
        url = urlsplit(self.ollama_url)
        if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment):
            raise ValueError("OLLAMA_BASE_URL must be a loopback HTTP address without a path or credentials.")
        if not 1 <= self.llm_timeout <= 3600 or self.cache_ttl_seconds < 1:
            raise ValueError("LLM timeout and cache lifetime must be positive and bounded.")
        if not 256 <= self.max_output_tokens <= 4096 or not 4096 <= self.context_tokens <= 32768:
            raise ValueError("LLM output/context limits are out of range.")
        if (not self.local_test_mode and self.provider == "ollama"
                and self.context_tokens < (1 if self._single_prompt else 2) * self.chunk_tokens + self.max_output_tokens + 1500):
            factor=1 if self._single_prompt else 2
            required = factor * self.chunk_tokens + self.max_output_tokens + 1500
            raise ValueError(f"OLLAMA_CONTEXT_TOKENS={self.context_tokens} is too small for "
                             f"CHUNK_TOKENS={self.chunk_tokens} and LLM_MAX_OUTPUT_TOKENS={self.max_output_tokens}. "
                             f"Conservative reserve: {factor} × {self.chunk_tokens} + {self.max_output_tokens} + 1500 = {required}. "
                             "Use CHUNK_TOKENS=2000 with context 8192 and output 1200; "
                             "lower input/output budgets before increasing memory usage.")
        if self.max_pdf_bytes < 1 or self.max_pages < 1:
            raise ValueError("PDF size and page limits must be positive.")
        if not 1000 <= self.chunk_tokens <= 12000:
            raise ValueError("CHUNK_TOKENS must be between 1000 and 12000.")
        if not 1 <= self.max_chunks <= 100:
            raise ValueError("MAX_CHUNKS must be between 1 and 100.")
        if not 1 <= self.max_questions <= 8 or not 1 <= self.papers_per_question <= 5:
            raise ValueError("Question/paper limits are out of range.")

    @classmethod
    def from_env(cls) -> "Settings":
        # Read afresh on every Streamlit analysis without promoting file values
        # into os.environ, where they would otherwise shadow subsequent edits.
        file_values = dotenv_values(ROOT / ".env")

        def value(name: str, default: str) -> str:
            return os.environ[name] if name in os.environ else (file_values.get(name) or default)

        def boolean(name: str, default: str = "false") -> bool:
            setting = value(name, default).strip().lower()
            if setting not in {"true", "false"}:
                raise ValueError(f"{name} must be true or false.")
            return setting == "true"

        provider = value("LLM_PROVIDER", "ollama").strip().lower()
        try:
            return cls(model=value("OLLAMA_MODEL", "llama3.2:latest") if provider == "ollama"
                   else value("OPENAI_MODEL", "gpt-4.1-mini"),
                   provider=provider, allow_paid_api=boolean("ALLOW_PAID_API"),
                   openai_key=value("OPENAI_API_KEY", ""),
                   local_test_mode=boolean("LOCAL_TEST_MODE"),
                   ollama_url=value("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                   ollama_gpu_layers=(int(value("OLLAMA_GPU_LAYERS", ""))
                                      if value("OLLAMA_GPU_LAYERS", "").strip() else None),
                   cache_enabled=boolean("LLM_CACHE_ENABLED", "true"),
                   cache_dir=Path(value("LLM_CACHE_DIR", str(ROOT / ".cache" / "llm"))),
                   cache_ttl_seconds=int(value("LLM_CACHE_TTL_SECONDS", "2592000")),
                   llm_timeout=int(value("LLM_TIMEOUT_SECONDS", "90")),
                   document_timeout=int(value("DOCUMENT_TIMEOUT_SECONDS", "600")),
                   research_mode=value("RESEARCH_MODE","FAST_RESEARCH_MODE"),
                   summary_output_tokens=int(value("SUMMARY_OUTPUT_TOKENS","256")),
                   summary_context_tokens=int(value("SUMMARY_CONTEXT_TOKENS",
                       str(min(8192, int(value("OLLAMA_CONTEXT_TOKENS", "8192")))))),
                   fast_evidence_limit=int(value("FAST_EVIDENCE_LIMIT","4")),
                   research_db=Path(value("CORPUS_ROOT",str(ROOT))) / "research" / "corpus.sqlite3",
                   context_tokens=int(value("OLLAMA_CONTEXT_TOKENS", "8192")),
                   max_output_tokens=int(value("LLM_MAX_OUTPUT_TOKENS", "1200")),
                   chunk_tokens=int(value("CHUNK_TOKENS", "2000")),
                   max_chunks=int(value("MAX_CHUNKS", "32")),
                   max_questions=int(value("MAX_QUESTIONS", "5")),
                   papers_per_question=int(value("PAPERS_PER_QUESTION", "3")),
                   openalex_key=value("OPENALEX_API_KEY", ""))
        except ValueError as exc:
            if str(exc).startswith("OLLAMA_CONTEXT_TOKENS="):
                overrides = [name for name in ("CHUNK_TOKENS", "OLLAMA_CONTEXT_TOKENS", "LLM_MAX_OUTPUT_TOKENS")
                             if name in os.environ]
                source = ("Process environment overrides .env for: " + ", ".join(overrides) + ". "
                          if overrides else "Budget settings are from the project .env or defaults. ")
                raise ValueError(f"{exc} {source}Restart Streamlit after clearing stale shell overrides.") from None
            raise
