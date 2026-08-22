"""Retrieval evaluation suite.

Fixed question set with expected documents/pages/concepts so retrieval quality
can be measured (recall@K, MRR) instead of judged by feel. The questions
target the ``make_search_book_pdf`` fixture corpus.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.search.base import SearchResponse
from mindweaver.search.service import search


class EvalQuestion(BaseModel):
    question: str
    expected_document: str
    expected_pages: list[int] = Field(default_factory=list)
    expected_concepts: list[str] = Field(default_factory=list)
    category: Literal["exact", "semantic", "chapter", "multi_page", "negative"]


EVALUATION_SUITE: list[EvalQuestion] = [
    EvalQuestion(
        question=(
            "What is the faculty by which information is encoded, stored, and "
            "retrieved in the human brain?"
        ),
        expected_document="Search Book",
        expected_pages=[1],
        expected_concepts=["Memory is the faculty"],
        category="exact",
    ),
    EvalQuestion(
        question="How are memories stabilised over time?",
        expected_document="Search Book",
        expected_pages=[3],
        expected_concepts=["Consolidation stabilises memories"],
        category="semantic",
    ),
    EvalQuestion(
        question="What does Chapter 2 discuss?",
        expected_document="Search Book",
        expected_pages=[3, 4],
        expected_concepts=["Consolidation", "Retrieval cues"],
        category="chapter",
    ),
    EvalQuestion(
        question=("Which group achieved the highest recall percentage in the experimental study?"),
        expected_document="Search Book",
        expected_pages=[2],
        expected_concepts=["Recall (%)", "B"],
        category="multi_page",
    ),
    EvalQuestion(
        question="How do whales photosynthesise underwater?",
        expected_document="",
        expected_pages=[],
        expected_concepts=[],
        category="negative",
    ),
]


class EvalResult(BaseModel):
    question: str
    category: str
    hit_count: int
    relevant: bool
    rank: int | None = None


class EvaluationReport(BaseModel):
    total: int
    recall_at_k: float
    mrr: float
    results: list[EvalResult]


def _is_relevant(
    result: SearchResponse,
    question: EvalQuestion,
) -> tuple[bool, int | None]:
    """Whether any top-k hit covers the question, and its rank."""
    if question.category == "negative":
        return (result.total == 0, None)
    for index, hit in enumerate(result.results, start=1):
        text = hit.text
        pages = set(range(hit.page_start, hit.page_end + 1))
        concept_hit = any(concept.lower() in text.lower() for concept in question.expected_concepts)
        page_hit = bool(question.expected_pages) and bool(set(question.expected_pages) & pages)
        if concept_hit or page_hit:
            return (True, index)
    return (False, None)


def run_evaluation(
    session: Session,
    settings: Settings,
    questions: list[EvalQuestion] | None = None,
    *,
    k: int = 5,
) -> EvaluationReport:
    questions = questions or EVALUATION_SUITE
    results: list[EvalResult] = []
    for question in questions:
        response = search(session, settings, question.question, limit=k)
        relevant, rank = _is_relevant(response, question)
        results.append(
            EvalResult(
                question=question.question,
                category=question.category,
                hit_count=len(response.results),
                relevant=relevant,
                rank=rank,
            )
        )

    relevant_items = [result for result in results if result.relevant]
    recall = len(relevant_items) / len(results) if results else 0.0
    rr_values = [1.0 / result.rank for result in relevant_items if result.rank]
    mrr = sum(rr_values) / len(results) if results else 0.0

    return EvaluationReport(
        total=len(results),
        recall_at_k=recall,
        mrr=mrr,
        results=results,
    )
