from research_swarm.prompt_loader import load_prompt
import json
from research_swarm.llm import LLM
from research_swarm.models import Questions, Relevance
from research_swarm.tools.openalex import OpenAlexClient, OpenAlexError
from research_swarm.telemetry import emit

def safe_text(value: str) -> str:
    """Escape external metadata for Markdown display."""
    for char in "\\`*_{}[]<>#|":
        value = value.replace(char, "\\" + char)
    return value.replace("\n", " ")

class LiteratureAgent:
    def __init__(self, llm: LLM, client: OpenAlexClient, limit: int, prompt_variant: str = "baseline") -> None:
        self.llm, self.client, self.limit = llm, client, limit
        self.prompt_variant = prompt_variant
        self.records = []

    async def search(self, questions: Questions) -> tuple[str, list[str]]:
        self.records = []
        sections = ["# Literature review\n",
                    "Metadata comes from OpenAlex. Relevance is an AI assessment based on titles, "
                    "not a full-text review; search matches may not answer the question.\n"]
        warnings: list[str] = []
        for number, question in enumerate(questions.questions, 1):
            emit("activity",text=f"Searching OpenAlex for question {number} of {len(questions.questions)}")
            sections.append(f"## {number}. {question.question}\n\nQuery: {question.search_query}\n")
            try:
                papers = await self.client.search(question.search_query, self.limit)
            except OpenAlexError as exc:
                warning = f"Question {number}: {exc}"
                warnings.append(warning)
                sections.append(f"Search unavailable: {exc}\n")
                continue
            if not papers:
                sections.append("No papers returned for this query.\n")
            for paper_index,paper in enumerate(papers,1):
                emit("activity",text=f"Assessing literature for question {number}: paper {paper_index} of {len(papers)}")
                assessment = await self.llm.run(
                    "Literature Search Agent",
                    load_prompt("literature", variant=self.prompt_variant),
                    json.dumps({"question": question.question, "title": paper.title}), Relevance)
                assert isinstance(assessment, Relevance)
                self.records.append(dict(question=question.question, search_query=question.search_query,
                    openalex_id=paper.id, title=paper.title, authors=list(paper.authors), year=paper.year,
                    doi=paper.doi, relevance=assessment.model_dump(), evidence_scope="title only"))
                authors = ", ".join(paper.authors) or "Not available"
                doi = f"[DOI]({paper.doi})" if paper.doi else "DOI not available"
                sections.append(f"### {safe_text(paper.title)}\n\n"
                                f"**Authors:** {safe_text(authors)}\n\n"
                                f"**Year:** {paper.year or 'Not available'} · {doi} · "
                                f"[OpenAlex]({paper.id})\n\n"
                                f"**Potential relevance:** {assessment.explanation}\n")
        return "\n".join(sections), warnings
