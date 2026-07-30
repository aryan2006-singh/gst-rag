"""Confidence intervals and significance tests for retrieval comparisons.

Why this file exists
--------------------
On a 250-question gold set, the standard error of Recall@5 is roughly
sqrt(0.25/250) ~= 0.032. So a pipeline scoring 0.71 and one scoring 0.74 are
**indistinguishable**, and an ablation table that reports them as an improvement
is reporting noise.

Nearly every RAG project you will compete against reports bare point estimates.
Reporting a confidence interval and a paired significance test is cheap, takes
one file, and is the difference between "I tuned some knobs" and "I ran an
experiment".

Use the paired test, not the unpaired one. Both pipelines are evaluated on the
same questions, so the pairing removes question difficulty as a source of
variance and gives you far more power on a small gold set.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float
    n: int

    def __str__(self) -> str:
        return f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}]"

    def markdown(self) -> str:
        return f"{self.point:.3f}<br><sub>[{self.low:.3f}, {self.high:.3f}]</sub>"


@dataclass(frozen=True)
class Comparison:
    baseline_mean: float
    variant_mean: float
    delta: float
    delta_ci: Interval
    p_value: float
    n: int
    significant: bool

    def __str__(self) -> str:
        verdict = "significant" if self.significant else "NOT significant"
        return (
            f"{self.baseline_mean:.3f} -> {self.variant_mean:.3f} "
            f"(delta {self.delta:+.3f}, 95% CI [{self.delta_ci.low:+.3f}, "
            f"{self.delta_ci.high:+.3f}], p={self.p_value:.4f}, {verdict})"
        )


def bootstrap_ci(
    values: Sequence[float],
    confidence: float = 0.95,
    iterations: int = 10_000,
    seed: int = 0,
) -> Interval:
    """Percentile bootstrap CI for the mean of per-question scores.

    Resamples questions with replacement. Non-parametric, so it makes no
    normality assumption — which matters because metrics like Recall@5 are
    bounded in [0, 1] and often bimodal (a question is usually either solved or
    not).
    """
    if not values:
        raise ValueError("no values")
    if len(values) == 1:
        only = float(values[0])
        return Interval(only, only, only, 1)

    rng = random.Random(seed)
    n = len(values)
    point = sum(values) / n

    means = []
    for _ in range(iterations):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()

    alpha = (1.0 - confidence) / 2.0
    low = means[int(alpha * iterations)]
    high = means[min(int((1.0 - alpha) * iterations), iterations - 1)]
    return Interval(point, low, high, n)


def paired_permutation_test(
    baseline: Sequence[float],
    variant: Sequence[float],
    iterations: int = 10_000,
    seed: int = 0,
) -> float:
    """Two-sided p-value for the mean paired difference.

    Under the null hypothesis that the two pipelines are exchangeable on each
    question, flipping the sign of any question's difference is equally likely.
    We sample that null directly rather than assuming a t-distribution.

    Returns a p-value with add-one smoothing, so it is never exactly 0 — you
    cannot claim more certainty than your iteration count supports.
    """
    if len(baseline) != len(variant):
        raise ValueError("paired test needs equal-length score vectors")
    if not baseline:
        raise ValueError("no values")

    diffs = [v - b for b, v in zip(baseline, variant)]
    observed = abs(sum(diffs) / len(diffs))

    # If every question is a tie, there is nothing to test.
    if all(d == 0 for d in diffs):
        return 1.0

    rng = random.Random(seed)
    at_least_as_extreme = 0
    for _ in range(iterations):
        total = 0.0
        for d in diffs:
            total += d if rng.random() < 0.5 else -d
        if abs(total / len(diffs)) >= observed - 1e-12:
            at_least_as_extreme += 1
    return (at_least_as_extreme + 1) / (iterations + 1)


def compare(
    baseline: Sequence[float],
    variant: Sequence[float],
    alpha: float = 0.05,
    iterations: int = 10_000,
    seed: int = 0,
) -> Comparison:
    """Full paired comparison: means, bootstrap CI on the delta, permutation p."""
    if len(baseline) != len(variant):
        raise ValueError("paired comparison needs equal-length score vectors")
    diffs = [v - b for b, v in zip(baseline, variant)]
    delta_ci = bootstrap_ci(diffs, iterations=iterations, seed=seed)
    p_value = paired_permutation_test(baseline, variant, iterations=iterations, seed=seed)
    return Comparison(
        baseline_mean=sum(baseline) / len(baseline),
        variant_mean=sum(variant) / len(variant),
        delta=delta_ci.point,
        delta_ci=delta_ci,
        p_value=p_value,
        n=len(baseline),
        significant=p_value < alpha,
    )


def holm_bonferroni(p_values: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Correct for testing many pipeline variants against one baseline.

    Five variants at alpha=0.05 gives roughly a 23% chance of at least one false
    positive. Holm-Bonferroni controls the family-wise error rate and is
    uniformly more powerful than plain Bonferroni, so there is no reason to use
    plain Bonferroni.
    """
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    verdicts: dict[str, bool] = {}
    rejected_so_far = True
    for index, (name, p) in enumerate(ordered):
        threshold = alpha / (m - index)
        if rejected_so_far and p <= threshold:
            verdicts[name] = True
        else:
            rejected_so_far = False
            verdicts[name] = False
    return verdicts


def required_sample_size(
    effect: float,
    baseline_variance: float = 0.25,
    power: float = 0.8,
    alpha: float = 0.05,
) -> int:
    """Roughly how many gold questions to detect `effect` on a paired metric.

    Normal approximation, so treat it as an order-of-magnitude guide for how big
    to make your gold set — not as a precise number. The useful takeaway is that
    detecting a 3-point Recall@5 improvement needs *hundreds* of questions, which
    is why "150-300" is the right target and 30 is not.
    """
    z_alpha = 1.959963985  # two-sided 0.05
    z_beta = 0.8416212336  # power 0.8
    if effect <= 0:
        raise ValueError("effect must be positive")
    n = ((z_alpha + z_beta) ** 2) * baseline_variance / (effect**2)
    return math.ceil(n)
