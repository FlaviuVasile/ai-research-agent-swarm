"""Structured outputs used between specialists."""
from dataclasses import dataclass, field
from pydantic import BaseModel, ConfigDict, Field

class ResearchQuestion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    why_it_matters: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(min_length=1, max_length=2000)
    kind: str = Field(min_length=1, max_length=100,
                      description="Explicit limitation or inferred research opportunity")
    search_query: str = Field(min_length=1, max_length=300)

class Questions(BaseModel):
    questions: list[ResearchQuestion] = Field(min_length=1, max_length=8)

class Relevance(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    explanation: str = Field(min_length=1, max_length=1800)

@dataclass
class Extraction:
    text: str
    warnings: list[str] = field(default_factory=list)
    pages: dict[int, str] = field(default_factory=dict)

@dataclass
class AnalysisResult:
    files: dict[str, str]
    warnings: list[str]
    output_dir: str
    structured: dict = field(default_factory=dict)


class SourcePage(BaseModel):
    page: int = Field(ge=1)
    text: str


class PaperSource(BaseModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pages: list[SourcePage]
    warnings: list[str] = Field(default_factory=list)


class LiteratureRecord(BaseModel):
    question: str
    search_query: str
    openalex_id: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    relevance: Relevance
    evidence_scope: str = "title only"


class ScientificPaperData(BaseModel):
    summary: str
    questions: Questions
    literature: list[LiteratureRecord]
    coverage: str


class AnalysisResponse(BaseModel):
    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    source: PaperSource
    data: ScientificPaperData
    warnings: list[str]
    provider: str
    model: str
    prompt_variant: str
    prompt_fingerprint: str
    synthetic: bool


class SummaryResponse(BaseModel):
    summary: str
    source: PaperSource
    mode: str
    prompt_variant: str
    synthetic: bool


class QuestionsResponse(BaseModel):
    questions: Questions
    source: PaperSource
    summary: str
    synthetic: bool


class LiteratureResponse(BaseModel):
    papers: list[LiteratureRecord]
    markdown: str
    warnings: list[str]
    synthetic: bool
