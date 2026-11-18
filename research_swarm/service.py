"""Transport-independent, bounded access to the existing specialists."""
import asyncio
from dataclasses import replace
import hashlib
from io import BytesIO
from pathlib import Path, PureWindowsPath
import re
import threading
from uuid import uuid4

from research_swarm.config import Settings
from research_swarm.agents.pdf_master import PDFMaster
from research_swarm.agents.summary_agent import SummaryAgent
from research_swarm.agents.questions_agent import QuestionsAgent
from research_swarm.agents.literature_agent import LiteratureAgent
from research_swarm.llm import LLM
from research_swarm.models import (PaperSource, SourcePage, AnalysisResponse, ScientificPaperData,
    Questions, LiteratureRecord, SummaryResponse, QuestionsResponse, LiteratureResponse)
from research_swarm.prompt_loader import prompt_fingerprint
from research_swarm.tools.openalex import OpenAlexClient
from research_swarm.budgets import document_budget, timeboxed
from research_swarm.corpus.config import CorpusConfig
from research_swarm.corpus.ingest import CorpusPipeline
from research_swarm.corpus.qa import CorpusQA
from research_swarm.corpus.retrieval import EvidenceRetrieval


class ResearchService:
    def __init__(self, pdf_root: Path, output_root: Path, settings: Settings | None = None,
                 corpus_config: CorpusConfig | None = None):
        self.pdf_root = Path(pdf_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.settings = settings or Settings.from_env()
        self.corpus_config = corpus_config or CorpusConfig.from_env()
        self._worker = threading.Lock()

    def _run_async(self, awaitable):
        async def run():
            with document_budget(self.settings.document_timeout):
                return await timeboxed(awaitable,self.settings.document_timeout,"MCP operation")
        return asyncio.run(run())

    def read_pdf(self, relative_path: str) -> bytes:
        if not relative_path or Path(relative_path).is_absolute():
            raise ValueError("Provide a relative PDF path inside the configured PDF root.")
        if any(":" in part or PureWindowsPath(part).is_reserved() for part in Path(relative_path).parts):
            raise ValueError("Reserved Windows device names and alternate data streams are not PDF paths.")
        path = (self.pdf_root / relative_path).resolve()
        if not path.is_relative_to(self.pdf_root) or path.suffix.lower() != ".pdf":
            raise ValueError("PDF path is outside the configured root or is not a PDF.")
        try:
            with path.open("rb") as stream:
                data = stream.read(self.settings.max_pdf_bytes + 1)
        except OSError:
            raise ValueError("PDF is unavailable inside the configured root.") from None
        if not data or len(data) > self.settings.max_pdf_bytes:
            raise ValueError("PDF is empty or exceeds the configured byte limit.")
        return data

    def _source(self, data):
        extraction = PDFMaster(self.settings).extract(data)
        pages = [SourcePage(page=number, text=text) for number, text in extraction.pages.items()]
        return extraction, PaperSource(sha256=hashlib.sha256(data).hexdigest(),
            pages=pages, warnings=extraction.warnings)

    async def _bounded(self, operation):
        def work():
            if not self._worker.acquire(blocking=False):
                raise ValueError("Research worker is busy; retry after the current operation completes.")
            try:
                return operation()
            finally:
                self._worker.release()
        # The lock belongs to the worker, so client cancellation cannot free a still-running worker.
        return await asyncio.to_thread(work)

    async def extract(self, relative_path: str) -> PaperSource:
        return await self._bounded(lambda: self._source(self.read_pdf(relative_path))[1])

    async def ingest(self, relative_path: str, title: str, doi: str | None = None) -> dict:
        def work():
            data = self.read_pdf(relative_path)
            pipeline = CorpusPipeline(self.corpus_config)
            publication = pipeline.store.add_publication(title, doi, document_sha=hashlib.sha256(data).hexdigest())
            identifier = pipeline.collect(publication, BytesIO(data))
            pipeline.process(identifier)
            return pipeline.store.document(identifier)
        return await self._bounded(work)

    async def list_papers(self, limit: int, offset: int) -> list[dict]:
        return await self._bounded(lambda: CorpusPipeline(self.corpus_config).store.documents(limit, offset))

    async def inspect_evidence(self, chunk_id: int) -> dict:
        return await self._bounded(lambda: CorpusPipeline(self.corpus_config).store.evidence(chunk_id))

    async def search_evidence(self, query, **options) -> list[dict]:
        def work():
            pipeline = CorpusPipeline(self.corpus_config)
            retrieval = EvidenceRetrieval(pipeline.store, pipeline.config)
            return self._run_async(retrieval.search(query, **options))
        return await self._bounded(work)

    async def ask_corpus(self, question, **options) -> dict:
        return await self._bounded(lambda: self._run_async(
            CorpusQA(CorpusPipeline(self.corpus_config), self.settings).ask(question, **options)))

    async def summarize(self, relative_path: str, mode: str = "FAST_RESEARCH_MODE") -> SummaryResponse:
        settings = replace(self.settings, research_mode=mode)
        def work():
            extraction, source = self._source(self.read_pdf(relative_path))
            summary, _ = self._run_async(SummaryAgent(LLM(settings=settings),settings).summarize(extraction.text))
            return SummaryResponse(summary=summary, source=source, mode=mode,
                prompt_variant=settings.prompt_variant, synthetic=settings.local_test_mode)
        return await self._bounded(work)

    async def questions(self, relative_path: str) -> QuestionsResponse:
        # Reuse the same bounded summary/evidence contract as direct agent callers.
        def work():
            extraction, source = self._source(self.read_pdf(relative_path))
            async def run():
                llm = LLM(settings=self.settings)
                summary, evidence = await SummaryAgent(llm,self.settings).summarize(extraction.text)
                questions = await QuestionsAgent(llm,self.settings.max_questions,self.settings.prompt_variant).find(evidence,summary)
                return QuestionsResponse(questions=questions, source=source,
                    summary=summary, synthetic=self.settings.local_test_mode)
            return self._run_async(run())
        return await self._bounded(work)

    async def literature(self, questions: Questions) -> LiteratureResponse:
        def work():
            class OfflineSearch:
                async def search(self, query, limit):
                    return []
            client = OfflineSearch() if self.settings.local_test_mode else OpenAlexClient(self.settings.openalex_key)
            agent = LiteratureAgent(LLM(settings=self.settings),client,self.settings.papers_per_question,self.settings.prompt_variant)
            markdown, warnings = self._run_async(agent.search(questions))
            records = [LiteratureRecord.model_validate(row).model_dump() for row in agent.records]
            return LiteratureResponse(papers=records, markdown=markdown, warnings=warnings,
                synthetic=self.settings.local_test_mode)
        return await self._bounded(work)

    async def analyze(self, relative_path: str, mode: str = "FAST_RESEARCH_MODE") -> AnalysisResponse:
        from orchestrator import Orchestrator
        settings = replace(self.settings, research_mode=mode)
        def work():
            data = self.read_pdf(relative_path)
            _, source = self._source(data)
            run_id = uuid4().hex
            directory = self.output_root / run_id
            result = self._run_async(Orchestrator(settings,directory).run(data))
            response = AnalysisResponse(run_id=run_id, source=source,
                data=ScientificPaperData.model_validate(result.structured), warnings=result.warnings,
                provider=settings.provider, model=settings.model, prompt_variant=settings.prompt_variant,
                prompt_fingerprint=prompt_fingerprint(), synthetic=settings.local_test_mode)
            temporary = directory / "analysis.json.tmp"
            temporary.write_text(response.model_dump_json(indent=2),encoding="utf-8")
            temporary.replace(directory / "analysis.json")
            return response
        return await self._bounded(work)

    async def result(self, run_id: str) -> AnalysisResponse:
        if not re.fullmatch(r"[a-f0-9]{32}",run_id):
            raise ValueError("Invalid analysis identifier.")
        try:
            path = (self.output_root / run_id / "analysis.json").resolve()
            if not path.is_relative_to(self.output_root):
                raise ValueError("Saved analysis is outside the configured output root.")
            content = await asyncio.to_thread(path.read_text,encoding="utf-8")
            return AnalysisResponse.model_validate_json(content)
        except (OSError,ValueError):
            raise ValueError("No valid completed analysis exists for this identifier.") from None
