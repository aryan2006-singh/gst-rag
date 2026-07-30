"""Answer-quality judging: faithfulness, correctness, abstention.

Three backends, all local, in increasing order of cost:

  * `HeuristicJudge`  — no model. Lexical grounding + numeric-claim checking.
    Surprisingly strong for faithfulness in a domain full of rates and section
    numbers, and it is the honest baseline your LLM judge must beat.
  * `NLIJudge`        — a small entailment cross-encoder. Faithfulness becomes
    "does the retrieved context entail each sentence of the answer", which is
    what faithfulness actually means. ~100MB, CPU-viable.
  * `LocalLLMJudge`   — a small instruct model with an explicit rubric.

Whichever you use, `src/eval/agreement.py` must show it tracks *your* human
labels before any judged number goes in your results table. An unvalidated
LLM-judge score is a vibe with three decimal places.

The rubric below is deliberately binary per criterion. Asking a small model for a
1-5 score produces noise concentrated on 3 and 4; asking a yes/no question with
explicit criteria produces something you can actually compute a kappa against.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Judgment:
    faithful: bool
    correct: bool
    abstained: bool
    faithfulness_score: float  # [0,1], fraction of claims grounded
    unsupported_claims: list[str]
    rationale: str = ""


class Judge(Protocol):
    name: str

    def judge(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Judgment:
        ...


# --------------------------------------------------------------------------- #

ABSTENTION_MARKERS = (
    "i don't know",
    "i do not know",
    "not covered",
    "no relevant provision",
    "cannot determine",
    "insufficient information",
    "not found in the provided",
    "unable to answer",
)

NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
SECTION_REF_RE = re.compile(r"\b(?:section|rule)\s+\d+[A-Z]?(?:\(\d+\))*", re.IGNORECASE)


def detect_abstention(answer: str) -> bool:
    lowered = answer.lower()
    return any(marker in lowered for marker in ABSTENTION_MARKERS)


def split_claims(answer: str) -> list[str]:
    from src.index.chunking import split_sentences

    return [s for s in split_sentences(answer) if len(s.split()) >= 4]


class HeuristicJudge:
    """No model. Checks that every number and statutory citation in the answer
    appears in the retrieved context.

    Rationale: in tax QA, the hallucinations that matter are wrong *rates*, wrong
    *section numbers*, and wrong *dates* — all of which are surface tokens you can
    check exactly. This catches the dangerous errors and misses the subtle ones,
    which is a much better failure profile than the reverse.
    """

    name = "heuristic"

    def __init__(self, min_token_overlap: float = 0.5) -> None:
        self.min_token_overlap = min_token_overlap

    def judge(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Judgment:
        from src.index.bm25 import tokenize

        if detect_abstention(answer):
            return Judgment(True, False, True, 1.0, [], "abstained")

        context_blob = " ".join(contexts)
        context_lower = context_blob.lower()
        context_numbers = set(NUMBER_RE.findall(context_blob))
        context_sections = {s.lower() for s in SECTION_REF_RE.findall(context_blob)}
        context_tokens = set(tokenize(context_blob))

        unsupported: list[str] = []
        claims = split_claims(answer) or [answer]
        grounded = 0
        for claim in claims:
            numbers = set(NUMBER_RE.findall(claim))
            sections = {s.lower() for s in SECTION_REF_RE.findall(claim)}
            claim_tokens = set(tokenize(claim))

            bad_number = bool(numbers - context_numbers)
            bad_section = bool(sections - context_sections)
            overlap = (
                len(claim_tokens & context_tokens) / len(claim_tokens)
                if claim_tokens
                else 1.0
            )
            if bad_number or bad_section or overlap < self.min_token_overlap:
                reason = (
                    "ungrounded number" if bad_number
                    else "ungrounded citation" if bad_section
                    else f"low overlap {overlap:.2f}"
                )
                unsupported.append(f"{claim}  [{reason}]")
            else:
                grounded += 1

        score = grounded / len(claims) if claims else 0.0
        correct = self._correct(answer, reference, context_lower)
        return Judgment(
            faithful=score >= 0.99,
            correct=correct,
            abstained=False,
            faithfulness_score=score,
            unsupported_claims=unsupported,
            rationale=f"{grounded}/{len(claims)} claims grounded",
        )

    @staticmethod
    def _correct(answer: str, reference: str | None, context_lower: str) -> bool:
        """Correctness needs a reference; without one this is not a judgement."""
        if not reference:
            return False
        answer_numbers = set(NUMBER_RE.findall(answer))
        reference_numbers = set(NUMBER_RE.findall(reference))
        if reference_numbers:
            # If the reference answer is numeric, the number must match. This is
            # the single highest-signal correctness check in a tax domain.
            return bool(reference_numbers & answer_numbers)
        from src.index.bm25 import tokenize

        ref_tokens = set(tokenize(reference))
        ans_tokens = set(tokenize(answer))
        if not ref_tokens:
            return False
        return len(ref_tokens & ans_tokens) / len(ref_tokens) >= 0.6


class NLIJudge:
    """Entailment-based faithfulness with a small cross-encoder.

    Model: cross-encoder/nli-deberta-v3-small (or MoritzLaurer/DeBERTa-v3-base-mnli).
    For each answer sentence, ask whether the concatenated retrieved context
    entails it. This is the closest cheap approximation to what RAGAS's
    faithfulness metric does, without an API key.
    """

    name = "nli"

    def __init__(
        self,
        model_name: str = "cross-encoder/nli-deberta-v3-small",
        device: str = "cpu",
        entailment_threshold: float = 0.5,
    ) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, device=device)
        self.threshold = entailment_threshold
        self.name = f"nli:{model_name}"
        self.fallback = HeuristicJudge()

    def judge(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Judgment:
        if detect_abstention(answer):
            return Judgment(True, False, True, 1.0, [], "abstained")

        claims = split_claims(answer) or [answer]
        premise = " ".join(contexts)
        scores = self.model.predict([(premise, claim) for claim in claims])

        unsupported: list[str] = []
        grounded = 0
        for claim, score in zip(claims, scores):
            # CrossEncoder NLI heads return [contradiction, entailment, neutral]
            # for the deberta MNLI models; take the entailment column when the
            # output is multi-class.
            value = float(score[1]) if hasattr(score, "__len__") else float(score)
            if value >= self.threshold:
                grounded += 1
            else:
                unsupported.append(f"{claim}  [entailment {value:.2f}]")

        base = self.fallback.judge(question, answer, contexts, reference)
        score = grounded / len(claims)
        return Judgment(
            faithful=score >= 0.99,
            correct=base.correct,
            abstained=False,
            faithfulness_score=score,
            unsupported_claims=unsupported,
            rationale=f"NLI entailment {grounded}/{len(claims)}",
        )


RUBRIC = """You are grading an answer to a question about Indian GST law.

You are given the QUESTION, the retrieved CONTEXT passages, and the ANSWER.

Answer these two questions independently. Judge only what is written; do not use
your own knowledge of GST law.

1. FAITHFUL: Is every factual claim in the ANSWER — every rate, date, section
   number, and condition — directly supported by the CONTEXT? If the ANSWER adds
   any fact not present in the CONTEXT, answer no, even if that fact is true.

2. CORRECT: Does the ANSWER match the REFERENCE ANSWER in substance? Differences
   in wording, length, or extra correct detail do not matter. A different rate,
   a different section number, or an opposite conclusion does matter.

Reply in exactly this format and nothing else:
FAITHFUL: yes|no
CORRECT: yes|no
REASON: <one sentence>"""


class LocalLLMJudge:
    """Small local instruct model + the rubric above.

    Suggested models that run on CPU: Qwen2.5-1.5B-Instruct, Llama-3.2-3B-Instruct.
    Expect several seconds per judgement on CPU — that is ~20 minutes for a
    250-question run, which is fine as a nightly CI job and painful interactively.
    Cache judgements by (question, answer, context) hash.
    """

    name = "local-llm"

    def __init__(self, generator, rubric: str = RUBRIC) -> None:
        self.generator = generator
        self.rubric = rubric
        self.fallback = HeuristicJudge()

    def judge(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Judgment:
        if detect_abstention(answer):
            return Judgment(True, False, True, 1.0, [], "abstained")

        prompt = (
            f"{self.rubric}\n\n"
            f"QUESTION: {question}\n\n"
            f"CONTEXT:\n" + "\n---\n".join(contexts) + "\n\n"
            f"REFERENCE ANSWER: {reference or '(none provided)'}\n\n"
            f"ANSWER: {answer}\n\n"
        )
        raw = self.generator(prompt)
        faithful = _parse_yes_no(raw, "FAITHFUL")
        correct = _parse_yes_no(raw, "CORRECT")
        reason_match = re.search(r"REASON:\s*(.+)", raw)

        if faithful is None or correct is None:
            # A judge that fails to follow its own output format is not a judge.
            # Fall back rather than silently coercing a malformed reply to False.
            base = self.fallback.judge(question, answer, contexts, reference)
            base.rationale = f"llm judge unparseable, fell back: {raw[:120]!r}"
            return base

        return Judgment(
            faithful=faithful,
            correct=correct,
            abstained=False,
            faithfulness_score=1.0 if faithful else 0.0,
            unsupported_claims=[],
            rationale=reason_match.group(1).strip() if reason_match else "",
        )


def _parse_yes_no(text: str, field: str) -> bool | None:
    match = re.search(rf"{field}:\s*(yes|no)", text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "yes"


class StubJudge:
    """Deterministic judge for tests: faithful iff every answer token is in context."""

    name = "stub"

    def judge(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Judgment:
        from src.index.bm25 import tokenize

        if detect_abstention(answer):
            return Judgment(True, False, True, 1.0, [], "abstained")
        answer_tokens = set(tokenize(answer))
        context_tokens = set(tokenize(" ".join(contexts)))
        missing = answer_tokens - context_tokens
        score = 1.0 - (len(missing) / len(answer_tokens) if answer_tokens else 0.0)
        correct = bool(reference) and set(tokenize(reference)) <= answer_tokens
        return Judgment(
            faithful=not missing,
            correct=correct,
            abstained=False,
            faithfulness_score=score,
            unsupported_claims=sorted(missing)[:5],
        )
