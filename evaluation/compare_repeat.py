"""Reuse annotations only after exact output/evidence equality, never by assumption."""
import argparse
import hashlib
import json
from pathlib import Path


def compare(previous_path, current_path, previous_reviews, output):
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    current = json.loads(current_path.read_text(encoding="utf-8"))
    if previous["model"] != current["model"] or previous["configuration"] != current["configuration"]:
        raise ValueError("Model or generation configuration changed; this is not a matched repeat.")
    key = lambda row: (row["paper"],row["variant"],row["operation"])
    old = {key(row):row for row in previous["rows"]}
    new = {key(row):row for row in current["rows"]}
    if set(old) != set(new) or len(new) != 27 or len(previous["rows"]) != 27 or len(current["rows"]) != 27:
        raise ValueError("The repeat must contain the same complete 27 operations.")
    changed = []
    for identifier, row in new.items():
        prior = old[identifier]
        if row["evidence_sha256"] != prior["evidence_sha256"]:
            raise ValueError("Evidence changed; old annotations cannot be reused.")
        if not row["valid"] or row.get("output") != prior.get("output"):
            changed.append(identifier)
    result = dict(model_and_configuration_match=True,compared=27,changed_outputs=changed,
        exact_output_matches=27-len(changed),source_results=str(previous_path),repeat_results=str(current_path))
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    if changed:
        raise ValueError("Changed or failed outputs require new factual review; see comparison report.")
    reviews = json.loads(previous_reviews.read_text(encoding="utf-8"))
    if reviews["results_sha256"] != hashlib.sha256(previous_path.read_bytes()).hexdigest():
        raise ValueError("Previous annotations have an invalid result hash.")
    reviews.update(results_sha256=hashlib.sha256(current_path.read_bytes()).hexdigest(),
        reuse_basis="All 27 generated outputs and evidence hashes matched the analyst-reviewed previous run exactly.")
    review_path = output.with_name(output.stem + "-reviews.json")
    review_path.write_text(json.dumps(reviews,indent=2),encoding="utf-8")
    print(json.dumps(result),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("previous",type=Path)
    parser.add_argument("current",type=Path)
    parser.add_argument("reviews",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    compare(args.previous,args.current,args.reviews,args.output)
