"""Real client + real local model + real scientific PDF, never mocked tools."""
import argparse
import asyncio
import json
import hashlib
import os
from pathlib import Path
import sys
from time import perf_counter

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from research_swarm.config import ROOT
from research_swarm.models import AnalysisResponse
from research_swarm.agents.pdf_master import PDFMaster
from research_swarm.config import Settings


async def run(output):
    if output.exists():
        raise ValueError("Choose a new smoke report filename.")
    paper_root = ROOT / ".runtime" / "evaluation-papers"
    results = ROOT / ".runtime" / "mcp-live" / output.stem
    env = {**os.environ, "LLM_PROVIDER":"ollama", "LOCAL_TEST_MODE":"false", "ALLOW_PAID_API":"false",
        "LLM_CACHE_ENABLED":"false","MAX_QUESTIONS":"1","PAPERS_PER_QUESTION":"1",
        "PROMPT_VARIANT":"selected",
        "CORPUS_ROOT":str(results / "corpus"),"LLM_TIMEOUT_SECONDS":"120","DOCUMENT_TIMEOUT_SECONDS":"600"}
    params = StdioServerParameters(command=sys.executable,args=["-m","research_swarm.mcp_server",
        "--pdf-root",str(paper_root),"--output-root",str(results / "runs")],env=env,cwd=ROOT)
    started = perf_counter()
    async with Client(params,read_timeout_seconds=700) as client:
        tools = (await client.list_tools()).tools
        extracted = await client.call_tool("extract_paper_text",{"pdf_path":"1412.6980v9.pdf"})
        if extracted.is_error:
            raise RuntimeError(str(extracted))
        pdf_bytes = (paper_root / "1412.6980v9.pdf").read_bytes()
        expected_pages = PDFMaster(Settings()).extract(pdf_bytes).pages
        source = extracted.structured_content
        assert source["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert {row["page"]:row["text"] for row in source["pages"]} == expected_pages
        result = await client.call_tool("analyze_paper",{"pdf_path":"1412.6980v9.pdf"})
        if result.is_error:
            raise RuntimeError(str(result))
        analysis = AnalysisResponse.model_validate(result.structured_content)
        if analysis.synthetic:
            raise RuntimeError("Live smoke unexpectedly used fixtures.")
        assert analysis.source.model_dump() == source
        assert analysis.data.questions.questions
        run_folder = results / "runs" / analysis.run_id
        for name in ("extracted_text.txt","summary.md","open_questions.md","literature_review.md","analysis.json"):
            assert (run_folder / name).is_file(), name
        reread = await client.call_tool("get_analysis_result",{"run_id":analysis.run_id})
        assert reread.structured_content == result.structured_content
        error_checks = {}
        for name, tool, args in [
            ("path_traversal","extract_paper_text",{"pdf_path":"../outside.pdf"}),
            ("missing_file","extract_paper_text",{"pdf_path":"missing-scientific-paper.pdf"}),
            ("invalid_mode","analyze_paper",{"pdf_path":"1412.6980v9.pdf","mode":"invalid"}),
            ("invalid_run_id","get_analysis_result",{"run_id":"../outside"})]:
            bad = await client.call_tool(tool,args)
            assert bad.is_error, name
            error_checks[name] = True
        selection = json.loads((run_folder / "selection.json").read_text(encoding="utf-8"))
        from research_swarm.corpus.store import CorpusStore
        store = CorpusStore(results / "corpus" / "research" / "corpus.sqlite3")
        source_reference_checks = []
        for chosen in selection["selections"]:
            evidence = store.evidence(chosen["evidence_id"])
            page = expected_pages[chosen["page"]]
            # Corpus offsets refer to exact corpus page text (which retains outer whitespace).
            with store.connect() as db:
                stored_page = db.execute("SELECT text FROM pages WHERE document_id=? AND number=?",
                    (evidence["document_id"],chosen["page"])).fetchone()[0]
            assert stored_page.strip() == page
            assert stored_page[evidence["start_char"]:evidence["end_char"]] == evidence["text"]
            assert evidence["sha256"] == analysis.source.sha256
            source_reference_checks.append(dict(evidence_id=evidence["id"],page=chosen["page"],
                exact_offsets_match=True,checksum_matches=True))
        assert source_reference_checks
        report = dict(tools=[t.name for t in tools],seconds=perf_counter()-started,
            source_page_count=len(analysis.source.pages),invalid_path_rejected=error_checks["path_traversal"],
            error_checks=error_checks,exact_pdf_pages_match=True,source_reference_checks=source_reference_checks,
            saved_result_matches=True,analysis=analysis.model_dump())
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k!="analysis"}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    asyncio.run(run(parser.parse_args().output))
