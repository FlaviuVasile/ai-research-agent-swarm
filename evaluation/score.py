"""Aggregate inspectable analyst annotations; never infer factual truth from keywords."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean


def score(results, reviews, rubric):
    if reviews["results_sha256"] != hashlib.sha256(results.read_bytes()).hexdigest():
        raise ValueError("Reviews do not match these exact experiment results.")
    data = json.loads(results.read_text(encoding="utf-8"))
    summary = {}
    annotations = reviews["rows"]
    keys = lambda rows: [(r["paper"],r["variant"],r["operation"]) for r in rows]
    if len(set(keys(annotations))) != len(annotations) or set(keys(annotations)) != set(keys(data["rows"])):
        raise ValueError("Reviews must correspond one-to-one with experiment rows.")
    for row in annotations:
        if not 0 <= row["unsupported_claims"] <= row["factual_claims"] or not 0 <= row["correct_citations"] <= row["citations"]:
            raise ValueError("Invalid claim or citation counts.")
        if row["operation"] == "summary" and (row["reference_facts"] != len(set(row["reference_indices"]))
            or any(not 1 <= i <= len(rubric["summary_reference_facts"][row["paper"]]) for i in row["reference_indices"])):
            raise ValueError("Invalid reference-fact annotations.")
    for variant in ("baseline", "fields", "evidence"):
        for operation in ("summary", "questions", "literature"):
            rows = [r for r in data["rows"] if r["variant"] == variant and r["operation"] == operation]
            selected = [r for r in annotations if r["variant"] == variant and r["operation"] == operation]
            if len(rows) != 3 or len(selected) != 3:
                raise ValueError("Every variant/operation requires three outputs and reviews.")
            factual = sum(r["factual_claims"] for r in selected)
            unsupported = sum(r["unsupported_claims"] for r in selected)
            citations = sum(r["citations"] for r in selected)
            correct = sum(r["correct_citations"] for r in selected)
            item = dict(valid_fraction=sum(r["valid"] for r in rows)/len(rows),
                factual_claims=factual, unsupported_claims=unsupported,
                supported_precision=(factual-unsupported)/factual if factual else None,
                hallucination_rate=unsupported/factual if factual else None,
                citations=citations, citation_precision=correct/citations if citations else None,
                mean_seconds=mean(r["seconds"] for r in rows),
                generated_tokens=sum(m.get("eval_count",0) for r in rows for m in r["usage"]),
                prompt_tokens=sum(m.get("prompt_eval_count",0) for r in rows for m in r["usage"]))
            if operation == "summary":
                item["reference_recall"] = sum(r["reference_facts"] for r in selected)/sum(
                    len(facts) for facts in rubric["summary_reference_facts"].values())
            else:
                item["task_checks_passed"] = sum(r["task_pass"] for r in selected)
            if operation == "questions":
                item["category_correct"] = sum(r["category_correct"] for r in selected)
            summary[f"{variant}/{operation}"] = item
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("reviews", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = score(args.results, json.loads(args.reviews.read_text(encoding="utf-8")),
        json.loads(Path(__file__).with_name("rubric.json").read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(json.dumps(output,indent=2))
