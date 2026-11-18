"""Editable UTF-8 prompts with strict, single-pass named substitution."""
from pathlib import Path
from string import Template
import hashlib
import json
import re

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
VARIANTS = ("baseline", "fields", "evidence")


def load_prompt(name: str, *, variant: str = "baseline", **variables) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("Unknown prompt name or variant.")
    if variant == "selected":
        selection = json.loads((PROMPTS / "selection.json").read_text(encoding="utf-8-sig"))
        if not isinstance(selection,dict) or any(not isinstance(key,str) or value not in VARIANTS
                for key,value in selection.items()):
            raise ValueError("Prompt selection must map template names to baseline, fields, or evidence.")
        variant = selection.get(name, "baseline")
    if variant not in VARIANTS or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("Unknown prompt name or variant.")
    path = PROMPTS / variant / (name + ".md")
    if not path.is_file() and name not in {"summary_common", "questions", "literature"}:
        path = PROMPTS / "baseline" / (name + ".md")
    template = Template(path.read_text(encoding="utf-8-sig"))
    required = set(template.get_identifiers())
    if not template.is_valid() or required != set(variables):
        raise ValueError(f"Prompt {name} requires variables {sorted(required)}.")
    return template.substitute(variables)


def prompt_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(PROMPTS.glob("*/*.md")):
        digest.update(path.relative_to(PROMPTS).as_posix().encode())
        digest.update(path.read_text(encoding="utf-8-sig").encode("utf-8"))
    selection = PROMPTS / "selection.json"
    if selection.is_file():
        digest.update(selection.read_text(encoding="utf-8-sig").encode("utf-8"))
    return digest.hexdigest()
