"""Every metric checked against a value computed by hand.

If these are wrong, every row of the ablation table is wrong, and the project is
worse than useless — it is confidently misleading. So the expected values here
are derived in the comments, not produced by running the code and pasting the
output (which tests nothing except that the code is deterministic).
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.eval.metrics import (  # noqa: E402
    aggregate,
    average_precision,
    dcg,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    score_one,
)


# ------------------------------------------------------------------ recall
def test_recall_counts_relevant_found_not_positions_used():
    # relevant = {a, d}; top-3 = [a, b, c]; found a only -> 1/2
    assert recall_at_k(["a", "b", "c"], {"a", "d"}, 3) == 0.5


def test_recall_denominator_is_all_relevant_not_k():
    # 4 relevant, k=2, both retrieved -> 2/4, NOT 2/2
    assert recall_at_k(["a", "b", "x"], {"a", "b", "c", "d"}, 2) == 0.5


def test_recall_ignores_relevant_below_k():
    assert recall_at_k(["x", "y", "a"], {"a"}, 2) == 0.0
    assert recall_at_k(["x", "y", "a"], {"a"}, 3) == 1.0


def test_duplicates_do_not_inflate_recall():
    # A pipeline returning [a, a, a] has found one chunk, not three.
    assert recall_at_k(["a", "a", "a"], {"a", "b", "c"}, 3) == pytest.approx(1 / 3)


def test_empty_relevant_raises_rather_than_scoring_zero():
    with pytest.raises(ValueError):
        recall_at_k(["a"], set(), 5)


# --------------------------------------------------------------- precision
def test_precision_at_k():
    # top-4 = [a, x, b, y], relevant {a, b} -> 2/4
    assert precision_at_k(["a", "x", "b", "y"], {"a", "b"}, 4) == 0.5


def test_precision_uses_available_length_when_short():
    # only 2 results returned but k=5 -> 1 of 2, not 1 of 5
    assert precision_at_k(["a", "x"], {"a"}, 5) == 0.5


# --------------------------------------------------------------------- hit
def test_hit_at_k_is_binary():
    assert hit_at_k(["x", "a"], {"a"}, 2) == 1.0
    assert hit_at_k(["x", "a"], {"a"}, 1) == 0.0


# --------------------------------------------------------------------- MRR
def test_reciprocal_rank_uses_first_relevant():
    # a at position 3 -> 1/3; b at 4 is irrelevant to the score
    assert reciprocal_rank(["x", "y", "a", "b"], {"a", "b"}) == pytest.approx(1 / 3)


def test_reciprocal_rank_zero_when_absent():
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0


def test_reciprocal_rank_dedupes_before_ranking():
    # [a, a, b] deduped is [a, b]; b is relevant at rank 2 -> 0.5
    assert reciprocal_rank(["a", "a", "b"], {"b"}) == 0.5


# --------------------------------------------------------------------- MAP
def test_average_precision_hand_computed():
    # relevant {a, b}; ranked [a, x, b]
    # hit at 1 -> precision 1/1 = 1.0
    # hit at 3 -> precision 2/3 = 0.6667
    # AP = (1.0 + 0.6667) / 2 = 0.83333
    assert average_precision(["a", "x", "b"], {"a", "b"}) == pytest.approx(5 / 6)


def test_average_precision_penalises_missing_relevant():
    # relevant {a, b, c}; only a retrieved at rank 1
    # AP = (1/1) / 3 = 0.3333  -- divided by |relevant|, not by hits
    assert average_precision(["a", "x", "y"], {"a", "b", "c"}) == pytest.approx(1 / 3)


def test_average_precision_perfect_ranking_is_one():
    assert average_precision(["a", "b"], {"a", "b"}) == 1.0


# -------------------------------------------------------------------- nDCG
def test_dcg_hand_computed():
    # gains [1, 0, 1] -> 1/log2(2) + 0 + 1/log2(4) = 1.0 + 0.5 = 1.5
    assert dcg([1, 0, 1]) == pytest.approx(1.5)


def test_ndcg_hand_computed():
    # relevant {a, b}, ranked [x, a, b]
    # DCG  = 0 + 1/log2(3) + 1/log2(4) = 0.630930 + 0.5      = 1.130930
    # IDCG = 1/log2(2) + 1/log2(3)     = 1.0      + 0.630930 = 1.630930
    # nDCG = 1.130930 / 1.630930 = 0.693425
    expected = (1 / math.log2(3) + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    assert ndcg_at_k(["x", "a", "b"], {"a", "b"}, 3) == pytest.approx(expected)
    assert ndcg_at_k(["x", "a", "b"], {"a", "b"}, 3) == pytest.approx(0.693426, abs=1e-5)


def test_ndcg_perfect_ranking_is_one():
    assert ndcg_at_k(["a", "b", "x"], {"a", "b"}, 3) == pytest.approx(1.0)


def test_ndcg_ideal_uses_all_relevant_not_just_retrieved():
    # THE classic bug: normalising against what was retrieved.
    # relevant {a, b, c}; ranked [a] only.
    # Correct   IDCG over 3 items = 1 + 1/log2(3) + 1/log2(4) = 2.130930
    # Correct   nDCG = 1.0 / 2.130930 = 0.469278
    # Buggy version would normalise by IDCG over 1 item = 1.0 -> nDCG 1.0
    value = ndcg_at_k(["a"], {"a", "b", "c"}, 3)
    assert value == pytest.approx(1.0 / (1 + 1 / math.log2(3) + 1 / math.log2(4)))
    assert value < 0.5


def test_ndcg_graded_relevance():
    # gains a=3, b=1; ranked [b, a]
    # DCG  = 1/log2(2) + 3/log2(3) = 1.0 + 1.892789 = 2.892789
    # IDCG = 3/log2(2) + 1/log2(3) = 3.0 + 0.630930 = 3.630930
    expected = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
    assert ndcg_at_k(["b", "a"], {"a": 3.0, "b": 1.0}, 2) == pytest.approx(expected)


def test_ndcg_graded_beats_binary_when_top_item_is_more_relevant():
    graded = {"a": 3.0, "b": 1.0}
    good = ndcg_at_k(["a", "b"], graded, 2)
    bad = ndcg_at_k(["b", "a"], graded, 2)
    assert good == pytest.approx(1.0)
    assert bad < good


# --------------------------------------------------------------- aggregation
def test_score_one_returns_empty_for_unlabelled_question():
    assert score_one(["a"], set()) == {}


def test_aggregate_skips_unlabelled_questions():
    rows = [{"recall@5": 1.0}, {}, {"recall@5": 0.0}]
    # mean over the two labelled rows only -> 0.5, not 1/3
    assert aggregate(rows)["recall@5"] == 0.5


def test_aggregate_empty():
    assert aggregate([{}, {}]) == {}


def test_score_one_all_metrics_run():
    scores = score_one(["a", "x", "b"], {"a", "b"})
    assert set(scores) == {
        "recall@1", "recall@5", "recall@10", "recall@20",
        "hit@5", "precision@5", "mrr", "map", "ndcg@10",
    }
    assert scores["recall@1"] == 0.5
    assert scores["mrr"] == 1.0
