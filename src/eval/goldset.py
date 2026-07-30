"""The gold set: schema, loading, and validation.

This file is short and the gold set is the hardest part of the project. That is
not a contradiction — the difficulty is in the *labelling*, which is manual, and
the code's only job is to stop you from fooling yourself.

Rules the validator enforces, each because it corresponds to a way people
accidentally inflate their numbers:

  * Every question must cite at least one relevant chunk id, and those ids must
    exist in the index. A typo'd id silently makes a question unanswerable and
    drags every pipeline down equally, hiding real differences.
  * `source` must not be "llm_generated" for more than a stated fraction. LLM
    questions are paraphrases of chunks you already have, so retrieval on them is
    trivially easy and your Recall@5 will look wonderful and mean nothing.
  * Questions must be deduplicated by normalised text.
  * A `split` field ("dev" / "test"). You will tune chunk size, rrf_k, and
    rerank depth. If you tune on the same questions you report, you have
    reported your training accuracy.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

VALID_SOURCES = {
    "forum",  # e.g. a real practitioner question from a public forum
    "faq",  # official CBIC FAQ
    "exam",  # CA/CS exam question
    "practitioner",  # written by you or a domain expert
    "llm_generated",  # synthetic — keep this a small minority
}

VALID_TYPES = {
    "factual",  # "what is the rate on X"
    "procedural",  # "how do I file Y"
    "conditional",  # "can I claim ITC if ..."
    "temporal",  # "what was the rate in FY 2019-20"  <- supersession matters
    "multi_hop",  # requires combining two provisions
    "unanswerable",  # deliberately not covered by the corpus
}


@dataclass
class GoldQuestion:
    question_id: str
    question: str
    relevant_chunk_ids: list[str]
    source: str
    question_type: str = "factual"
    split: str = "dev"
    reference_answer: str | None = None
    graded_relevance: dict[str, float] = field(default_factory=dict)
    as_of: str | None = None
    notes: str = ""

    def relevance(self) -> dict[str, float] | set[str]:
        """Graded gains if provided, otherwise binary."""
        if self.graded_relevance:
            return dict(self.graded_relevance)
        return set(self.relevant_chunk_ids)

    @property
    def is_answerable(self) -> bool:
        return self.question_type != "unanswerable"


def normalize_question(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def load_gold_set(path: str | Path) -> list[GoldQuestion]:
    questions: list[GoldQuestion] = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: bad JSON — {exc}") from exc
            questions.append(GoldQuestion(**record))
    return questions


def save_gold_set(questions: Sequence[GoldQuestion], path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for question in questions:
            handle.write(json.dumps(asdict(question), ensure_ascii=False) + "\n")


@dataclass
class ValidationReport:
    n_questions: int
    errors: list[str]
    warnings: list[str]
    by_source: dict[str, int]
    by_type: dict[str, int]
    by_split: dict[str, int]
    synthetic_fraction: float

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"gold set: {self.n_questions} questions"]
        lines.append(f"  by source: {dict(sorted(self.by_source.items()))}")
        lines.append(f"  by type:   {dict(sorted(self.by_type.items()))}")
        lines.append(f"  by split:  {dict(sorted(self.by_split.items()))}")
        lines.append(f"  synthetic: {self.synthetic_fraction:.0%}")
        for warning in self.warnings:
            lines.append(f"  WARN  {warning}")
        for error in self.errors:
            lines.append(f"  ERROR {error}")
        return "\n".join(lines)


def validate_gold_set(
    questions: Sequence[GoldQuestion],
    known_chunk_ids: Iterable[str] | None = None,
    max_synthetic_fraction: float = 0.30,
    min_questions: int = 150,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    known = set(known_chunk_ids) if known_chunk_ids is not None else None

    seen_ids: set[str] = set()
    seen_text: dict[str, str] = {}
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_split: dict[str, int] = {}

    for question in questions:
        qid = question.question_id
        if qid in seen_ids:
            errors.append(f"duplicate question_id {qid!r}")
        seen_ids.add(qid)

        normalized = normalize_question(question.question)
        if normalized in seen_text:
            errors.append(
                f"{qid}: duplicate question text (same as {seen_text[normalized]})"
            )
        seen_text[normalized] = qid

        if question.source not in VALID_SOURCES:
            errors.append(f"{qid}: unknown source {question.source!r}")
        if question.question_type not in VALID_TYPES:
            errors.append(f"{qid}: unknown question_type {question.question_type!r}")
        if question.split not in ("dev", "test"):
            errors.append(f"{qid}: split must be 'dev' or 'test'")

        by_source[question.source] = by_source.get(question.source, 0) + 1
        by_type[question.question_type] = by_type.get(question.question_type, 0) + 1
        by_split[question.split] = by_split.get(question.split, 0) + 1

        if question.is_answerable and not question.relevant_chunk_ids:
            errors.append(f"{qid}: answerable question with no relevant_chunk_ids")
        if not question.is_answerable and question.relevant_chunk_ids:
            errors.append(f"{qid}: unanswerable question should have no gold chunks")

        if known is not None:
            missing = [c for c in question.relevant_chunk_ids if c not in known]
            if missing:
                errors.append(f"{qid}: relevant_chunk_ids not in index: {missing[:3]}")

        for chunk_id, gain in question.graded_relevance.items():
            if chunk_id not in question.relevant_chunk_ids:
                errors.append(f"{qid}: graded_relevance id {chunk_id!r} not in relevant list")
            if gain < 0:
                errors.append(f"{qid}: negative relevance gain for {chunk_id!r}")

        if question.question_type == "temporal" and not question.as_of:
            warnings.append(f"{qid}: temporal question with no as_of date")

    n = len(questions)
    synthetic = by_source.get("llm_generated", 0)
    fraction = synthetic / n if n else 0.0
    if fraction > max_synthetic_fraction:
        errors.append(
            f"{fraction:.0%} of questions are llm_generated (limit "
            f"{max_synthetic_fraction:.0%}). Synthetic questions are paraphrases of "
            f"chunks you already indexed, so they overstate retrieval quality."
        )
    if n < min_questions:
        warnings.append(
            f"only {n} questions; at n={n} the 95% CI on Recall@5 is roughly "
            f"+/-{1.96 * (0.25 / max(n, 1)) ** 0.5:.02f}, so small differences "
            f"between pipelines will not be detectable"
        )
    if by_split.get("test", 0) == 0:
        warnings.append("no test split — you will end up reporting tuned-on numbers")
    if by_type.get("unanswerable", 0) == 0:
        warnings.append(
            "no unanswerable questions — you cannot measure whether the system "
            "abstains, which is the failure mode that matters most in law"
        )

    return ValidationReport(
        n_questions=n,
        errors=errors,
        warnings=warnings,
        by_source=by_source,
        by_type=by_type,
        by_split=by_split,
        synthetic_fraction=fraction,
    )
