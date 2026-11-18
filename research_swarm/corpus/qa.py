"""Corpus question answering with bounded retrieval and claim verification."""
import asyncio
import hashlib
import json
import re
from time import perf_counter

from pydantic import BaseModel, Field

from research_swarm.llm import LLM
from research_swarm.prompt_loader import load_prompt
from .retrieval import EvidenceRetrieval

NUMERIC_TOKEN = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?:\s*(?:%|percent\b))?", re.I)


def numeric_tokens(text):
    return {re.sub(r"\s+", "", match.casefold()).replace("percent", "%")
            for match in NUMERIC_TOKEN.findall(text)}


class Candidate(BaseModel):
    quote: str = Field(min_length=12, max_length=500)
    chunk_id: int
    claim: str = Field(min_length=1, max_length=500)


class Draft(BaseModel):
    claims: list[Candidate] = Field(max_length=4)
    follow_up: str = Field(default="", max_length=200)


class Verdict(BaseModel):
    supported: list[int] = Field(max_length=4)


class CorpusQA:
    def __init__(self, pipeline, settings, llm=None):
        self.store = pipeline.store
        self.retrieval = EvidenceRetrieval(self.store, pipeline.config)
        self.settings = settings
        self.llm = llm if llm is not None else LLM(settings=settings)

    def context(self, question, rows, instructions):
        payload = {"question": question, "evidence": []}
        static = load_prompt("safety") + instructions + load_prompt("schema_instruction")
        budget = (self.settings.context_tokens - self.settings.max_output_tokens - 256
                  - len((static + json.dumps(Draft.model_json_schema())).encode()))
        selected = {}
        for row in rows:
            card = {"chunk_id": row["id"], "document_id": row["document_id"],
                    "title": row["title"], "page": row["page"],
                    "section": row["section"], "text": row["text"]}
            payload["evidence"].append(card)
            if len(json.dumps(payload, ensure_ascii=False).encode()) <= budget:
                selected[row["id"]] = row
            else:
                payload["evidence"].pop()
        return json.dumps(payload, ensure_ascii=False), selected

    def resolve(self, candidate, selected):
        row = selected.get(candidate.chunk_id)
        if row is None:
            return None
        parts = candidate.quote.split()
        match = re.search(r"(?<!\w)" + r"\s+".join(map(re.escape, parts)) + r"(?!\w)", row["text"]) if parts else None
        if match is None:
            return None
        quote = match.group()
        start = row["start_char"] + match.start()
        end = row["start_char"] + match.end()
        with self.store.connect() as db:
            page = db.execute("SELECT text FROM pages WHERE document_id=? AND number=?",
                              (row["document_id"], row["page"])).fetchone()
        if page is None or page["text"][start:end] != quote:
            return None
        citation = {key: row[key] for key in ("document_id", "publication_id", "title", "page", "sha256")}
        return dict(citation, chunk_id=candidate.chunk_id, quote=quote,
                    start_char=start, end_char=end)

    async def ask(self, question, *, document_id=None, mode="keyword", top_k=5, variant="evidence"):
        if variant not in {"baseline", "evidence"}:
            raise ValueError("Unknown corpus QA prompt variant.")
        started = perf_counter()
        async with asyncio.timeout(self.settings.document_timeout):
            result = await self._ask(question, document_id, mode, top_k, variant)
        return dict(result, seconds=round(perf_counter() - started, 3))

    async def _ask(self, question, document_id, mode, top_k, variant):
        instructions = load_prompt("corpus_qa", variant=variant)
        verify = load_prompt("corpus_verify")
        revision = load_prompt("corpus_revision")
        fingerprint = hashlib.sha256((instructions + verify + revision).encode()).hexdigest()
        trace, accepted = [], []
        query = question
        seen = {}
        revise = False
        for attempt in range(2):
            rows = [] if revise else await self.retrieval.search(
                query, mode=mode, limit=top_k, document_id=document_id)
            fresh = [row for row in rows if row["id"] not in seen]
            active_prompt = instructions + "\n" + revision if revise else instructions
            evidence, selected = self.context(question, fresh + list(seen.values()), active_prompt)
            seen.update((row["id"], row) for row in fresh)
            step = {"query": query, "retrieved": [row["id"] for row in rows],
                    "provided": list(selected), "omitted": len(seen) - len(selected), "revision": revise}
            trace.append(step)
            if (not fresh and not revise) or not selected:
                break
            draft = await self.llm.run("Corpus QA", active_prompt, evidence, Draft)
            candidates = []
            provenance_rejected = 0
            numeric_rejected = 0
            for candidate in draft.claims:
                citation = self.resolve(candidate, selected)
                if citation is None:
                    provenance_rejected += 1
                elif not numeric_tokens(candidate.claim) <= numeric_tokens(citation["quote"]):
                    numeric_rejected += 1
                else:
                    candidates.append({"claim": candidate.claim, "citation": citation})
            step["provenance_rejected"] = provenance_rejected
            step["numeric_rejected"] = numeric_rejected
            supported = set()
            for index, candidate in enumerate(candidates):
                packet = json.dumps({"question": question, "claims": [
                    {"index": 0, "claim": candidate["claim"], "quote": candidate["citation"]["quote"],
                     "title": candidate["citation"]["title"]}]}, ensure_ascii=False)
                verdict = await self.llm.run("Corpus claim checker", verify, packet, Verdict)
                if 0 in verdict.supported:
                    supported.add(index)
            step["semantic_rejected"] = len(candidates) - len(supported)
            accepted.extend(row for index, row in enumerate(candidates)
                            if index in supported and row not in accepted)
            follow_up = draft.follow_up.strip()
            step["requested_follow_up"] = follow_up or None
            if not follow_up or follow_up.casefold() in {question.strip().casefold(), query.strip().casefold()}:
                if accepted or not draft.claims or attempt:
                    break
                revise = True
            else:
                query = follow_up
        return {"status": "supported_claims" if accepted else "insufficient_evidence",
                "claims": accepted, "trace": trace, "prompt_version": fingerprint,
                "coverage": "Ranked excerpts within a fixed context and two draft attempts. Semantic support is model-assessed."}
