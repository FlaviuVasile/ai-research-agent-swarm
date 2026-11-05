import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pymupdf
import pytest

from orchestrator import Orchestrator, AnalysisError
from research_swarm.config import Settings
from research_swarm.llm import LLM, chunks, get_encoding
from research_swarm.models import Questions, ResearchQuestion, Relevance
from research_swarm.agents.pdf_master import PDFMaster
from research_swarm.agents.summary_agent import SummaryAgent
from research_swarm.tools.openalex import OpenAlexClient, OpenAlexError


@pytest.fixture(autouse=True)
def isolated_test_key(monkeypatch):
    # Never use local credentials in mocked SDK tests.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")


def paid_llm():
    sdk = pytest.importorskip("agents")
    if not hasattr(sdk, "Runner"):
        pytest.skip("Optional OpenAI Agents SDK is not installed")
    return LLM(settings=Settings(provider="openai", model="gpt-4.1-mini",
                                 allow_paid_api=True, cache_enabled=False))


def pdf_bytes(text: str | None = "Research on machine learning. We evaluate a classifier.") -> bytes:
    with pymupdf.open() as doc:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
        return doc.tobytes()


def question_output() -> Questions:
    return Questions(questions=[ResearchQuestion(
        question="Does the classifier generalize?", why_it_matters="External validity.",
        evidence="Only one evaluation is described.", kind="Inferred research opportunity",
        search_query="classifier external validity")])


def work_payload() -> dict:
    return {"results": [{"id": "https://openalex.org/W123", "title": "External validation",
                         "publication_year": 2024, "doi": "https://doi.org/10.1234/example",
                         "authorships": [{"author": {"display_name": "Example Author"}}]}]}


def mock_get(payload: dict, status: int = 200) -> AsyncMock:
    return AsyncMock(return_value=httpx.Response(
        status, json=payload, request=httpx.Request("GET", "https://api.openalex.org/works")))


def test_full_workflow_mocked_sdk_and_openalex(tmp_path: Path) -> None:
    stages = []
    sdk = AsyncMock(side_effect=[SimpleNamespace(final_output="# Research topic\nMachine learning"),
                                SimpleNamespace(final_output=question_output()),
                                SimpleNamespace(final_output=Relevance(explanation="The title suggests validation research."))])
    llm = paid_llm()
    with patch("agents.Runner.run", sdk), patch(
            "research_swarm.tools.openalex.httpx.AsyncClient.get", mock_get(work_payload())):
        result = asyncio.run(Orchestrator(Settings(), tmp_path, llm=llm).run(
            pdf_bytes(), lambda stage, status: stages.append((stage, status))))
    assert set(result.files) == {"extracted_text.txt", "summary.md", "open_questions.md", "literature_review.md"}
    assert all((tmp_path / name).read_text(encoding="utf-8") == value for name, value in result.files.items())
    assert "Example Author" in result.files["literature_review.md"]
    assert "https://doi.org/10.1234/example" in result.files["literature_review.md"]
    assert [stage for stage, status in stages if status == "complete"] == [
        "PDF Master", "Summary Agent", "Open Questions Finder", "Literature Search Agent"]
    assert sdk.await_count == 3


@pytest.mark.parametrize("data", [b"", b"not a pdf", pdf_bytes(None)])
def test_invalid_and_blank_pdfs(data: bytes, tmp_path: Path) -> None:
    fake = SimpleNamespace(run=AsyncMock())
    with pytest.raises(AnalysisError, match="PDF Master"):
        asyncio.run(Orchestrator(Settings(), tmp_path, llm=fake).run(data))
    fake.run.assert_not_awaited()


def test_partial_pdf_warning() -> None:
    with pymupdf.open(stream=pdf_bytes(), filetype="pdf") as doc:
        doc.new_page()
        result = PDFMaster(Settings()).extract(doc.tobytes())
    assert result.warnings and "OCR" in result.warnings[0]


def test_password_protected_pdf_is_rejected() -> None:
    with pymupdf.open(stream=pdf_bytes(), filetype="pdf") as doc:
        protected = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                                owner_pw="owner", user_pw="reader")
    with pytest.raises(ValueError, match="Password-protected"):
        PDFMaster(Settings()).extract(protected)


def test_api_failure_preserves_completed_output(tmp_path: Path) -> None:
    fake = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("secret-value")))
    (tmp_path / "summary.md").write_text("old summary")
    with pytest.raises(AnalysisError) as exc:
        asyncio.run(Orchestrator(Settings(), tmp_path, llm=fake).run(pdf_bytes()))
    assert "secret-value" not in str(exc.value)
    assert (tmp_path / "extracted_text.txt").exists()
    assert not (tmp_path / "summary.md").exists()


def test_missing_key_is_actionable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(AnalysisError, match="OPENAI_API_KEY"):
        asyncio.run(Orchestrator(Settings(provider="openai", allow_paid_api=True), tmp_path).run(pdf_bytes()))


def test_long_document_is_fully_chunked_and_reduced() -> None:
    text = "Evidence about evaluation. " * 1400
    fake = SimpleNamespace(run=AsyncMock(return_value="## Findings\nEvidence is limited."))
    settings = Settings(chunk_tokens=1000, max_chunks=100,research_mode="FULL_RESEARCH_MODE")
    summary, evidence = asyncio.run(SummaryAgent(fake, settings).summarize(text))
    parts = chunks(text, 1000)
    assert "".join(parts) == text
    assert all(len(get_encoding().encode(p)) <= 1000 for p in parts)
    calls = fake.run.await_args_list
    assert [call.args[2] for call in calls[:len(parts)]] == parts
    assert fake.run.await_count > len(parts)
    assert summary in evidence


def test_cost_limit_rejects_without_model_calls() -> None:
    fake = SimpleNamespace(run=AsyncMock())
    with pytest.raises(ValueError, match="cost limit"):
        asyncio.run(SummaryAgent(fake, Settings(chunk_tokens=1000, max_chunks=1,research_mode="FULL_RESEARCH_MODE")).summarize("word " * 3000))
    fake.run.assert_not_awaited()


def test_empty_openalex_results(tmp_path: Path) -> None:
    fake = SimpleNamespace(run=AsyncMock(side_effect=["Summary", question_output()]))
    with patch("research_swarm.tools.openalex.httpx.AsyncClient.get", mock_get({"results": []})):
        result = asyncio.run(Orchestrator(Settings(), tmp_path, llm=fake).run(pdf_bytes()))
    assert "No papers returned" in result.files["literature_review.md"]
    assert "doi.org" not in result.files["literature_review.md"]


def test_openalex_failure_is_partial_success(tmp_path: Path) -> None:
    fake = SimpleNamespace(run=AsyncMock(side_effect=["Summary", question_output()]))
    with patch("research_swarm.tools.openalex.httpx.AsyncClient.get", mock_get({}, 403)):
        result = asyncio.run(Orchestrator(Settings(), tmp_path, llm=fake).run(pdf_bytes()))
    assert result.warnings
    assert "Search unavailable" in result.files["literature_review.md"]


def test_openalex_retries_and_sanitizes_errors() -> None:
    responses = [httpx.Response(code, json={}, request=httpx.Request(
        "GET", "https://api.openalex.org/works?api_key=secret")) for code in [429, 503, 403]]
    getter = AsyncMock(side_effect=responses)
    with patch("research_swarm.tools.openalex.httpx.AsyncClient.get", getter), patch(
            "research_swarm.tools.openalex.asyncio.sleep", AsyncMock()):
        with pytest.raises(OpenAlexError) as exc:
            asyncio.run(OpenAlexClient("secret").search("query", 3))
    assert getter.await_count == 3
    assert "secret" not in str(exc.value)


def test_metadata_deduplication_and_missing_doi() -> None:
    item = work_payload()["results"][0]
    item["doi"] = None
    item["authorships"] = []
    with patch("research_swarm.tools.openalex.httpx.AsyncClient.get", mock_get({"results": [item, item]})):
        papers = asyncio.run(OpenAlexClient().search("query", 3))
    assert len(papers) == 1
    assert papers[0].doi is None and papers[0].authors == ()


def test_unicode_chunking_preserves_text() -> None:
    text = "研究🧠 café România " * 400
    parts = chunks(text, 1000)
    assert "".join(parts) == text
    assert all(len(get_encoding().encode(p)) <= 1000 for p in parts)


@pytest.mark.parametrize("payload", [None, [], {"results": [None]}, {"results": [{"authorships": 7,
    "id": "https://openalex.org/W123", "title": "Title"}]}])
def test_malformed_openalex_payload_is_safe(payload) -> None:
    with patch("research_swarm.tools.openalex.httpx.AsyncClient.get", mock_get(payload)):
        with pytest.raises(OpenAlexError):
            asyncio.run(OpenAlexClient().search("query", 3))


def test_optional_metadata_and_unsafe_links() -> None:
    item = work_payload()["results"][0]
    item.update(authorships=None, publication_year="<script>", doi="https://doi.org/10.1/a) [x](evil)")
    with patch("research_swarm.tools.openalex.httpx.AsyncClient.get", mock_get({"results": [item]})):
        paper = asyncio.run(OpenAlexClient().search("query", 3))[0]
    assert paper.authors == () and paper.year is None
    assert ")" not in paper.doi and " " not in paper.doi


@pytest.mark.parametrize("output", [None, "", "   ", 42])
def test_invalid_text_model_output(output) -> None:
    llm = paid_llm()
    with patch("agents.Runner.run", AsyncMock(return_value=SimpleNamespace(final_output=output))):
        with pytest.raises(ValueError, match="empty response"):
            asyncio.run(llm.run("Summary Agent", "Summarize", "Evidence"))


def test_invalid_structured_model_output() -> None:
    llm = paid_llm()
    with patch("agents.Runner.run", AsyncMock(return_value=SimpleNamespace(final_output="wrong"))):
        with pytest.raises(ValueError, match="invalid structured output"):
            asyncio.run(llm.run("Questions", "Find questions", "Evidence", Questions))


def test_sdk_validation_error_does_not_expose_input(tmp_path: Path) -> None:
    llm = paid_llm()
    with patch("agents.Runner.run", AsyncMock(side_effect=ValueError("secret-document"))):
        with pytest.raises(AnalysisError) as exc:
            asyncio.run(Orchestrator(Settings(), tmp_path, llm=llm).run(pdf_bytes()))
    assert "secret-document" not in str(exc.value)
    assert (tmp_path / "extracted_text.txt").exists()


def test_questions_failure_preserves_summary(tmp_path: Path) -> None:
    fake = SimpleNamespace(run=AsyncMock(side_effect=["Saved summary", RuntimeError("failed")]))
    with pytest.raises(AnalysisError, match="Open Questions Finder"):
        asyncio.run(Orchestrator(Settings(), tmp_path, llm=fake).run(pdf_bytes()))
    assert "Saved summary" in (tmp_path / "summary.md").read_text()
    assert not (tmp_path / "open_questions.md").exists()


@pytest.mark.parametrize("settings", [{"model": " "}, {"max_pages": 0}, {"max_pdf_bytes": 0}])
def test_invalid_settings(settings) -> None:
    with pytest.raises(ValueError):
        Settings(**settings)


def test_whitespace_structured_output_is_rejected() -> None:
    with pytest.raises(ValueError):
        Relevance(explanation="   ")
    data = question_output().questions[0].model_dump()
    data["search_query"] = "   "
    with pytest.raises(ValueError):
        ResearchQuestion(**data)


def test_model_clients_are_closed_between_event_loops() -> None:
    sdk = AsyncMock(return_value=SimpleNamespace(final_output="Summary"))
    llm = paid_llm()
    with patch("agents.Runner.run", sdk):
        for _ in range(2):
            asyncio.run(llm.run("Summary Agent", "Summarize", "Evidence"))
    clients = [call.kwargs["run_config"].model_provider._client for call in sdk.await_args_list]
    assert clients[0] is not clients[1]
    assert all(client.is_closed() for client in clients)
