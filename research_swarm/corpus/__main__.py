"""CLI: python -m research_swarm.corpus --help"""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path

from .config import CorpusConfig
from .ingest import CorpusPipeline
from .retrieval import EvidenceRetrieval, evidence_reference


def main():
    parser = argparse.ArgumentParser(description="Local academic corpus foundation; no paid AI calls.")
    parser.add_argument("--root", type=Path, help="Corpus root containing research/ and deCitit/")
    commands = parser.add_subparsers(dest="command",required=True)
    add = commands.add_parser("add", help="Register metadata and import a lawfully held local PDF")
    add.add_argument("pdf", type=Path)
    add.add_argument("--title", required=True)
    add.add_argument("--doi")
    add.add_argument("--author", action="append", default=[])
    add.add_argument("--year", type=int)
    listing = commands.add_parser("list")
    listing.add_argument("--offset",type=int,default=0)
    commands.add_parser("ingest",help="Run one bounded resumable page-processing slice")
    commands.add_parser("index",help="Run one bounded local embedding slice; requires installed embedding model")
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--semantic",action="store_true")
    search.add_argument("--publication",type=int)
    search.add_argument("--limit",type=int,default=10)
    evidence = commands.add_parser("evidence")
    evidence.add_argument("id",type=int)
    reset = commands.add_parser("reset",help="Discard one document's derived pages/vectors and requeue; keep PDF/metadata")
    reset.add_argument("document_id")
    args = parser.parse_args()
    config = CorpusConfig.from_env()
    if args.root:
        config = replace(config,root=args.root)
    pipeline = CorpusPipeline(config)
    retrieval = EvidenceRetrieval(pipeline.store, config)
    try:
        if args.command == "add":
            publication = pipeline.store.add_publication(args.title,args.doi,args.author,args.year)
            with args.pdf.open("rb") as stream:
                output = {"publication_id":publication,"document_id":pipeline.collect(publication,stream)}
        elif args.command == "list":
            output = pipeline.store.documents(offset=args.offset)
        elif args.command == "ingest":
            output = pipeline.run(lambda document,page,total: print(f"{document}: page {page}/{total}"))
        elif args.command == "index":
            output = {"passages_indexed":asyncio.run(retrieval.index())}
        elif args.command == "reset":
            pipeline.store.reset(args.document_id)
            output = {"reset":args.document_id}
        elif args.command == "evidence":
            output = pipeline.store.evidence(args.id)
            output["citation"] = evidence_reference(output)
        else:
            rows = (asyncio.run(retrieval.semantic(args.query,args.limit,args.publication)) if args.semantic
                    else retrieval.keyword(args.query,args.limit,args.publication))
            output = [dict(row,citation=evidence_reference(row)) for row in rows]
        print(json.dumps(output,indent=2,ensure_ascii=False))
    except (ValueError,OSError) as exc:
        parser.exit(1, f"Corpus operation failed: {exc}\n")


if __name__ == "__main__":
    main()
