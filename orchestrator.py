"""Central deterministic controller for four specialized agents."""
import logging
from pathlib import Path
from typing import Callable
from research_swarm.config import Settings, ROOT
from research_swarm.llm import LLM
from research_swarm.agents.pdf_master import PDFMaster
from research_swarm.agents.summary_agent import SummaryAgent
from research_swarm.agents.questions_agent import QuestionsAgent, render_questions
from research_swarm.agents.literature_agent import LiteratureAgent
from research_swarm.tools.openalex import OpenAlexClient
from research_swarm.models import AnalysisResult
from research_swarm.budgets import document_budget,timeboxed,BudgetExceeded
from research_swarm.summary_work import SummaryJournal,select_corpus_evidence

logger = logging.getLogger(__name__)
Progress = Callable[[str, str], None]

class AnalysisError(RuntimeError):
    """User-safe workflow error; completed files remain available on disk."""

class Orchestrator:
    def __init__(self, settings: Settings | None = None, output_dir: Path | None = None,
                 llm: LLM | None = None, openalex: OpenAlexClient | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.output_dir = output_dir or ROOT / "output"
        llm = LLM(settings=self.settings) if self.settings.local_test_mode else (llm or LLM(settings=self.settings))
        self.pdf = PDFMaster(self.settings)
        self.summary = SummaryAgent(llm, self.settings)
        self.questions = QuestionsAgent(llm, self.settings.max_questions)
        self.literature = LiteratureAgent(llm, openalex or OpenAlexClient(self.settings.openalex_key),
                                          self.settings.papers_per_question)
        if self.settings.local_test_mode:
            # Test mode never reaches OpenAlex, even with an injected client.
            class OfflineSearch:
                async def search(self, query, limit):
                    return []
            self.literature.client = OfflineSearch()

    async def run(self, pdf: bytes, progress: Progress | None = None) -> AnalysisResult:
        try:
            with document_budget(self.settings.document_timeout):
                return await timeboxed(self._run(pdf,progress),self.settings.document_timeout,"Document")
        except BudgetExceeded as exc:
            raise AnalysisError(str(exc)) from None

    async def _run(self,pdf,progress=None):
        notify = progress or (lambda stage, status: None)
        files: dict[str, str] = {}
        warnings: list[str] = []
        if self.settings.local_test_mode:
            warnings.append("TEST MODE: Synthetic fixtures only. No AI analysis or OpenAlex search was performed.")
        stage = "PDF Master"

        def save(name: str, content: str) -> None:
            if self.settings.local_test_mode and name.endswith(".md"):
                content = "> TEST MODE: Synthetic test output; not academic research.\n\n" + content
            path = self.output_dir / name
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
            files[name] = content

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            # Remove only this application's old artifacts so failed runs cannot expose stale results.
            for name in ("extracted_text.txt", "summary.md", "open_questions.md", "literature_review.md"):
                (self.output_dir / name).unlink(missing_ok=True)
            notify(stage, "running")
            extraction = self.pdf.extract(pdf)
            warnings.extend(extraction.warnings)
            save("extracted_text.txt", extraction.text)
            notify(stage, "complete")

            stage = "Summary Agent"
            notify(stage, "running")
            journal=SummaryJournal(self.settings.research_db or self.output_dir / "research.sqlite3")
            self.summary.journal=journal
            self.summary.notes_path=self.output_dir / "summary_chunks.md"
            if self.settings.research_mode=="FAST_RESEARCH_MODE":
                self.summary.selected_evidence=select_corpus_evidence(pdf,self.settings,journal,self.output_dir / "selection.json")
            summary, evidence = await self.summary.summarize(extraction.text)
            save("summary.md", summary)
            if self.settings.research_mode=="FULL_RESEARCH_MODE" and self.summary.notes_path.is_file():
                files["summary_chunks.md"]=self.summary.notes_path.read_text(encoding="utf-8")
            notify(stage, "complete")

            stage = "Open Questions Finder"
            notify(stage, "running")
            questions = await self.questions.find(evidence, summary)
            save("open_questions.md", render_questions(questions))
            notify(stage, "complete")

            stage = "Literature Search Agent"
            notify(stage, "running")
            literature, search_warnings = await self.literature.search(questions)
            warnings.extend(search_warnings)
            save("literature_review.md", literature)
            notify(stage, "complete with warnings" if search_warnings else "complete")
            return AnalysisResult(files, warnings, str(self.output_dir))
        except Exception as exc:
            notify(stage, "failed")
            logger.error("Workflow failed at %s (%s)", stage, type(exc).__name__)
            if isinstance(exc, ValueError):
                message = str(exc)
            else:
                message = "Service or filesystem error. Check connectivity, credentials, quota, and output permissions."
            raise AnalysisError(f"{stage}: {message}") from None
