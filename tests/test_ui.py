from streamlit.testing.v1 import AppTest
from pathlib import Path
from io import BytesIO
from unittest.mock import AsyncMock, patch
from research_swarm.models import AnalysisResult
from research_swarm.config import Settings
from orchestrator import AnalysisError
import pymupdf
from research_swarm.corpus.config import CorpusConfig
from research_swarm.jobs import active
import time
import threading
import asyncio
from research_swarm.telemetry import emit


def settle(app):
    deadline = time.monotonic()+10
    while active(app.session_state["analysis_run_id"]) and time.monotonic()<deadline:
        time.sleep(.01)
    assert not active(app.session_state["analysis_run_id"])
    app.run(timeout=30)


def test_initial_interface_renders_without_secrets() -> None:
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "AI Research Agent Swarm"
    assert app.button[0].label == "Start Analysis"
    assert app.button[0].disabled


def test_upload_analysis_progress_and_downloads(tmp_path) -> None:
    files = {name: "# Generated report" for name in ("summary.md", "open_questions.md", "literature_review.md")}

    async def run(data, progress):
        assert data == b"uploaded PDF"
        progress("PDF Master", "complete")
        return AnalysisResult(files, ["Review citations"], str(tmp_path))

    with patch("research_swarm.config.ROOT",tmp_path), patch("streamlit.file_uploader", return_value=BytesIO(b"uploaded PDF")), patch(
            "research_swarm.config.Settings.from_env", return_value=Settings()), patch(
            "orchestrator.Orchestrator.run", side_effect=run):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
        assert not app.button[0].disabled
        app.button[0].click().run(timeout=30)
        settle(app)
        assert not app.exception
        assert app.success and app.warning
        assert len(app.tabs) == 3
        assert len(app.get("download_button")) == 3
        assert any("PDF Master" in entry.value for entry in app.markdown)
        app.run(timeout=30)
        assert len(app.get("download_button")) == 3


def test_failed_analysis_clears_previous_results(tmp_path) -> None:
    with patch("research_swarm.config.ROOT",tmp_path), patch("streamlit.file_uploader", return_value=BytesIO(b"bad PDF")), patch(
            "research_swarm.config.Settings.from_env", return_value=Settings()), patch(
            "orchestrator.Orchestrator.run", AsyncMock(side_effect=AnalysisError("PDF Master: invalid PDF"))):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
        app.session_state["result"] = AnalysisResult({}, [], "old")
        app.button[0].click().run(timeout=30)
        settle(app)
    assert not app.exception
    assert "invalid PDF" in app.error[0].value
    assert not app.get("download_button")


def test_offline_mode_runs_real_orchestrator_in_ui(tmp_path) -> None:
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "A synthetic automotive research PDF.")
        data = doc.tobytes()
    with patch("streamlit.file_uploader", return_value=BytesIO(data)), patch(
            "research_swarm.config.Settings.from_env", return_value=Settings(local_test_mode=True, cache_enabled=False)), patch(
            "research_swarm.config.ROOT", tmp_path), patch("httpx.AsyncClient.send", AsyncMock(side_effect=AssertionError("Network forbidden"))):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
        app.button[0].click().run(timeout=30)
        settle(app)
    assert not app.exception and not app.error
    assert len(app.get("download_button")) == 4
    assert any("TEST MODE" in warning.value for warning in app.warning)


def test_corpus_registration_checkpoint_and_evidence_ui(tmp_path) -> None:
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72,72),"QNX scheduling evidence. Synthetic UI test only.")
        data = doc.tobytes()
    with patch("streamlit.file_uploader",return_value=BytesIO(data)), patch(
            "research_swarm.corpus.config.CorpusConfig.from_env",return_value=CorpusConfig(root=tmp_path)), patch(
            "httpx.AsyncClient.send",AsyncMock(side_effect=AssertionError("Network forbidden"))):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
        app.checkbox(key="corpus_enabled").check().run(timeout=30)
        app.text_input(key="corpus_title").input("Synthetic corpus UI paper").run(timeout=30)
        app.button(key="corpus_register").click().run(timeout=30)
        assert not app.exception and not app.error
        app.button(key="corpus_process").click().run(timeout=30)
        app.text_input(key="corpus_query").input("QNX").run(timeout=30)
        app.button(key="corpus_search").click().run(timeout=30)
        assert not app.exception and not app.error
        assert any("QNX" in row.value for row in app.code)
        assert any("/p1/E" in row.value for row in app.text)
        citation = {"title": "Synthetic corpus UI paper", "page": 1, "chunk_id": 1,
                    "sha256": "fixture-sha", "start_char": 0, "end_char": 24,
                    "quote": "QNX scheduling evidence."}
        answer = {"status": "model_checked_answer", "answer": "The study describes QNX scheduling.",
                  "claims": [{"claim": "The study describes QNX scheduling.",
                              "kind": "reported_finding", "citations": [citation]}],
                  "evidence": [{"citation": citation}], "unanswered_parts": [],
                  "coverage": "Model support assessment only."}
        with patch("research_swarm.service.ResearchService.ask_corpus",
                   AsyncMock(return_value=answer)):
            app.button(key="corpus_ask").click().run(timeout=30)
        assert not app.exception and not app.error
        assert any("The study describes QNX scheduling." in row.value for row in app.markdown)
        assert any("QNX scheduling evidence." in row.value for row in app.code)


def test_dashboard_remains_responsive_and_reruns_do_not_restart_slow_work(tmp_path):
    entered=threading.Event()
    release=threading.Event()
    async def slow_run(data,progress):
        progress("PDF Master","complete")
        progress("Summary Agent","running")
        emit("summary_plan",total=2)
        emit("chunk_start",index=1)
        emit("request_start",agent="Summary Agent")
        emit("response",characters=4)
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.01)
        emit("request_end")
        emit("chunk_complete",index=1,seconds=1,cached=False)
        return AnalysisResult({name:"Synthetic mocked report" for name in (
            "summary.md","open_questions.md","literature_review.md")},[],str(tmp_path))
    with patch("research_swarm.config.ROOT",tmp_path),patch("streamlit.file_uploader",return_value=BytesIO(b"PDF")),patch(
            "research_swarm.config.Settings.from_env",return_value=Settings()),patch(
            "orchestrator.Orchestrator.run",side_effect=slow_run) as run:
        app=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py").run(timeout=30)
        try:
            app.button[0].click().run(timeout=30)
            assert entered.wait(5)
            app.run(timeout=30)
            assert not app.exception and app.button[0].disabled
            assert any("Chunk 1 is in progress" in row.value for row in app.caption)
            assert any("still running" in row.value for row in app.info)
            assert run.call_count==1
            identifier=app.session_state["analysis_run_id"]
            restored=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py")
            restored.query_params["run"]=identifier
            restored.run(timeout=30)
            assert not restored.exception and restored.button[0].disabled
            assert run.call_count==1
        finally:
            release.set()
            settle(app)
