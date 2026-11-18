"""Download fixed paper versions; retain PDFs locally, never fabricate papers."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path
import httpx
import pymupdf

PAPERS = [
    ("1706.03762v7", "Attention Is All You Need"),
    ("1412.6980v9", "Adam: A Method for Stochastic Optimization"),
    ("2106.09685v2", "LoRA: Low-Rank Adaptation of Large Language Models"),
]


def main():
    folder = Path(__file__).resolve().parent
    pdf_dir = folder.parent / ".runtime" / "evaluation-papers"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for identifier, title in PAPERS:
        path = pdf_dir / (identifier + ".pdf")
        url = f"https://arxiv.org/pdf/{identifier}"
        if not path.exists():
            response = httpx.get(url, follow_redirects=True, timeout=60)
            response.raise_for_status()
            path.write_bytes(response.content)
        with pymupdf.open(path) as pdf:
            text = pdf[0].get_text("text", sort=False)
        abstract = re.split(r"\bABSTRACT\b", text, maxsplit=1, flags=re.I)[1]
        abstract = re.split(r"\n1\s*\nINTRODUCTION|\n∗Equal|\n\*Equal", abstract, maxsplit=1)[0]
        abstract = re.sub(r"(\w)-\n(\w)", r"\1\2", abstract)
        abstract = " ".join(unicodedata.normalize("NFKC", abstract).split())
        # Attention's first page ends with author notes rather than Introduction.
        if identifier.startswith("1706"):
            abstract = abstract.split("Equal contribution")[0].rstrip(" ∗*")
            abstract = abstract[:abstract.index("training data.") + len("training data.")]
        records.append(dict(id=identifier, title=title, url=url,
            pdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), page=1,
            evidence="[Page 1]\n" + abstract,
            normalization="PyMuPDF sort=False; abstract only; join line hyphenation; NFKC; collapse whitespace"))
        print(identifier, len(abstract), flush=True)
    (folder / "sources.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
