"""Run live corpus QA through the MCP SDK with locally cached evaluation PDFs."""
import argparse
import asyncio
import hashlib
import json
import os
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters
import pymupdf

from research_swarm.config import ROOT


async def main(evidence_only=False):
    papers = ROOT / ".runtime" / "evaluation-papers"
    sources = json.loads((ROOT / "evaluation" / "sources.json").read_text(encoding="utf-8"))
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "research_swarm.mcp_server", "--pdf-root", str(papers),
              "--corpus-root", str(ROOT / ".runtime" / "rag-demo")],
        env={**os.environ, "LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "llama3.2:latest",
             "LOCAL_TEST_MODE": "false", "ALLOW_PAID_API": "false", "LLM_CACHE_ENABLED": "false"},
    )
    async def call(client, name, args):
        result = await client.call_tool(name, args)
        if result.is_error:
            raise RuntimeError(result.content)
        return result.structured_content

    async with Client(params, read_timeout_seconds=240) as client:
        imported = []
        for source in sources:
            pdf_path = papers / (source["id"] + ".pdf")
            if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != source["pdf_sha256"]:
                raise ValueError(f"Unexpected PDF checksum for {source['id']}")
            for _ in range(2000):
                row = await call(client, "ingest_paper", {"pdf_path": source["id"] + ".pdf", "title": source["title"]})
                if row["status"] == "complete":
                    imported.append(row)
                    break
                if row["status"] != "pending":
                    raise RuntimeError(row)
            else:
                raise RuntimeError(f"Indexing did not complete for {source['id']}")

    async with Client(params, read_timeout_seconds=240) as client:
        tools = [tool.name for tool in (await client.list_tools()).tools]
        listing = (await call(client, "list_indexed_papers", {}))["papers"]
        assert {row["id"] for row in imported} <= {row["id"] for row in listing}
        cases = [
            ("What architectural mechanism replaces recurrence and convolutions in the Transformer?", imported[0]["id"]),
            ("What BLEU score did the Transformer achieve on WMT 2014 English-to-German translation?", imported[0]["id"]),
            ("What GPU memory reduction did LoRA report compared with GPT-3 175B fine-tuned with Adam?", imported[2]["id"]),
            ("What did the Transformer achieve for English-to-German BLEU and what GPU memory reduction did LoRA report?", None),
            ("xylophonezz", None),
        ]
        results = []
        originals = {row["id"]: papers / (source["id"] + ".pdf") for row, source in zip(imported, sources)}
        def check_page(reference, quote):
            with pymupdf.open(originals[reference["document_id"]]) as pdf:
                page = pdf[reference["page"] - 1].get_text("text", sort=True)
            assert page[reference["start_char"]:reference["end_char"]] == quote

        for question, scope in cases:
            if evidence_only:
                response = await call(client, "search_evidence", {"query": question, "document_id": scope, "top_k": 3})
                evidence = response["evidence"]
                for row in evidence:
                    detail = await call(client, "inspect_evidence", {"chunk_id": row["id"]})
                    assert detail["text"] == row["text"]
                    check_page(row, row["text"])
                results.append({"question": question, "evidence": evidence})
                continue
            result = await client.call_tool("ask_scientific_question",
                                            {"question": question, "document_id": scope})
            if result.is_error:
                results.append({"question": question, "error": [item.text for item in result.content]})
                continue
            answer = result.structured_content
            for claim in answer["claims"]:
                citation = claim["citation"]
                check_page(citation, citation["quote"])
            results.append({"question": question, **answer})

    name = "corpus-evidence-live.json" if evidence_only else "corpus-rag-live.json"
    path = ROOT / "evaluation" / "results" / name
    path.write_text(json.dumps({"tools": tools, "indexed": listing, "answers": results},
                               indent=2, ensure_ascii=False), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-only", action="store_true",
                        help="Verify SDK retrieval and source pages without generation.")
    asyncio.run(main(parser.parse_args().evidence_only))
