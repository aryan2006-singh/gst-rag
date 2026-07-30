"""Statistics and judge-validation tests.

The properties tested here are the ones that make the difference between a
significance test that protects you and one that manufactures false confidence.
"""

from __future__ import annotations

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.eval.agreement import (  # noqa: E402
    cohens_kappa,
    evaluate_judge,
    interpret_kappa,
    krippendorff_alpha_nominal,
)
from src.eval.stats import (  # noqa: E402
    bootstrap_ci,
    compare,
    holm_bonferroni,
    paired_permutation_test,
    required_sample_size,
)


# ------------------------------------------------------------------ bootstrap
def test_bootstrap_ci_contains_point_estimate():
    values = [0.0, 1.0] * 50
    interval = bootstrap_ci(values, iterations=2000, seed=1)
    assert interval.point == pytest.approx(0.5)
    assert interval.low < interval.point < interval.high


def test_bootstrap_ci_narrows_with_more_data():
    rng = random.Random(0)
    small = [rng.random() for _ in range(20)]
    large = [rng.random() for _ in range(2000)]
    narrow = bootstrap_ci(large, iterations=2000, seed=1)
    wide = bootstrap_ci(small, iterations=2000, seed=1)
    assert (narrow.high - narrow.low) < (wide.high - wide.low)


def test_bootstrap_ci_zero_width_on_constant_data():
    interval = bootstrap_ci([0.7] * 40, iterations=500, seed=1)
    assert interval.low == pytest.approx(0.7)
    assert interval.high == pytest.approx(0.7)


def test_bootstrap_is_deterministic_given_seed():
    values = [random.Random(3).random() for _ in range(50)]
    a = bootstrap_ci(values, iterations=1000, seed=7)
    b = bootstrap_ci(values, iterations=1000, seed=7)
    assert (a.low, a.high) == (b.low, b.high)


# ---------------------------------------------------------------- permutation
def test_identical_pipelines_are_not_significant():
    scores = [random.Random(i).random() for i in range(80)]
    assert paired_permutation_test(scores, scores) == 1.0


def test_large_consistent_improvement_is_significant():
    baseline = [0.0] * 60
    variant = [1.0] * 60
    assert paired_permutation_test(baseline, variant, iterations=2000) < 0.01


def test_tiny_improvement_on_small_n_is_not_significant():
    """The whole reason this file exists.

    30 questions, variant wins on 2 of them. Point estimate +0.067 looks like a
    win in a bare table; the test correctly refuses to call it one.
    """
    rng = random.Random(0)
    baseline = [float(rng.random() < 0.7) for _ in range(30)]
    variant = list(baseline)
    flipped = 0
    for i, value in enumerate(variant):
        if value == 0.0 and flipped < 2:
            variant[i] = 1.0
            flipped += 1
    p = paired_permutation_test(baseline, variant, iterations=5000)
    assert p > 0.05


def test_p_value_is_never_zero():
    baseline = [0.0] * 200
    variant = [1.0] * 200
    p = paired_permutation_test(baseline, variant, iterations=1000)
    assert p > 0.0


def test_permutation_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        paired_permutation_test([0.1, 0.2], [0.1])


def test_compare_reports_direction_and_ci():
    baseline = [0.0, 0.0, 1.0, 0.0, 0.0] * 12
    variant = [1.0, 0.0, 1.0, 1.0, 0.0] * 12
    result = compare(baseline, variant, iterations=2000)
    assert result.delta > 0
    assert result.delta_ci.low < result.delta < result.delta_ci.high
    assert result.significant


# ------------------------------------------------------------ multiple testing
def test_holm_bonferroni_is_stricter_than_raw_alpha():
    p_values = {"v1": 0.04, "v2": 0.04, "v3": 0.04, "v4": 0.04, "v5": 0.04}
    verdicts = holm_bonferroni(p_values, alpha=0.05)
    # All five are "significant" at raw 0.05, none survive correction:
    # smallest must beat 0.05/5 = 0.01.
    assert not any(verdicts.values())


def test_holm_bonferroni_keeps_a_strong_result():
    p_values = {"strong": 0.0001, "weak": 0.4}
    verdicts = holm_bonferroni(p_values, alpha=0.05)
    assert verdicts["strong"] is True
    assert verdicts["weak"] is False


def test_holm_stops_at_first_failure():
    # 0.001 passes (0.05/3), 0.03 fails (0.05/2 = 0.025), so 0.04 must also fail
    # even though 0.04 < 0.05/1.
    verdicts = holm_bonferroni({"a": 0.001, "b": 0.03, "c": 0.04}, alpha=0.05)
    assert verdicts == {"a": True, "b": False, "c": False}


def test_required_sample_size_grows_as_effect_shrinks():
    assert required_sample_size(0.10) < required_sample_size(0.03)
    # Detecting a 3-point improvement needs hundreds of questions.
    assert required_sample_size(0.03) > 500


# -------------------------------------------------------------------- kappa
def test_kappa_perfect_agreement():
    labels = [True] * 8 + [False] * 2
    assert cohens_kappa(labels, labels) == pytest.approx(1.0)


def test_kappa_zero_for_degenerate_always_yes_judge():
    """The reason we report kappa and not raw agreement.

    Human says faithful 8/10. A judge that says 'faithful' every time gets 80%
    raw agreement and is worthless. Kappa = 0.
    """
    human = [True] * 8 + [False] * 2
    judge = [True] * 10
    report = evaluate_judge(human, judge)
    assert report.raw_agreement == pytest.approx(0.8)
    assert report.cohens_kappa == pytest.approx(0.0, abs=1e-9)
    assert not report.trustworthy


def test_kappa_negative_when_worse_than_chance():
    human = [True, True, False, False]
    judge = [False, False, True, True]
    assert cohens_kappa(human, judge) < 0


def test_kappa_undefined_case_returns_zero():
    # Both raters used one identical label: agreement total, information zero.
    assert cohens_kappa([True] * 5, [True] * 5) == 0.0


def test_evaluate_judge_report_contents():
    human = [True] * 20 + [False] * 20
    judge = [True] * 18 + [False] * 2 + [False] * 17 + [True] * 3
    report = evaluate_judge(human, judge)
    assert report.n == 40
    assert 0.5 < report.cohens_kappa < 1.0
    assert report.trustworthy
    assert set(report.per_label) == {True, False}
    assert report.per_label[True]["support"] == 20.0
    assert "substantial" in str(report) or "moderate" in str(report)


def test_interpret_kappa_bands():
    assert interpret_kappa(-0.1) == "worse than chance"
    assert interpret_kappa(0.1) == "poor"
    assert interpret_kappa(0.5) == "moderate"
    assert interpret_kappa(0.7) == "substantial"
    assert interpret_kappa(0.9) == "near-perfect"


def test_trustworthy_requires_enough_examples():
    human = [True, False] * 5
    report = evaluate_judge(human, human)  # perfect agreement, but n=10
    assert report.cohens_kappa == pytest.approx(1.0)
    assert not report.trustworthy


def test_mismatched_lengths_rejected():
    with pytest.raises(ValueError):
        cohens_kappa([True, False], [True])


# ------------------------------------------------------------ krippendorff
def test_krippendorff_perfect_agreement():
    ratings = [[1, 1], [0, 0], [1, 1], [0, 0]] * 3
    assert krippendorff_alpha_nominal(ratings) == pytest.approx(1.0)


def test_krippendorff_handles_missing_values():
    ratings = [[1, 1], [0, None], [1, 1], [0, 0]]
    alpha = krippendorff_alpha_nominal(ratings)
    assert -1.0 <= alpha <= 1.0


def test_krippendorff_low_for_disagreement():
    ratings = [[1, 0], [0, 1], [1, 0], [0, 1]] * 3
    assert krippendorff_alpha_nominal(ratings) < 0.1
