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

@dataclass
class AnalysisResult:
    files: dict[str, str]
    warnings: list[str]
    output_dir: str
