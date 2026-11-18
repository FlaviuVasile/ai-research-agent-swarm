"""Real, local, uncached paired prompt experiment. Run as a module."""
import argparse
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from time import perf_counter

from research_swarm.config import Settings
from research_swarm.llm import LLM
from research_swarm.agents.summary_agent import SummaryAgent
from research_swarm.agents.questions_agent import QuestionsAgent
from research_swarm.models import Relevance
from research_swarm.prompt_loader import load_prompt, prompt_fingerprint, VARIANTS
from research_swarm.telemetry import observe


async def run(output):
    if output.exists():
        raise ValueError("Choose a new results filename; previous experiments are never overwritten.")
    folder = Path(__file__).resolve().parent
    papers = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
    settings = replace(Settings.from_env(), provider="ollama", local_test_mode=False,
        allow_paid_api=False, openai_key="", cache_enabled=False,
        research_mode="FULL_RESEARCH_MODE", chunk_tokens=2000,
        max_questions=1, summary_output_tokens=256, llm_timeout=120)
    identity = await LLM(settings=settings).provider.identity()
    report = dict(model=identity, prompt_fingerprint=prompt_fingerprint(),
        configuration={key:getattr(settings,key) for key in ("context_tokens","summary_context_tokens",
            "summary_output_tokens","max_output_tokens","ollama_gpu_layers","chunk_tokens")},
        cache_enabled=False, journal_enabled=False, temperature=0,
        scope="Three real paper abstracts, one paired pass; not full-paper or held-out validation", rows=[])
    output.parent.mkdir(parents=True, exist_ok=True)
    for index, paper in enumerate(papers):
        # Rotate order to reduce consistent first-variant cold-start advantage.
        variants = VARIANTS[index:] + VARIANTS[:index]
        for variant in variants:
            config = replace(settings, prompt_variant=variant)
            llm = LLM(settings=config)
            for operation in ("summary", "questions", "literature"):
                metrics = []
                def event(kind, **fields):
                    if kind == "request_metrics":
                        metrics.append(fields)
                row = dict(paper=paper["id"], variant=variant, operation=operation,
                    evidence_sha256=hashlib.sha256(paper["evidence"].encode()).hexdigest())
                started = perf_counter()
                try:
                    with observe(event):
                        if operation == "summary":
                            result, _ = await SummaryAgent(llm, config).summarize(paper["evidence"])
                        elif operation == "questions":
                            # Fixed summary across variants: no upstream generated-output confound.
                            result = (await QuestionsAgent(llm, 1, variant).find(paper["evidence"],
                                "Summary omitted for controlled evidence-only comparison.")).model_dump()
                        else:
                            result = (await llm.run("Literature Search Agent", load_prompt("literature",variant=variant),
                                json.dumps({"question":"How can the proposed method improve computational efficiency?",
                                    "title":paper["title"]}), Relevance)).model_dump()
                    row.update(output=result, valid=True)
                except Exception as exc:
                    row.update(error=str(exc), valid=False)
                row.update(seconds=perf_counter()-started, usage=metrics)
                report["rows"].append(row)
                output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
                print(paper["id"],variant,operation,row["valid"],round(row["seconds"],2),flush=True)
    failures = sum(not row["valid"] for row in report["rows"])
    if failures:
        raise RuntimeError(f"{failures} experiment operations failed; partial results retained at {output}.")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
