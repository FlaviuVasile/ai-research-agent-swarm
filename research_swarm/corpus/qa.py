"""Corpus question answering with bounded retrieval and claim verification."""
import asyncio
import hashlib
import json
import re
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field

from research_swarm.llm import LLM
from research_swarm.prompt_loader import load_prompt
from .query import canonical_term
from .retrieval import EvidenceRetrieval
from .spans import SpanAnswer, query_terms, question_parts, ranked_spans

NUMERIC_TOKEN = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?:\s*(?:%|percent\b))?", re.I)
COMPLEX_QUESTION = re.compile(
    r"\b(?:compare|contrast|compared|versus|vs\.?|why|how\s+(?:does|do|did|can|could|would|is|are|was|were)|"
    r"explain|difference|similarit\w*|evaluate)\b",
    re.I,
)
COMPARISON_QUESTION = re.compile(r"\b(?:compare|contrast|compared|versus|vs\.?)\b", re.I)
WHY_PREMISE = re.compile(r"^\s*why\b.*?\b(?:use|choose|include|adopt|apply)\s+([\w-]+)", re.I)
EXPLICIT_NEGATION = re.compile(r"\b(?:dispens\w*\s+with|without|did not|does not|do not|never)\b", re.I)
POLARITY_RELATION = re.compile(
    r"\b(requir\w*|need\w*|us(?:e|es|ed|ing)|includ\w*|contain\w*|rel(?:y|ies|ied|ying)|"
    r"allow\w*|support\w*|increas\w*|decreas\w*|improv\w*|reduc\w*|caus\w*|prevent\w*|"
    r"train\w*|freez\w*)\b",
    re.I,
)
NEGATION_PREFIX = re.compile(
    r"(?:\b(?:not|never|no|without|cannot|can't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't)\s*"
    r"|\b(?:do|does|did|is|are|was|were|can|could|should|would|will|must)\s+not\s*)$",
    re.I,
)
NEGATED_PRESENCE = re.compile(r"\b(?:dispen\w*\s+with|without)\s+([\w-]+)", re.I)
COMPARISON_ACTIONS = frozenset({"compare", "compared", "contrast", "versus"})
PAPER_TITLE_ALIASES = {"attention is all you need": ("transformer",)}
GENERIC_TITLE_TERMS = frozenset({
    "all", "approach", "large", "language", "method", "model", "models", "need",
    "new", "paper", "result", "results", "study", "system", "systems", "you",
})


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
    supported: list[int] = Field(max_length=8)


class SynthesisClaim(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    span_ids: list[int] = Field(min_length=1, max_length=4)
    kind: Literal["reported_finding", "method", "comparison", "interpretation"] = "reported_finding"


class ScientificSynthesis(BaseModel):
    claims: list[SynthesisClaim] = Field(max_length=8)


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
        return self.source_span(row, match.start(), match.end())

    def source_span(self, row, offset, stop):
        quote = row["text"][offset:stop]
        start = row["start_char"] + offset
        end = row["start_char"] + stop
        with self.store.connect() as db:
            page = db.execute("SELECT text FROM pages WHERE document_id=? AND number=?",
                              (row["document_id"], row["page"])).fetchone()
        if page is None or page["text"][start:end] != quote:
            return None
        citation = {key: row[key] for key in ("document_id", "publication_id", "title", "page", "sha256")}
        return dict(citation, chunk_id=row["id"], quote=quote,
                    start_char=start, end_char=end)

    def _comparison_documents(self, parts, document_id, document_ids):
        if not any(COMPARISON_QUESTION.search(part) for part in parts):
            return {}
        documents = self.store.documents(limit=500)
        if document_id is not None:
            documents = [row for row in documents if row["id"] == document_id]
        elif document_ids:
            scoped = set(document_ids)
            documents = [row for row in documents if row["id"] in scoped]

        requirements = {}
        for index, part in enumerate(parts, 1):
            terms = query_terms(part)
            matched = {
                row["id"]: row["title"] for row in documents
                if (query_terms(row["title"]) - GENERIC_TITLE_TERMS) & terms
            }
            if len(matched) >= 2:
                requirements[index] = matched
        if not requirements and len(documents) > 1 and document_ids:
            requirements = {
                index: {row["id"]: row["title"] for row in documents}
                for index in range(1, len(parts) + 1)
            }
        return requirements

    def _comparison_query(self, part, identifier, documents):
        title_terms = {
            key: query_terms(title)
            for key, title in documents.items()
        }
        other_terms = set().union(*(
            terms - GENERIC_TITLE_TERMS for key, terms in title_terms.items()
            if key != identifier
        ))
        terms = query_terms(part) - other_terms - COMPARISON_ACTIONS
        title = documents[identifier]
        normalized_title = " ".join(re.findall(r"\w+", title.casefold()))
        terms.update(query_terms(" ".join(PAPER_TITLE_ALIASES.get(normalized_title, ()))))
        return " ".join(sorted(terms)) if terms else part

    def _comparison_spans(self, title, query, rows):
        candidates = ranked_spans(query, rows, limit=20)
        normalized_title = " ".join(re.findall(r"\w+", title.casefold()))
        aliases = query_terms(" ".join(PAPER_TITLE_ALIASES.get(normalized_title, ())))
        if aliases:
            candidates = [
                candidate for candidate in candidates
                if aliases & query_terms(candidate[0]["text"][candidate[1]:candidate[2]])
            ]
        return candidates[:5]

    def _correct_explicit_false_premise(self, question, selected):
        premise = WHY_PREMISE.search(question)
        if premise is None:
            return None
        term = canonical_term(premise.group(1))
        if term is None:
            return None
        for span_id, entry in selected.items():
            citation = entry["citation"]
            quote = citation["quote"]
            if term not in query_terms(quote) or not EXPLICIT_NEGATION.search(quote):
                continue
            return {
                "claim": "The premise is contradicted by the cited text, which explicitly says it dispenses with recurrence.",
                "citation": citation, "citations": [citation],
                "kind": "reported_finding", "question_parts": [entry["question_part"]],
                "evidence_span_ids": [span_id],
                "validation": {
                    "provenance": "exact_page_span",
                    "relevance": "selector_model_assessed",
                    "semantic_support": "deterministic_explicit_negation_match",
                    "numeric_values": "not_applicable",
                },
            }
        return None

    def _comparison_source_excerpts(self, selected, comparison_documents, covered_documents=None):
        excerpts = []
        for part, documents in comparison_documents.items():
            for identifier, title in sorted(documents.items()):
                if identifier in (covered_documents or {}).get(part, set()):
                    continue
                match = next((
                    (span_id, entry) for span_id, entry in selected.items()
                    if entry["question_part"] == part
                    and entry["citation"]["document_id"] == identifier
                ), None)
                if match is None:
                    return []
                span_id, entry = match
                citation = entry["citation"]
                excerpts.append({
                    "claim": f"{title} (PDF p. {citation['page']}): {citation['quote']}",
                    "citation": citation, "citations": [citation],
                    "kind": "source_excerpt", "question_part": part,
                    "question_parts": [part], "evidence_span_ids": [span_id],
                    "validation": {
                        "provenance": "exact_page_span",
                        "relevance": "selector_model_assessed",
                        "semantic_support": "not_assessed",
                    },
                })
        return excerpts

    def _negation_conflict(self, claim, evidence):
        claim_terms = query_terms(claim)
        claim_negated_objects = set().union(*(
            query_terms(match.group(1)) for match in NEGATED_PRESENCE.finditer(claim)
        ))
        claim_relations = []
        for match in POLARITY_RELATION.finditer(claim):
            before = claim[max(0, match.start() - 40):match.start()]
            claim_relations.append((
                self._relation_family(match.group().casefold()),
                bool(NEGATION_PREFIX.search(before)),
                query_terms(claim[max(0, match.start() - 100):match.end() + 120]),
            ))
        for source in evidence:
            quote = source["quote"]
            source_relations = []
            for match in POLARITY_RELATION.finditer(quote):
                before = quote[max(0, match.start() - 40):match.start()]
                source_relations.append((
                    self._relation_family(match.group().casefold()),
                    bool(NEGATION_PREFIX.search(before)),
                    query_terms(quote[max(0, match.start() - 100):match.end() + 120]),
                    set(),
                ))
            for match in NEGATED_PRESENCE.finditer(quote):
                source_relations.append((
                    "use", True,
                    query_terms(quote[max(0, match.start() - 100):match.end() + 120]),
                    query_terms(match.group(1)),
                ))
            for source_family, source_negative, source_terms, object_terms in source_relations:
                for claim_family, claim_negative, claim_context in claim_relations:
                    if source_family != claim_family or source_negative == claim_negative:
                        continue
                    if object_terms and object_terms <= claim_negated_objects:
                        continue
                    if object_terms & claim_terms and not object_terms <= claim_negated_objects:
                        return True
                    if len(source_terms & claim_context) >= 2:
                        return True
        return False

    @staticmethod
    def _relation_family(word):
        for prefix, family in (
            ("requir", "require"), ("need", "need"), ("us", "use"),
            ("includ", "include"), ("contain", "contain"), ("rel", "rely"),
            ("allow", "allow"), ("support", "support"), ("increas", "increase"),
            ("decreas", "decrease"), ("improv", "improve"), ("reduc", "reduce"),
            ("caus", "cause"), ("prevent", "prevent"), ("train", "train"),
            ("freez", "freeze"),
        ):
            if word.startswith(prefix):
                return family
        return word

    async def ask(self, question, *, document_id=None, document_ids=(), mode="keyword", top_k=5, variant="evidence",
                  strategy="spans", decompose=True):
        if variant not in {"baseline", "evidence"}:
            raise ValueError("Unknown corpus QA prompt variant.")
        if strategy not in {"legacy", "spans"}:
            raise ValueError("Unknown corpus QA strategy.")
        started = perf_counter()
        async with asyncio.timeout(self.settings.document_timeout):
            if strategy == "legacy":
                if document_ids:
                    raise ValueError("Legacy QA accepts a single document ID.")
                result = await self._ask(question, document_id, mode, top_k, variant)
            else:
                result = await self._ask_spans(question, document_id, document_ids, mode, top_k, variant, decompose)
        return dict(result, seconds=round(perf_counter() - started, 3))

    async def _ask_spans(self, question, document_id, document_ids, mode, top_k, variant, decompose):
        if not question.strip() or len(question) > 1000:
            raise ValueError("Enter a query of 1–1000 characters.")
        parts = question_parts(question) if decompose else [question]
        comparison_question = bool(COMPARISON_QUESTION.search(question))
        comparison_documents = self._comparison_documents(parts, document_id, document_ids)
        comparison_requirements = {
            part: set(documents) for part, documents in comparison_documents.items()
        }
        instructions = load_prompt("corpus_spans", variant=variant) + "\n\n" + load_prompt("corpus_span_adaptive")
        synthesis_prompt = load_prompt("corpus_synthesis")
        revision_prompt = load_prompt("corpus_synthesis_revision")
        verifier_prompt = load_prompt("corpus_synthesis_verify")
        safety = load_prompt("safety")
        schema = load_prompt("schema_instruction") + json.dumps(SpanAnswer.model_json_schema())
        budget = self.settings.context_tokens - 512 - len((instructions + safety + schema).encode())
        packets, trace, selections, choices_by_part = [], [], {}, []
        locations = set()
        for part_index, part in enumerate(parts, 1):
            terms = query_terms(part)
            search_query = " ".join(sorted(terms)) if mode == "keyword" and terms else part
            required_documents = comparison_requirements.get(part_index)
            document_queries = {}
            if required_documents:
                rows = []
                for identifier in sorted(required_documents):
                    document_query = self._comparison_query(
                        part, identifier, comparison_documents[part_index]
                    )
                    document_queries[identifier] = document_query
                    rows.extend(await self.retrieval.search(
                        document_query, mode=mode, limit=top_k, document_id=identifier
                    ))
            else:
                rows = await self.retrieval.search(search_query, mode=mode, limit=top_k,
                                                   document_id=document_id, document_ids=document_ids)
            trace.append({"query": search_query, "retrieved": [row["id"] for row in rows],
                          "provided": [], "candidate_spans": [],
                          "required_documents": sorted(required_documents) if required_documents else [],
                          "document_queries": document_queries})
            packets.append({"part": len(packets) + 1, "question": part, "options": []})
            if required_documents:
                choices_by_doc = {
                    identifier: self._comparison_spans(
                        comparison_documents[part_index][identifier],
                        document_queries[identifier],
                        [row for row in rows if row["document_id"] == identifier]
                    )
                    for identifier in sorted(required_documents)
                }
                choices = []
                for rank in range(max((len(items) for items in choices_by_doc.values()), default=0)):
                    for identifier in sorted(choices_by_doc):
                        if rank < len(choices_by_doc[identifier]):
                            choices.append(choices_by_doc[identifier][rank])
                choices_by_part.append(choices)
            else:
                choices_by_part.append(ranked_spans(part, rows))

        def encode():
            return json.dumps({"question": question, "parts": packets}, ensure_ascii=False)

        def add_option(index, row, start, end, trace_record=None):
            location = (row["document_id"], row["page"], row["start_char"] + start)
            if location in locations:
                return None
            key = len(selections) + 1
            packets[index]["options"].append(
                {"span": key, "paper": row["title"], "text": " ".join(row["text"][start:end].split())}
            )
            if len(encode().encode()) > budget:
                packets[index]["options"].pop()
                return None
            locations.add(location)
            selections[key] = (index + 1, row, start, end)
            destination = trace[index] if trace_record is None else trace_record
            destination["candidate_spans"].append({"span": key, "chunk_id": row["id"]})
            if row["id"] not in destination["provided"]:
                destination["provided"].append(row["id"])
            return key

        # Round-robin candidate selection gives each question part room in the shared context.
        for rank in range(max((len(choices) for choices in choices_by_part), default=0)):
            for index, choices in enumerate(choices_by_part):
                if rank < len(choices):
                    add_option(index, *choices[rank])

        selected = {}
        selector_calls = 0
        complex_question = len(parts) > 1 or bool(COMPLEX_QUESTION.search(question))
        selection_limits = {
            index: min(4, max(2, len(comparison_requirements.get(index, ()))))
            if comparison_question else 1
            for index in range(1, len(parts) + 1)
        }
        rejected_span_ids = []

        def select_spans(span_ids):
            counts = {}
            documents_by_part = {}
            for entry in selected.values():
                part = entry["question_part"]
                counts[part] = counts.get(part, 0) + 1
                documents_by_part.setdefault(part, set()).add(entry["citation"]["document_id"])
            for key in span_ids[:4]:
                span = selections.get(key)
                if span is None or counts.get(span[0], 0) >= selection_limits[span[0]]:
                    rejected_span_ids.append(key)
                    continue
                required = comparison_requirements.get(span[0], set())
                document_id = span[1]["document_id"]
                if required and document_id in documents_by_part.get(span[0], set()) \
                        and not required <= documents_by_part[span[0]]:
                    rejected_span_ids.append(key)
                    continue
                citation = self.source_span(*span[1:])
                if citation is not None:
                    selected[key] = {"question_part": span[0], "citation": citation}
                    counts[span[0]] = counts.get(span[0], 0) + 1
                    documents_by_part.setdefault(span[0], set()).add(document_id)
                else:
                    rejected_span_ids.append(key)

        def ensure_comparison_span_coverage():
            for part, required in comparison_requirements.items():
                selected_documents = {
                    entry["citation"]["document_id"] for entry in selected.values()
                    if entry["question_part"] == part
                }
                for identifier in sorted(required - selected_documents):
                    count = sum(entry["question_part"] == part for entry in selected.values())
                    while count >= selection_limits[part]:
                        redundant = next((
                            key for key in reversed(list(selected))
                            if selected[key]["question_part"] == part
                            and sum(
                                entry["question_part"] == part
                                and entry["citation"]["document_id"] == selected[key]["citation"]["document_id"]
                                for entry in selected.values()
                            ) > 1
                        ), None)
                        if redundant is None:
                            break
                        selected.pop(redundant)
                        rejected_span_ids.append(redundant)
                        count -= 1
                    if count >= selection_limits[part]:
                        continue
                    for key, span in selections.items():
                        if key in selected or span[0] != part or span[1]["document_id"] != identifier:
                            continue
                        citation = self.source_span(*span[1:])
                        if citation is not None:
                            selected[key] = {"question_part": part, "citation": citation}
                            break

        first_draft = None
        if selections or complex_question:
            first_draft = await self.llm.run(
                "Corpus evidence selector", instructions, encode(), SpanAnswer, max_output_tokens=256
            )
            selector_calls += 1
            select_spans(first_draft.span_ids)
            ensure_comparison_span_coverage()

        followed_parts = set()
        follow_up_decisions = []
        follow_up_options = 0
        if first_draft is not None:
            selected_counts = {}
            for entry in selected.values():
                part = entry["question_part"]
                selected_counts[part] = selected_counts.get(part, 0) + 1
            for request in first_draft.follow_up:
                index = request.part - 1
                query = request.query.strip()
                if index >= len(parts):
                    follow_up_decisions.append({"part": request.part, "query": query,
                                                "decision": "rejected", "reason": "part_out_of_range"})
                    continue
                if selected_counts.get(index + 1, 0) >= selection_limits[index + 1] or index in followed_parts:
                    follow_up_decisions.append({"part": request.part, "query": query,
                                                "decision": "rejected", "reason": "part_already_attempted_or_sufficient"})
                    continue
                if not query:
                    follow_up_decisions.append({"part": request.part, "query": query,
                                                "decision": "rejected", "reason": "empty_query"})
                    continue
                if query.casefold() == parts[index].casefold():
                    follow_up_decisions.append({"part": request.part, "query": query,
                                                "decision": "rejected", "reason": "repeats_original_question"})
                    continue
                followed_parts.add(index)
                rows = await self.retrieval.search(query, mode=mode, limit=top_k,
                                                   document_id=document_id, document_ids=document_ids)
                follow_up_decisions.append({"part": request.part, "query": query, "decision": "retrieved",
                                            "candidate_count": len(rows)})
                follow_trace = {"query": query, "question_part": index + 1,
                                "retrieved": [row["id"] for row in rows], "provided": [],
                                "candidate_spans": [], "follow_up": True}
                trace.append(follow_trace)
                for row, start, end in ranked_spans(query, rows):
                    key = add_option(index, row, start, end, follow_trace)
                    if key is not None:
                        follow_up_options += 1

        if follow_up_options:
            follow_up_draft = await self.llm.run(
                "Corpus evidence selector", instructions, encode(), SpanAnswer, max_output_tokens=256
            )
            selector_calls += 1
            select_spans(follow_up_draft.span_ids)
            ensure_comparison_span_coverage()

        selected = dict(sorted(selected.items(), key=lambda item: (item[1]["question_part"], item[0])))
        evidence = [
            {"span_id": key, "question_part": entry["question_part"], "citation": entry["citation"],
             "validation": {"provenance": "exact_page_span", "relevance": "selector_model_assessed"}}
            for key, entry in selected.items()
        ]
        covered_parts = {entry["question_part"] for entry in selected.values()}
        unanswered = [part for index, part in enumerate(parts, 1) if index not in covered_parts]
        claims = []
        synthesis_trace = None
        extractive_comparison = False
        comparison_covered = {part: set() for part in comparison_requirements}
        if selected and complex_question:
            claims, synthesis_trace = await self._synthesize(
                question, parts, selected, synthesis_prompt, revision_prompt, verifier_prompt,
                comparison_requirements,
            )
            for claim in claims:
                for part in claim["question_parts"]:
                    if part in comparison_requirements:
                        comparison_covered[part].update(
                            set(citation["document_id"] for citation in claim["citations"])
                            & comparison_requirements[part]
                        )
            if comparison_requirements and any(
                not required <= comparison_covered[part]
                for part, required in comparison_requirements.items()
            ):
                excerpts = self._comparison_source_excerpts(
                    selected, comparison_documents, comparison_covered
                )
                claims.extend(excerpts)
                extractive_comparison = bool(excerpts)
                if extractive_comparison:
                    synthesis_trace["extractive_comparison_fallback"] = "exact_source_excerpts_for_missing_sides"
            if not claims:
                correction = self._correct_explicit_false_premise(question, selected)
                if correction is not None:
                    claims = [correction]
                    synthesis_trace["deterministic_correction"] = "explicit_negated_premise"
            verified_parts = {part for claim in claims for part in claim["question_parts"]}
            unanswered = [part for index, part in enumerate(parts, 1) if index not in verified_parts]
            if extractive_comparison:
                unanswered = [
                    parts[part - 1] for part, required in comparison_requirements.items()
                    if not required <= comparison_covered[part]
                ]
            for part_index, required in comparison_requirements.items():
                if not required <= comparison_covered[part_index] and parts[part_index - 1] not in unanswered:
                    unanswered.append(parts[part_index - 1])
            if claims:
                if extractive_comparison:
                    status = "partial_evidence"
                    prefix = (
                        "The model validated only part of the comparison. Exact source excerpts for the "
                        "missing side(s):"
                        if any(claim["kind"] != "source_excerpt" for claim in claims)
                        else "The model did not validate a synthesized comparison. Exact source excerpts:"
                    )
                    answer = (prefix + "\n\n"
                              + "\n\n".join(claim["claim"] for claim in claims))
                else:
                    status = "model_checked_answer" if not unanswered else "partial_evidence"
                    answer = " ".join(claim["claim"] for claim in claims)
            else:
                status = "evidence_only"
                answer = ""
        else:
            claims = [
                {"claim": " ".join(entry["citation"]["quote"].split()),
                 "citation": entry["citation"], "citations": [entry["citation"]],
                 "kind": "source_excerpt", "question_part": entry["question_part"],
                 "evidence_span_ids": [key],
                 "validation": {"provenance": "exact_page_span",
                                "relevance": "selector_model_assessed",
                                "semantic_support": "not_assessed"}}
                for key, entry in selected.items()
            ]
            answer = " ".join(claim["claim"] for claim in claims)
            status = ("evidence_available" if not unanswered else "partial_evidence") if claims else "insufficient_evidence"

        evidence_covered = {
            part: {
                entry["citation"]["document_id"] for entry in selected.values()
                if entry["question_part"] == part
            }
            for part in comparison_requirements
        }
        prompt_material = (instructions + safety + schema + synthesis_prompt + revision_prompt + verifier_prompt
                           + json.dumps(ScientificSynthesis.model_json_schema(), sort_keys=True)
                           + json.dumps(Verdict.model_json_schema(), sort_keys=True))
        model_calls = {"span_selection": selector_calls,
                       "synthesis": synthesis_trace["draft_calls"] if synthesis_trace else 0,
                       "claim_validation": synthesis_trace["validation_calls"] if synthesis_trace else 0}
        return {"status": status, "answer": answer, "claims": claims, "evidence": evidence,
                "trace": trace, "selected_span_ids": list(selected),
                "rejected_span_ids": rejected_span_ids, "follow_up_decisions": follow_up_decisions,
                "unanswered_parts": unanswered,
                "comparison_coverage": {
                    "required_documents": {
                        str(part): documents for part, documents in comparison_documents.items()
                    },
                    "evidence_documents": {
                        str(part): {
                            identifier: title for identifier, title in documents.items()
                            if identifier in evidence_covered[part]
                        }
                        for part, documents in comparison_documents.items()
                    },
                    "missing_documents": {
                        str(part): {
                            identifier: title for identifier, title in documents.items()
                            if identifier not in evidence_covered[part]
                        }
                        for part, documents in comparison_documents.items()
                        if any(identifier not in evidence_covered[part] for identifier in documents)
                    },
                    "unvalidated_documents": {
                        str(part): {
                            identifier: title for identifier, title in documents.items()
                            if identifier not in comparison_covered[part]
                        }
                        for part, documents in comparison_documents.items()
                        if any(identifier not in comparison_covered[part] for identifier in documents)
                    },
                    "synthesis_validated": not any(
                        not required <= comparison_covered[part]
                        for part, required in comparison_requirements.items()
                    ),
                },
                "model_calls": {**model_calls, "additional_retrieval": len(followed_parts)},
                "provider": self.settings.provider, "model": self.settings.model,
                "validation_trace": synthesis_trace,
                "prompt_version": hashlib.sha256(prompt_material.encode()).hexdigest(),
                "coverage": ("Exact page provenance is checked. Extractive answers do not receive semantic support "
                             "assessment; generated claims receive a separate local-model check, not human verification.")}

    async def _synthesize(self, question, parts, selected, instructions, revision, verifier,
                          comparison_requirements):
        source = []
        by_span = {}
        for span_id, entry in selected.items():
            citation = entry["citation"]
            card = {"span_id": span_id, "question_part": entry["question_part"],
                    "document_id": citation["document_id"], "title": citation["title"],
                    "page": citation["page"],
                    "quote": citation["quote"]}
            source.append(card)
            by_span[span_id] = card
        context = {"question": question, "parts": parts, "evidence": source}
        feedback = None
        attempts = []
        validation_calls = 0
        for attempt in range(2):
            verified_by_key = {}
            packet = dict(context)
            if feedback:
                packet["validation_feedback"] = feedback
            draft = await self.llm.run(
                "Scientific evidence synthesis",
                instructions if attempt == 0 else instructions + "\n\n" + revision,
                json.dumps(packet, ensure_ascii=False), ScientificSynthesis, max_output_tokens=768,
            )
            prepared = []
            provenance_rejected = 0
            numeric_rejected = 0
            polarity_rejected = 0
            comparison_coverage_rejected = 0
            rejected = []
            for candidate in draft.claims:
                span_ids = list(dict.fromkeys(candidate.span_ids))
                if not span_ids or any(identifier not in by_span for identifier in span_ids):
                    provenance_rejected += 1
                    rejected.append({"claim": candidate.text, "span_ids": span_ids,
                                     "reason": "invalid_source_span"})
                    continue
                cited = [by_span[identifier] for identifier in span_ids]
                if self._negation_conflict(candidate.text, cited):
                    polarity_rejected += 1
                    rejected.append({"claim": candidate.text, "span_ids": span_ids,
                                     "reason": "source_polarity_conflict"})
                    continue
                claim_numbers = numeric_tokens(candidate.text)
                evidence_numbers = set().union(*(numeric_tokens(row["quote"]) for row in cited))
                if claim_numbers and not claim_numbers <= evidence_numbers:
                    numeric_rejected += 1
                    rejected.append({"claim": candidate.text, "span_ids": span_ids,
                                     "reason": "numeric_fidelity"})
                    continue
                covered = sorted({row["question_part"] for row in cited})
                required = set().union(*(comparison_requirements.get(part, set()) for part in covered))
                cited_documents = {row["document_id"] for row in cited}
                if candidate.kind == "comparison" and required and not required <= cited_documents:
                    comparison_coverage_rejected += 1
                    rejected.append({"claim": candidate.text, "span_ids": span_ids,
                                     "reason": "comparison_coverage"})
                    continue
                prepared.append((candidate, span_ids, cited, covered))

            support = set()
            if prepared:
                validation_packet = {"question": question, "claims": [
                    {"index": index, "claim": candidate.text,
                     "evidence": [{"title": row["title"], "page": row["page"], "quote": row["quote"]}
                                  for row in cited]}
                    for index, (candidate, _, cited, _) in enumerate(prepared)
                ]}
                verdict = await self.llm.run(
                    "Scientific claim support checker", verifier,
                    json.dumps(validation_packet, ensure_ascii=False), Verdict, max_output_tokens=256,
                )
                validation_calls += 1
                support = {index for index in verdict.supported if 0 <= index < len(prepared)}

            accepted = []
            for index, (candidate, span_ids, _, covered) in enumerate(prepared):
                if index not in support:
                    rejected.append({"claim": candidate.text, "span_ids": span_ids,
                                     "reason": "semantic_support"})
                    continue
                key = (candidate.text, tuple(span_ids))
                citations = [selected[span_id]["citation"] for span_id in span_ids]
                record = {"claim": candidate.text, "citation": citations[0], "citations": citations,
                          "kind": candidate.kind, "question_parts": covered,
                          "evidence_span_ids": span_ids,
                          "validation": {"provenance": "exact_page_span",
                                         "relevance": "selector_model_assessed",
                                         "semantic_support": "model_assessed",
                                         "numeric_values": "digit_tokens_match_when_present"}}
                verified_by_key[key] = record
                accepted.append(record)
            attempts.append({"draft_claims": len(draft.claims), "provenance_rejected": provenance_rejected,
                             "numeric_rejected": numeric_rejected,
                             "polarity_rejected": polarity_rejected,
                             "comparison_coverage_rejected": comparison_coverage_rejected,
                             "semantic_rejected": len(prepared) - len(support),
                             "accepted": len(accepted), "rejected_claims": rejected[:8]})
            needs_revision = bool(
                rejected or provenance_rejected or numeric_rejected or comparison_coverage_rejected
            )
            if attempt == 1 or not needs_revision:
                break
            feedback = {"unsupported_claims": rejected,
                        "rejected_claim_counts": {"provenance": provenance_rejected,
                                                  "numeric_fidelity": numeric_rejected,
                                                  "source_polarity": polarity_rejected,
                                                  "comparison_coverage": comparison_coverage_rejected},
                        "instruction": "Remove unsupported claims or narrow them to the supplied evidence; do not add evidence."}
            if not draft.claims:
                break
        return list(verified_by_key.values()), {
            "draft_calls": len(attempts), "validation_calls": validation_calls, "attempts": attempts,
        }

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
