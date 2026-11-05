from research_swarm.llm import LLM
from research_swarm.models import Questions

class QuestionsAgent:
    def __init__(self, llm: LLM, limit: int) -> None:
        self.llm, self.limit = llm, limit

    async def find(self, evidence: str, summary: str) -> Questions:
        output = await self.llm.run(
            "Open Questions Finder",
            f"Identify 1 to {self.limit} concrete research questions, their importance, "
            "supporting evidence/page if available, and short academic keyword search queries. "
            "Label each as explicit limitation or inferred research opportunity. "
            "Do not assert that an inferred gap is globally unsolved. Avoid generic questions.",
            f"PDF evidence:\n{evidence}\n\nSummary:\n{summary}", Questions)
        assert isinstance(output, Questions)
        output.questions = output.questions[:self.limit]
        return output

def render_questions(questions: Questions) -> str:
    sections = ["# Open research questions\n",
                "Inferred opportunities require validation against the wider literature.\n"]
    for index, q in enumerate(questions.questions, 1):
        sections.append(f"## {index}. {q.question}\n\n**Type:** {q.kind}\n\n"
                        f"**Why it matters:** {q.why_it_matters}\n\n"
                        f"**Evidence:** {q.evidence}\n\n**Search query:** {q.search_query}\n")
    return "\n".join(sections)
