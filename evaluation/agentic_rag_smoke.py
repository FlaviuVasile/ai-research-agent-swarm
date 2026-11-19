"""Reproduce the live shared-QA workflow through an official MCP stdio client."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from research_swarm.config import ROOT, Settings

PAPERS = (
    ("1412.6980v9.pdf", "Adam: A Method for Stochastic Optimization"),
    ("1706.03762v7.pdf", "Attention Is All You Need"),
    ("2106.09685v2.pdf", "LoRA: Low-Rank Adaptation of Large Language Models"),
)
QUESTIONS = {
    "simple_numerical": "What default values does Adam use for beta1 and beta2?",
    "false_premise": "Why did the Transformer use recurrent layers?",
    "cross_paper": (
        "Compare the attention mechanism in Attention Is All You Need with the low-rank updates in the LoRA paper."
    ),
    "unanswerable": "What participant dropout rate was measured in the randomized clinical trial?",
}
EXPECTED_TOOLS = {
    "extract_paper_text", "summarize_paper", "find_research_questions", "search_literature",
    "analyze_paper", "get_analysis_result", "ingest_paper", "list_indexed_papers",
    "search_evidence", "inspect_evidence", "ask_scientific_question",
}


def verify_citations(corpus_root: Path, answer: dict) -> dict:
    citations = {}
    for evidence in answer.get("evidence", []):
        citation = evidence.get("citation")
        if citation:
            key = (citation["document_id"], citation["page"], citation["start_char"], citation["end_char"])
            citations[key] = citation
    for claim in answer.get("claims", []):
        for citation in claim.get("citations", [claim.get("citation")]):
            if citation:
                key = (citation["document_id"], citation["page"], citation["start_char"], citation["end_char"])
                citations[key] = citation

    if not citations:
        return {"citation_count": 0, "exact_provenance": None}

    with sqlite3.connect(corpus_root / "research" / "corpus.sqlite3") as db:
        db.row_factory = sqlite3.Row
        for citation in citations.values():
            row = db.execute(
                "SELECT pg.text,d.sha256 FROM pages pg JOIN documents d ON d.id=pg.document_id "
                "WHERE pg.document_id=? AND pg.number=?",
                (citation["document_id"], citation["page"]),
            ).fetchone()
            if (row is None or row["sha256"] != citation["sha256"]
                    or row["text"][citation["start_char"]:citation["end_char"]] != citation["quote"]):
                raise AssertionError("MCP returned a citation that does not match the stored PDF page.")
    return {"citation_count": len(citations), "exact_provenance": True}


async def run(corpus_root: Path, output: Path, pdf_root: Path, question_cases=None) -> dict:
    settings = Settings.from_env()
    if settings.provider != "ollama" or settings.local_test_mode:
        raise ValueError("This smoke run requires the configured real local Ollama provider.")
    if corpus_root.exists():
        raise FileExistsError(f"Refusing to overwrite an existing corpus: {corpus_root}")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite an existing result: {output}")
    if question_cases is not None and (
        not question_cases or any(name not in QUESTIONS for name in question_cases)
    ):
        raise ValueError(f"Select one or more question cases from: {', '.join(QUESTIONS)}.")
    selected_questions = (
        {name: question for name, question in QUESTIONS.items()
         if question_cases is None or name in question_cases}
    )
    missing = [filename for filename, _ in PAPERS if not (pdf_root / filename).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing local evaluation PDFs: {', '.join(missing)}")

    env = {key: value for key, value in os.environ.items()
           if not key.startswith("OPENAI_") and not key.startswith("OPENALEX_")}
    env.update({
        "LLM_PROVIDER": "ollama",
        "OLLAMA_MODEL": settings.model,
        "OLLAMA_BASE_URL": settings.ollama_url,
        "OLLAMA_CONTEXT_TOKENS": str(settings.context_tokens),
        "LLM_TIMEOUT_SECONDS": str(settings.llm_timeout),
        "DOCUMENT_TIMEOUT_SECONDS": str(settings.document_timeout),
        "LLM_CACHE_ENABLED": "false",
        "ALLOW_PAID_API": "false",
        "LOCAL_TEST_MODE": "false",
        "CORPUS_ROOT": str(corpus_root),
    })
    if settings.ollama_gpu_layers is not None:
        env["OLLAMA_GPU_LAYERS"] = str(settings.ollama_gpu_layers)
    else:
        env.pop("OLLAMA_GPU_LAYERS", None)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "research_swarm.mcp_server", "--pdf-root", str(pdf_root),
              "--output-root", str(corpus_root / "output"), "--corpus-root", str(corpus_root)],
        cwd=ROOT,
        env=env,
    )
    report = {
        "schema": "agentic-rag-live-mcp-smoke-v1",
        "model": settings.model,
        "provider": settings.provider,
        "context_tokens": settings.context_tokens,
        "llm_timeout_seconds": settings.llm_timeout,
        "cache_enabled": False,
        "corpus_root": str(corpus_root),
        "source_papers": [{"file": name, "title": title} for name, title in PAPERS],
        "tool_count": 0,
        "question_cases": list(selected_questions),
        "questions": {},
    }

    async with Client(params, read_timeout_seconds=settings.document_timeout + 30) as client:
        tools = (await client.list_tools()).tools
        names = {tool.name for tool in tools}
        if names != EXPECTED_TOOLS:
            raise AssertionError(f"Unexpected MCP tool set: {sorted(names)}")
        report["tool_count"] = len(tools)
        indexed = {}
        for filename, title in PAPERS:
            document = None
            for attempt in range(3):
                result = await client.call_tool(
                    "ingest_paper", {"pdf_path": filename, "title": title}
                )
                if result.is_error:
                    raise RuntimeError(f"MCP ingestion failed for {filename}.")
                document = result.structured_content
                if document["status"] == "complete":
                    break
            if document is None or document["status"] != "complete":
                raise RuntimeError(f"MCP ingestion did not complete for {filename}.")
            indexed[title] = document["id"]
        report["indexed_documents"] = indexed

        for name, question in selected_questions.items():
            result = await client.call_tool("ask_scientific_question", {"question": question})
            if result.is_error:
                raise RuntimeError(f"MCP scientific QA failed for the {name} case.")
            answer = result.structured_content
            report["questions"][name] = {
                "question": question,
                "response": answer,
                "provenance": verify_citations(corpus_root, answer),
            }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf-root", type=Path, default=ROOT / ".runtime" / "evaluation-papers")
    parser.add_argument("--case", choices=tuple(QUESTIONS), action="append",
                        help="Run selected question case(s); omit to run the full smoke set.")
    arguments = parser.parse_args()
    result = asyncio.run(run(arguments.corpus_root.resolve(), arguments.output.resolve(),
                             arguments.pdf_root.resolve(), arguments.case))
    print(json.dumps({"tool_count": result["tool_count"], "model": result["model"],
                      "questions": {
                          key: {"status": value["response"]["status"],
                                "seconds": value["response"]["seconds"],
                                **value["provenance"]}
                          for key, value in result["questions"].items()
                      }}, indent=2))
