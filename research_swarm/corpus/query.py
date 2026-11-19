"""Shared scientific query normalization for lexical retrieval and span ranking."""
import re
import unicodedata

MOTIVATION_QUESTION = re.compile(r"\b(?:motivat\w*|difficult\w*|challeng\w*|barrier|obstacle)\b", re.I)
MOTIVATION_TERMS = frozenset({"cost", "costly", "expensive", "feasible", "memory", "resource", "resources"})
BETA_PARAMETER = re.compile(r"(?<!\w)(?:beta|\u03b2)[\s_-]*([12])(?!\w)", re.I)
TERM_ALIASES = {
    "recur": "recur",
    "recurrent": "recur",
    "recurrently": "recur",
    "recurrence": "recur",
    "convolution": "convolution",
    "convolutional": "convolution",
    "convolutions": "convolution",
    "mechanisms": "mechanism",
    "matrices": "matrix",
    "updates": "update",
    "finetune": "finetune",
    "finetunes": "finetune",
    "finetuned": "finetune",
    "finetuning": "finetune",
}
TERM_VARIANTS = {
    "\u03b21": ("\u03b21", "\u03b2"),
    "\u03b22": ("\u03b22", "\u03b2"),
    "recur": ("recur", "recurrent", "recurrently", "recurrence"),
    "convolution": ("convolution", "convolutional", "convolutions"),
    "mechanism": ("mechanism", "mechanisms"),
    "matrix": ("matrix", "matrices"),
    "update": ("update", "updates"),
    "finetune": ("finetune", "finetuned", "finetuning", "fine", "tune", "tuned", "tuning"),
}
STOP_WORDS = frozenset("""
a an and are as at be by can did do does for from had has have how in into is it its of on or
paper report reported study than that the their this to use used using was were what when where
which who why with would achieve achieved
""".split())
FINE_TUNING = re.compile(r"\bfine[\s-]*tun(?:e|es|ed|ing)\b|\bfinetun(?:e|es|ed|ing)\b", re.I)


def _tokens(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", normalized)
    normalized = FINE_TUNING.sub("finetune", normalized)
    normalized = BETA_PARAMETER.sub(lambda match: f"\u03b2{match.group(1)}", normalized)
    return [TERM_ALIASES.get(word, word) for word in re.findall(r"\w+", normalized)
            if len(word) > 1 and word not in STOP_WORDS]


def canonical_term(text):
    terms = _tokens(text)
    return terms[0] if terms else None


def query_terms(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    terms = set(_tokens(normalized))
    if MOTIVATION_QUESTION.search(normalized):
        terms.update(MOTIVATION_TERMS)
    return terms


def query_search_terms(text):
    terms = list(dict.fromkeys(_tokens(text)))
    expanded = list(terms)
    seen = set(expanded)
    for term in terms:
        for variant in TERM_VARIANTS.get(term, ()):
            if variant not in seen:
                expanded.append(variant)
                seen.add(variant)
    if MOTIVATION_QUESTION.search(text):
        expanded.extend(term for term in sorted(MOTIVATION_TERMS) if term not in seen)
    return expanded
