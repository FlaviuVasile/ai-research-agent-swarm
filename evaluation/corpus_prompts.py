"""Compare prompts and retrieval on fixed local corpus QA probes."""
import asyncio
from dataclasses import replace
import json

from research_swarm.config import ROOT, Settings
from research_swarm.corpus.config import CorpusConfig
from research_swarm.corpus.ingest import CorpusPipeline
from research_swarm.corpus.qa import CorpusQA


CASES = [
    ("What BLEU score did the Transformer achieve on WMT 2014 English-to-German translation?", "28.4"),
    ("What GPU memory reduction did LoRA report compared with GPT-3 175B fine-tuned with Adam?", "3 times"),
    ("What was the participant dropout rate in the randomized clinical trial?", None),
]


async def main():
    qa = CorpusQA(CorpusPipeline(CorpusConfig(root=ROOT / ".runtime" / "rag-demo")),
                  replace(Settings(), cache_enabled=False))
    results = []
    for variant, mode in (("baseline", "keyword"), ("evidence", "keyword"), ("evidence", "hybrid")):
        for question, expected in CASES:
            try:
                result = await qa.ask(question, mode=mode, variant=variant)
            except (TimeoutError, ValueError) as exc:
                result = {"error": str(exc)}
            results.append({"variant": variant, "retrieval": mode, "question": question,
                            "expected": expected, "result": result})
    path = ROOT / "evaluation" / "results" / "corpus-prompts-live.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    asyncio.run(main())
