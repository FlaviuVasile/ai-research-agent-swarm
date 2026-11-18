"""Evaluate ranking against page-and-text labels on the local demo corpus."""
import asyncio
import json
from statistics import mean
from time import perf_counter

from research_swarm.config import ROOT
from research_swarm.corpus.config import CorpusConfig
from research_swarm.corpus.ingest import CorpusPipeline
from research_swarm.corpus.retrieval import EvidenceRetrieval

# Page numbers refer to the pinned PDFs in sources.json.
LABELS = [
    ("What BLEU score did the Transformer achieve on WMT 2014 English-to-German translation?",
     [(0, 1, "28.4 bleu")]),
    ("What GPU memory reduction did LoRA report compared with GPT-3 175B fine-tuned with Adam?",
     [(2, 1, "by 3 times")]),
    ("Which estimates are used in Adam's adaptive stochastic optimization method?",
     [(1, 1, "adaptive estimates of lower-order mo- ments")]),
    ("What did the Transformer achieve for English-to-German BLEU and what GPU memory reduction did LoRA report?",
     [(0, 1, "28.4 bleu"), (2, 1, "by 3 times")]),
    ("What was the participant dropout rate in the randomized clinical trial?", []),
]


async def main():
    root = ROOT / ".runtime" / "rag-demo"
    pipeline = CorpusPipeline(CorpusConfig(root=root))
    search = EvidenceRetrieval(pipeline.store, pipeline.config)
    sources = json.loads((ROOT / "evaluation" / "sources.json").read_text(encoding="utf-8"))
    with pipeline.store.connect() as db:
        rows = db.execute("SELECT e.*,d.sha256 FROM passages e JOIN documents d ON e.document_id=d.id").fetchall()
    fixtures = []
    for question, labels in LABELS:
        relevant = set()
        for source, page, phrase in labels:
            matches = {row["id"] for row in rows if row["sha256"] == sources[source]["pdf_sha256"]
                       and row["page"] == page and phrase in " ".join(row["text"].casefold().split())}
            if not matches:
                raise ValueError(f"No passage matches annotation {source}, page {page}, {phrase}")
            relevant.update(matches)
        fixtures.append((question, relevant))
    while await search.index():
        pass

    report = {}
    for mode in ("keyword", "semantic", "hybrid"):
        cases = []
        for question, relevant in fixtures:
            started = perf_counter()
            hits = await search.search(question, mode=mode, limit=5)
            ids = [row["id"] for row in hits]
            positions = [rank for rank, item in enumerate(ids, 1) if item in relevant]
            cases.append({"question": question, "expected_ids": sorted(relevant), "returned_ids": ids,
                          "precision_at_5": len(positions) / 5,
                          "recall_at_5": len(positions) / len(relevant) if relevant else None,
                          "reciprocal_rank": 1 / positions[0] if positions else 0,
                          "seconds": round(perf_counter() - started, 4)})
        answerable = [case for case in cases if case["expected_ids"]]
        report[mode] = {"cases": cases, "mean_answerable": {
            key: mean(case[key] for case in answerable)
            for key in ("precision_at_5", "recall_at_5", "reciprocal_rank", "seconds")}}
    path = ROOT / "evaluation" / "results" / "corpus-retrieval-live.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    asyncio.run(main())
