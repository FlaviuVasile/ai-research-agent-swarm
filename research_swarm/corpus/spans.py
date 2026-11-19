"""Rank addressable excerpts and resolve their exact PDF coordinates."""
from collections import Counter
import re
from .query import STOP_WORDS, MOTIVATION_QUESTION, canonical_term, query_terms

from pydantic import BaseModel, Field

QUESTION_SPLIT = re.compile(r"\s*(?:;|\band\b)\s+(?=(?:what|which|how|why|where|when|did|does|was|were)\b)", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|\n\s*\n")
DIRECTIVE = re.compile(r"\b(?:ignore (?:all |the )?(?:previous|prior) instructions|(?:system|assistant) prompt|output .* as your .*answer)\b", re.I)
FOCUS = re.compile(r"^\s*(?:which|what)\s+(\w+)", re.I)
PREMISE = re.compile(r"^\s*why\b.*?\b(?:use|choose|include|adopt|assume|apply)\s+(\w+)", re.I)
QUANTITY = re.compile(r"\b(?:how (?:many|much|long)|(?:what|which)\b[^?]{0,55}\b(?:bleu|score|rate|reduction|percentage))\b", re.I)
QUANTITY_VALUE = re.compile(r"\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand)\b", re.I)
BLEU_VALUE = re.compile(r"\b\d+(?:\.\d+)?\s+BLEU\b|\bBLEU\s+(?:score\s+)?(?:of\s+)?\d", re.I)
CONTRAST = re.compile(r"\b(?:instead|dispens\w*|replac\w*|eschew\w*|without|rather than|did not)\b", re.I)
MOTIVATION_EVIDENCE = re.compile(
    r"\b(?:cost|costly|expensive|infeasible|feasible|prohibitively|resources?|memory)\b", re.I
)
GENERIC_FOCUS = {"architecture", "architectural", "difficulty", "mechanism", "method", "problem"}


def question_parts(question):
    pieces = [part.strip() for part in QUESTION_SPLIT.split(question, maxsplit=3) if part.strip()]
    return pieces or [question]


class SpanFollowUp(BaseModel):
    part: int = Field(ge=1, le=4)
    query: str = Field(min_length=2, max_length=160)


class SpanAnswer(BaseModel):
    span_ids: list[int] = Field(max_length=4)
    follow_up: list[SpanFollowUp] = Field(default_factory=list, max_length=4)


def ranked_spans(question, rows, limit=5):
    terms = query_terms(question)
    premise = PREMISE.match(question)
    field = FOCUS.match(question) or premise
    quantity = QUANTITY.search(question)
    focus = canonical_term(field[1]) if field else None
    value_pattern = BLEU_VALUE if "bleu" in terms else QUANTITY_VALUE
    if focus in GENERIC_FOCUS or focus not in terms:
        focus = None
    candidates = []
    seen = set()
    for rank, row in enumerate(rows):
        text = row["text"]
        boundaries = list(SENTENCE_END.finditer(text))
        starts = [0, *(match.end() for match in boundaries)]
        ends = [*(match.start() for match in boundaries), len(text)]
        for start, end in zip(starts, ends):
            leading = start == 0
            segment = text[start:end]
            start += len(segment) - len(segment.lstrip())
            end -= len(segment) - len(segment.rstrip())
            quote = text[start:end]
            if (not 24 <= len(quote) <= 650 or quote[-1] not in ".!?"
                    or DIRECTIVE.search(" ".join(quote.split()))):
                continue
            if leading and row["start_char"] and quote[0].islower():
                continue
            words = quote.split()
            if all(word[0].isupper() or word.casefold() in STOP_WORDS for word in words):
                continue
            if quantity and not value_pattern.search(quote):
                continue
            quote_terms = query_terms(quote)
            overlap = terms & quote_terms
            identity_terms = terms & query_terms(row["title"])
            minimum_identity_overlap = 2 if premise else min(3, len(terms))
            if (len(overlap) < (1 if len(terms) <= 2 else 2)
                    or len(overlap | identity_terms) < minimum_identity_overlap
                    or (focus and focus not in quote_terms)):
                continue
            location = (row["document_id"], row["page"], row["start_char"] + start)
            if not overlap or location in seen:
                continue
            seen.add(location)
            candidates.append((row, start, end, overlap, rank))
    frequency = Counter(term for _, _, _, overlap, _ in candidates for term in overlap)
    motivation_question = MOTIVATION_QUESTION.search(question)
    candidates.sort(key=lambda item: (
        -bool(premise and CONTRAST.search(item[0]["text"][item[1]:item[2]])),
        -bool(motivation_question and MOTIVATION_EVIDENCE.search(item[0]["text"][item[1]:item[2]])),
        -sum(1 / frequency[term] ** .5 for term in sorted(item[3])), item[4], item[1]))
    return [(row, start, end) for row, start, end, _, _ in candidates[:limit]]
