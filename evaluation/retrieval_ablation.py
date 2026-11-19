"""Compare lexical and embedding retrieval with explicit query-processing controls."""
import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from research_swarm.corpus.config import CorpusConfig
from research_swarm.corpus.ingest import CorpusPipeline
from research_swarm.corpus.retrieval import EvidenceRetrieval
from research_swarm.corpus.spans import question_parts
from evaluation.span_benchmark import FIXTURES, matches


ARMS = (
    ("bm25_raw", "keyword", False, False),
    ("bm25_normalized", "keyword", True, False),
    ("bm25_normalized_clause_split", "keyword", True, True),
    ("semantic_clause_split", "semantic", None, True),
    ("hybrid_clause_split", "hybrid", None, True),
)


def retrieval_metrics(returned_ids, target_groups, cutoff=10):
    ranked = list(dict.fromkeys(returned_ids))[:cutoff]
    target_ranks = [
        next((rank for rank, identifier in enumerate(ranked, 1) if identifier in group), None)
        for group in target_groups
    ]
    if not target_groups:
        return {
            "target_ranks": [],
            "target_recall": None,
            "precision_at_k": None,
            "recall_at_k": None,
            "mrr_targets": None,
        }
    relevant = set().union(*target_groups)
    found = relevant.intersection(ranked)
    return {
        "target_ranks": target_ranks,
        "target_recall": sum(rank is not None for rank in target_ranks) / len(target_ranks),
        "precision_at_k": len(found) / cutoff,
        "recall_at_k": len(found) / len(relevant) if relevant else None,
        "mrr_targets": mean(1 / rank if rank is not None else 0 for rank in target_ranks),
    }


async def _search(retrieval, query, mode, top_k, normalize_query):
    if mode == "keyword":
        return retrieval.keyword(query, limit=top_k, normalize_query=normalize_query)
    return await retrieval.search(query, mode=mode, limit=top_k)


async def _run_arm(retrieval, arm, top_k, target_groups):
    _, mode, normalize_query, decompose = arm
    cases = []
    for split, question, expected in FIXTURES:
        queries = question_parts(question) if decompose else [question]
        started = perf_counter()
        rankings = [
            await _search(retrieval, query, mode, top_k, normalize_query)
            for query in queries
        ]
        ordered_ids = []
        for rank in range(top_k):
            for ranking in rankings:
                if rank < len(ranking):
                    identifier = ranking[rank]["id"]
                    if identifier not in ordered_ids:
                        ordered_ids.append(identifier)
                if len(ordered_ids) == top_k:
                    break
            if len(ordered_ids) == top_k:
                break
        case_targets = target_groups[question]
        cases.append({
            "split": split,
            "question": question,
            "target_count": len(expected),
            "relevant_passage_count": len(set().union(*case_targets)) if case_targets else 0,
            "returned_ids": ordered_ids,
            **retrieval_metrics(ordered_ids, case_targets, top_k),
            "seconds": round(perf_counter() - started, 4),
        })
    answerable = [case for case in cases if case["target_count"]]
    metrics = {}
    for key in ("target_recall", "precision_at_k", "recall_at_k", "mrr_targets", "seconds"):
        metrics[key] = mean(case[key] for case in answerable)
    return {
        "retriever": mode,
        "normalized_query": normalize_query,
        "clause_decomposition": decompose,
        "top_k_per_part": top_k,
        "answerable_cases": len(answerable),
        "metrics": metrics,
        "cases": cases,
    }


async def run(corpus, output, top_k, index_embeddings):
    if not 1 <= top_k <= 50:
        raise ValueError("Top-k must be between 1 and 50.")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing experiment output: {output}")
    pipeline = CorpusPipeline(CorpusConfig(root=corpus))
    retrieval = EvidenceRetrieval(pipeline.store, pipeline.config)
    documents = pipeline.store.documents(limit=500)
    if len(documents) < 3 or any(row["status"] != "complete" for row in documents):
        raise ValueError("The isolated evaluation corpus must contain at least three complete documents.")

    with pipeline.store.connect() as db:
        rows = db.execute(
            "SELECT e.*,p.title,d.sha256 FROM passages e "
            "JOIN documents d ON d.id=e.document_id "
            "JOIN publications p ON p.id=d.publication_id"
        ).fetchall()
    evidence = [dict(row) for row in rows]
    target_groups = {}
    for _, question, targets in FIXTURES:
        groups = []
        for target in targets:
            identifiers = {row["id"] for row in evidence if matches(row, target)}
            if not identifiers:
                raise ValueError(f"No stored passage matches the source annotation: {question}")
            groups.append(identifiers)
        target_groups[question] = groups

    report = {
        "schema": "scientific-retrieval-ablation-v1",
        "annotation_status": "Existing source-anchored pilot labels; human review pending.",
        "corpus_documents": len(documents),
        "scientific_questions": len(FIXTURES),
        "top_k": top_k,
        "arms": {},
    }
    if index_embeddings:
        before = perf_counter()
        indexed = 0
        for _ in range(100):
            count = await retrieval.index()
            indexed += count
            if count == 0:
                break
        else:
            raise RuntimeError("Embedding indexing exceeded the bounded 100-batch limit.")
        report["embedding_index"] = {
            "model": pipeline.config.embedding_model,
            "new_vectors": indexed,
            "seconds": round(perf_counter() - before, 3),
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    for arm in ARMS:
        result = await _run_arm(retrieval, arm, top_k, target_groups)
        report["arms"][arm[0]] = result
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(arm[0], result["metrics"], flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--index-embeddings", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.corpus, args.output, args.top_k, args.index_embeddings))
