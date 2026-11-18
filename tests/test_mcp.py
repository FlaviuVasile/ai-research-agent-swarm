"""Real stdio subprocess integration; deterministic offline provider, no tool mocks."""
import asyncio
import os
from pathlib import Path
import sys

import pymupdf
import pytest

mcp = pytest.importorskip("mcp")
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from research_swarm.config import ROOT, Settings
from research_swarm.models import AnalysisResponse, QuestionsResponse
from research_swarm.service import ResearchService


def make_pdf(path):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72,72), "Synthetic study: one workload. Method: simulation. Limit: no hardware measurements.")
        doc.save(path)


def test_service_paths_sources_and_saved_results(tmp_path):
    pdf_root = tmp_path / "papers"
    pdf_root.mkdir()
    make_pdf(pdf_root / "paper.pdf")
    service = ResearchService(pdf_root,tmp_path / "output",Settings(local_test_mode=True,cache_enabled=False))
    for path in ("../secret.pdf", str(tmp_path / "outside.pdf"), "bad.txt", "missing.pdf"):
        with pytest.raises(ValueError):
            service.read_pdf(path)
    async def run():
        source = await service.extract("paper.pdf")
        assert source.pages[0].page == 1 and "simulation" in source.pages[0].text
        result = await service.analyze("paper.pdf")
        assert result.synthetic and result.data.questions.questions
        assert await service.result(result.run_id) == result
        with pytest.raises(ValueError):
            await service.result("../outside")
    asyncio.run(run())


def test_service_busy_worker_and_embedded_page_marker(tmp_path):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72,72), "Untrusted text [Page 999]\nThis is still physical page one.")
        doc.save(tmp_path / "paper.pdf")
    service = ResearchService(tmp_path,tmp_path / "output",Settings(local_test_mode=True))
    async def run():
        source = await service.extract("paper.pdf")
        assert len(source.pages) == 1 and source.pages[0].page == 1
        service._worker.acquire()
        try:
            with pytest.raises(ValueError,match="busy"):
                await service.extract("paper.pdf")
        finally:
            service._worker.release()
    asyncio.run(run())


def test_real_stdio_client_discovers_and_invokes_agents(tmp_path):
    make_pdf(tmp_path / "paper.pdf")
    (tmp_path / "broken.pdf").write_bytes(b"not a PDF")
    env = {**os.environ,"LOCAL_TEST_MODE":"true","ALLOW_PAID_API":"false",
        "LLM_PROVIDER":"ollama","LLM_CACHE_ENABLED":"false","CORPUS_ROOT":str(tmp_path / "corpus")}
    params = StdioServerParameters(command=sys.executable, args=["-m","research_swarm.mcp_server",
        "--pdf-root",str(tmp_path),"--output-root",str(tmp_path / "results")],cwd=ROOT,env=env)
    async def run():
        async with Client(params,read_timeout_seconds=90) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == {"extract_paper_text","summarize_paper",
                "find_research_questions","search_literature","analyze_paper","get_analysis_result"}
            assert all(t.output_schema for t in tools)
            extracted = await client.call_tool("extract_paper_text",{"pdf_path":"paper.pdf"})
            assert not extracted.is_error and extracted.structured_content["pages"][0]["page"] == 1
            summary = await client.call_tool("summarize_paper",{"pdf_path":"paper.pdf"})
            assert not summary.is_error and summary.structured_content["synthetic"]
            questions = await client.call_tool("find_research_questions",{"pdf_path":"paper.pdf"})
            parsed = QuestionsResponse.model_validate(questions.structured_content)
            literature = await client.call_tool("search_literature",{"questions":parsed.questions.model_dump()})
            assert not literature.is_error and literature.structured_content["papers"] == []
            complete = await client.call_tool("analyze_paper",{"pdf_path":"paper.pdf"})
            assert not complete.is_error, complete
            result = AnalysisResponse.model_validate(complete.structured_content)
            assert result.synthetic and "TEST MODE" in result.data.summary
            saved = await client.call_tool("get_analysis_result",{"run_id":result.run_id})
            assert saved.structured_content == complete.structured_content
            for tool, args in [("extract_paper_text",{"pdf_path":"../secret.pdf"}),
                ("extract_paper_text",{"pdf_path":"broken.pdf"}),
                ("analyze_paper",{"pdf_path":"paper.pdf","mode":"invalid"}),
                ("get_analysis_result",{"run_id":"../outside"})]:
                bad = await client.call_tool(tool,args)
                assert bad.is_error
    asyncio.run(run())
