from research_swarm.prompt_loader import load_prompt
from research_swarm.llm import LLM
from research_swarm.models import Questions

class QuestionsAgent:
    def __init__(self, llm: LLM, limit: int, prompt_variant: str = "baseline") -> None:
        self.llm, self.limit = llm, limit
        self.prompt_variant = prompt_variant

    async def find(self, evidence: str, summary: str) -> Questions:
        output = await self.llm.run(
            "Open Questions Finder",
            load_prompt("questions", variant=self.prompt_variant, limit=self.limit),
            load_prompt("questions_input", evidence=evidence, summary=summary), Questions)
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
