"""Official MCP SDK stdio adapter. No Streamlit import or duplicated agent logic."""
import argparse
from dataclasses import replace
from functools import wraps
import logging
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from research_swarm.config import ROOT, Settings
from research_swarm.models import (AnalysisResponse, PaperSource, Questions, SummaryResponse,
    QuestionsResponse, LiteratureResponse)
from research_swarm.service import ResearchService
from research_swarm.corpus.config import CorpusConfig

Mode = Literal["FAST_RESEARCH_MODE", "FULL_RESEARCH_MODE"]
RetrievalMode = Literal["keyword", "semantic", "hybrid"]


def create_server(service: ResearchService) -> MCPServer:
    server = MCPServer("Scientific Paper Research", version="1.0.0")

    def tool(function):
        @wraps(function)
        async def safe(*args, **kwargs):
            try:
                return await function(*args, **kwargs)
            except ValueError as exc:
                raise ToolError(str(exc)) from None
            except Exception:
                raise ToolError("Research operation failed. Check local services and output permissions; completed files were retained.") from None
        return server.tool()(safe)

    @tool
    async def extract_paper_text(pdf_path: str) -> PaperSource:
        """Extract actual PDF page text. Path is relative to the configured PDF root. No LLM calls."""
        return await service.extract(pdf_path)

    @tool
    async def summarize_paper(pdf_path: str, mode: Mode = "FAST_RESEARCH_MODE") -> SummaryResponse:
        """Invoke SummaryAgent; FAST samples excerpts, FULL maps all accepted chunks. Writes configured response cache."""
        return await service.summarize(pdf_path,mode)

    @tool
    async def find_research_questions(pdf_path: str) -> QuestionsResponse:
        """Invoke SummaryAgent then QuestionsAgent; return validated questions and source pages. May write cache."""
        return await service.questions(pdf_path)

    @tool
    async def search_literature(questions: Questions) -> LiteratureResponse:
        """Invoke LiteratureAgent with OpenAlex; relevance uses titles only. Sends queries online unless in test mode."""
        return await service.literature(questions)

    @tool
    async def analyze_paper(pdf_path: str, mode: Mode = "FAST_RESEARCH_MODE") -> AnalysisResponse:
        """Run the existing four-agent Orchestrator. Saves reports, journals and validated data; OpenAlex receives queries."""
        return await service.analyze(pdf_path,mode)

    @tool
    async def get_analysis_result(run_id: str) -> AnalysisResponse:
        """Read a previously completed analysis by its returned run ID without rerunning agents."""
        return await service.result(run_id)

    @tool
    async def ingest_paper(pdf_path: str, title: str, doi: str | None = None) -> dict[str, Any]:
        """Register a root-relative PDF and process one bounded batch. Repeat to resume."""
        return await service.ingest(pdf_path, title, doi)

    @tool
    async def list_indexed_papers(limit: int = 50, offset: int = 0) -> dict[str, list[dict[str, Any]]]:
        """List stored papers and indexing progress."""
        return {"papers": await service.list_papers(limit, offset)}

    @tool
    async def search_evidence(query: str, document_id: str | None = None,
                              mode: RetrievalMode = "keyword", top_k: int = 5) -> dict[str, list[dict[str, Any]]]:
        """Retrieve ranked indexed PDF passages. Semantic and hybrid require indexed embeddings."""
        rows = await service.search_evidence(query, document_id=document_id, mode=mode, limit=top_k)
        return {"evidence": rows}

    @tool
    async def inspect_evidence(chunk_id: int) -> dict[str, Any]:
        """Read an indexed passage with its document, page, offsets and checksum."""
        return await service.inspect_evidence(chunk_id)

    @tool
    async def ask_scientific_question(question: str, document_id: str | None = None,
                                      mode: RetrievalMode = "keyword", top_k: int = 5) -> dict[str, Any]:
        """Run bounded corpus QA and return supported claims, citations and a validation trace."""
        return await service.ask_corpus(question, document_id=document_id, mode=mode, top_k=top_k)

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-root",type=Path,default=ROOT / "deCitit")
    parser.add_argument("--output-root",type=Path,default=ROOT / "output" / "mcp")
    parser.add_argument("--corpus-root", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)  # stderr only; stdout belongs to MCP.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    corpus = CorpusConfig.from_env()
    if args.corpus_root is not None:
        corpus = replace(corpus, root=args.corpus_root.resolve())
    service = ResearchService(args.pdf_root,args.output_root,Settings.from_env(),corpus)
    create_server(service).run(transport="stdio")


if __name__ == "__main__":
    main()
