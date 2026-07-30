"""Judge validation: does your LLM judge agree with a human?

An LLM-as-judge score is worthless until you have shown it tracks human
judgement on *your* data. This is the step almost every RAG project skips, and
it is the cheapest credibility you can buy: label 50 examples yourself, compute
agreement, report it next to every judged metric.

Report Cohen's kappa, not raw agreement. If 85% of your answers are faithful,
a judge that says "faithful" every single time scores 85% raw agreement and is
completely uninformative. Kappa corrects for that chance agreement — the same
degenerate judge scores kappa = 0.

Rough reading of kappa (Landis & Koch, and treat these as soft guidance):
    < 0.20   poor          — do not report judged metrics
    0.21-0.40 fair         — usable only for coarse directional claims
    0.41-0.60 moderate     — acceptable; state the kappa everywhere
    0.61-0.80 substantial  — good enough to gate CI on
    > 0.80   near-perfect  — suspicious on subjective labels; check for leakage
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class AgreementReport:
    n: int
    raw_agreement: float
    cohens_kappa: float
    confusion: dict[tuple[object, object], int] = field(default_factory=dict)
    per_label: dict[object, dict[str, float]] = field(default_factory=dict)
    interpretation: str = ""

    def __str__(self) -> str:
        lines = [
            f"n = {self.n}",
            f"raw agreement = {self.raw_agreement:.1%}",
            f"Cohen's kappa = {self.cohens_kappa:.3f} ({self.interpretation})",
        ]
        for label, scores in sorted(self.per_label.items(), key=lambda kv: str(kv[0])):
            lines.append(
                f"  label={label!r}: precision={scores['precision']:.2f} "
                f"recall={scores['recall']:.2f} f1={scores['f1']:.2f} "
                f"(human n={int(scores['support'])})"
            )
        return "\n".join(lines)

    @property
    def trustworthy(self) -> bool:
        """The bar for letting a judged metric into your results table."""
        return self.n >= 30 and self.cohens_kappa >= 0.4


def interpret_kappa(kappa: float) -> str:
    if kappa < 0.0:
        return "worse than chance"
    if kappa <= 0.20:
        return "poor"
    if kappa <= 0.40:
        return "fair"
    if kappa <= 0.60:
        return "moderate"
    if kappa <= 0.80:
        return "substantial"
    return "near-perfect"


def cohens_kappa(human: Sequence, judge: Sequence) -> float:
    """Chance-corrected agreement between two raters on categorical labels.

    kappa = (p_observed - p_chance) / (1 - p_chance)

    >>> # 10 items, both raters say True 8 times and agree on all of them,
    >>> # both say False twice and agree: perfect agreement
    >>> cohens_kappa([True]*8 + [False]*2, [True]*8 + [False]*2)
    1.0
    >>> # degenerate judge that always says True, human says True 8/10
    >>> round(cohens_kappa([True]*8 + [False]*2, [True]*10), 10)
    0.0
    """
    if len(human) != len(judge):
        raise ValueError("rating vectors must be the same length")
    n = len(human)
    if n == 0:
        raise ValueError("no ratings")

    observed = sum(1 for h, j in zip(human, judge) if h == j) / n

    labels = set(human) | set(judge)
    chance = 0.0
    for label in labels:
        p_human = sum(1 for h in human if h == label) / n
        p_judge = sum(1 for j in judge if j == label) / n
        chance += p_human * p_judge

    if abs(1.0 - chance) < 1e-12:
        # Both raters used exactly one label, the same one. Agreement is total
        # but carries no information; kappa is undefined, report 0.
        return 0.0
    return (observed - chance) / (1.0 - chance)


def evaluate_judge(human: Sequence, judge: Sequence) -> AgreementReport:
    """Full validation report for a judge against human labels."""
    if len(human) != len(judge):
        raise ValueError("rating vectors must be the same length")
    n = len(human)
    if n == 0:
        raise ValueError("no ratings")
    if n < 30:
        # Not fatal, but a kappa on 12 examples means nothing.
        pass

    confusion: dict[tuple[object, object], int] = {}
    for h, j in zip(human, judge):
        confusion[(h, j)] = confusion.get((h, j), 0) + 1

    per_label: dict[object, dict[str, float]] = {}
    for label in set(human) | set(judge):
        tp = sum(1 for h, j in zip(human, judge) if h == label and j == label)
        fp = sum(1 for h, j in zip(human, judge) if h != label and j == label)
        fn = sum(1 for h, j in zip(human, judge) if h == label and j != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_label[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(tp + fn),
        }

    kappa = cohens_kappa(human, judge)
    return AgreementReport(
        n=n,
        raw_agreement=sum(1 for h, j in zip(human, judge) if h == j) / n,
        cohens_kappa=kappa,
        confusion=confusion,
        per_label=per_label,
        interpretation=interpret_kappa(kappa),
    )


def krippendorff_alpha_nominal(ratings: Sequence[Sequence]) -> float:
    """Alpha for 2+ raters with possible missing values (None).

    Use when you get a second human to label a subset — reporting inter-*human*
    agreement sets the ceiling for what any judge can achieve. If two humans only
    reach alpha = 0.55, a judge at kappa = 0.60 is already at the noise floor and
    chasing a higher number is wasted effort. Stating this explicitly is a strong
    signal in an interview.

    `ratings` is a list of per-item rating lists, e.g. [[1, 1], [0, None], ...].
    """
    units = [[r for r in item if r is not None] for item in ratings]
    units = [u for u in units if len(u) >= 2]
    if not units:
        raise ValueError("need at least one item rated by 2+ raters")

    labels = sorted({r for unit in units for r in unit}, key=str)
    index = {label: i for i, label in enumerate(labels)}
    size = len(labels)

    coincidence = [[0.0] * size for _ in range(size)]
    for unit in units:
        m = len(unit)
        # Standard coincidence construction: all ordered pairs within a unit,
        # excluding self-pairs, weighted by 1/(m-1).
        for i, a in enumerate(unit):
            for j, b in enumerate(unit):
                if i == j:
                    continue
                coincidence[index[a]][index[b]] += 1.0 / (m - 1)

    total = sum(sum(row) for row in coincidence)
    if total == 0:
        return 1.0
    observed_disagreement = sum(
        coincidence[i][j] for i in range(size) for j in range(size) if i != j
    )
    marginals = [sum(coincidence[i]) for i in range(size)]
    expected_disagreement = (
        sum(marginals[i] * marginals[j] for i in range(size) for j in range(size) if i != j)
        / (total - 1)
    )
    if expected_disagreement == 0:
        return 1.0
    return 1.0 - (observed_disagreement / expected_disagreement)
