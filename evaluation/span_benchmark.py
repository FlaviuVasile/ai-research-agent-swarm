"""Paired corpus retrieval and generation measurements against reviewed source anchors."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from itertools import zip_longest
from time import perf_counter
import unicodedata
import re

from research_swarm.config import Settings
from research_swarm.corpus.config import CorpusConfig
from research_swarm.corpus.ingest import CorpusPipeline
from research_swarm.corpus.qa import CorpusQA
from research_swarm.corpus.spans import query_terms, question_parts

FIXTURES = [
    ("development", "What BLEU score did Transformer big achieve on WMT 2014 English-to-German?",
     [("Attention Is All You Need", (1, 8), ("28.4", "bleu"))]),
    ("development", "What English-to-German BLEU did Transformer achieve and what GPU memory reduction did LoRA report?",
     [("Attention Is All You Need", (1, 8), ("28.4", "bleu")),
      ("LoRA", (1,), ("gpu memory requirement", "3 times"))]),
    ("development", "What was the human participant dropout rate in the randomized clinical trial?", []),
    ("held_out", "What is the AdaMax variant of Adam based on?",
     [("Adam:", (1, 9), ("adamax", "infinity norm"))]),
    ("held_out", "What French BLEU score does the Transformer abstract report for a single model?",
     [("Attention Is All You Need", (1,), ("41.8", "bleu"))]),
    ("held_out", "Does LoRA add inference latency according to its conclusion?",
     [("LoRA", (12,), ("neither introduces inference latency",))]),
]


def normalized(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    return " ".join(text.split())


def matches(row, target):
    title, pages, fragments = target
    text = normalized(row.get("quote", row.get("text", "")))
    return row["title"].startswith(title) and row["page"] in pages and all(s in text for s in fragments)


async def main(args):
    pipeline = CorpusPipeline(CorpusConfig(root=args.corpus))
    if len(pipeline.store.documents()) < 3:
        raise ValueError("Index the three benchmark PDFs before running this experiment.")
    settings = replace(Settings.from_env(), provider="ollama", local_test_mode=False,
                       allow_paid_api=False, cache_enabled=False, llm_timeout=90)
    qa = CorpusQA(pipeline, settings)
    fixtures = FIXTURES
    report = {"retrieval": {}, "generation": {}}
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    experiments = [("keyword",False,False), ("keyword",True,False), ("keyword",True,True)]
    if args.embeddings:
        while await qa.retrieval.index():
            pass
        experiments += [("semantic",False,False), ("hybrid",False,False)]
    for mode, clean, split in experiments:
        cases = []
        for group, question, expected in fixtures:
            started = perf_counter()
            lists = []
            for part in question_parts(question) if split else [question]:
                query = " ".join(sorted(query_terms(part))) if clean else part
                lists.append(await qa.retrieval.search(query or part, mode=mode, limit=10))
            # Round-robin top ten across clause rankings, including any uneven tails.
            unique = list(dict.fromkeys(row["id"] for round_rows in zip_longest(*lists)
                                        for row in round_rows if row is not None))[:10]
            rows = pipeline.store.evidence_many(unique)
            ranks = [next((i for i, row in enumerate(rows,1) if matches(row,target)), None)
                     for target in expected]
            cases.append({"split":group,"question":question,"target_ranks":ranks,"returned_ids":unique,
                          "top10_target_recall":sum(rank is not None for rank in ranks)/len(ranks) if ranks else None,
                          "seconds":round(perf_counter()-started,4)})
        report["retrieval"][f"{mode}/clean={clean}/clauses={split}"] = cases
        save()
    if not args.live:
        return
    for label, variant, split in [("short", "baseline", True), ("evidence_first", "evidence", True),
                                   ("no_decomposition", "evidence", False)]:
        cases = []
        report["generation"][label] = cases
        for group, question, expected in fixtures:
            if label == "no_decomposition" and len(expected) != 2:
                continue
            try:
                answer = await qa.ask(question, variant=variant, decompose=split)
            except (TimeoutError,ValueError) as exc:
                answer = {"error": str(exc)}
            citations = [claim["citation"] for claim in answer.get("claims", [])]
            coverage = [any(matches(citation,target) for citation in citations) for target in expected]
            cases.append({"split":group,"question":question,"targets":expected,"matched_targets":coverage,
                          "successful_abstention":not expected and answer.get("status") == "insufficient_evidence",
                          "answer":answer})
            save()
            print(label,group,answer.get("status",answer.get("error")),coverage,flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path(".runtime/rag-demo"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/span-benchmark.json"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--embeddings", action="store_true")
    asyncio.run(main(parser.parse_args()))
