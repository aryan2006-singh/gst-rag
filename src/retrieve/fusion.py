"""Combining ranked lists from BM25 and dense retrieval.

Two options, and the choice is not arbitrary.

**Reciprocal Rank Fusion** ignores scores and uses only ranks:

    RRF(d) = sum over retrievers r of  weight_r / (k + rank_r(d))

Use this by default. BM25 scores are unbounded and corpus-dependent; cosine
similarities live in [-1, 1] and are squashed near the top. They are not
commensurable, so any weighted sum of the raw scores is comparing units that do
not exist. RRF sidesteps the problem entirely and is remarkably hard to beat.

**Normalised score fusion** is provided for the ablation, because "we tried it
and it was worse" is a result worth reporting. Min-max normalisation per query
is sensitive to a single outlier score, which is exactly its failure mode.

The constant k=60 comes from the original RRF paper and mostly controls how much
the head of each list dominates. It is worth a sweep on your gold set — treat it
as a hyperparameter, and report the sweep.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

Ranking = Sequence[tuple[str, float]]


def reciprocal_rank_fusion(
    rankings: Mapping[str, Ranking],
    k: int = 60,
    weights: Mapping[str, float] | None = None,
) -> list[tuple[str, float]]:
    """Fuse named ranked lists. Returns [(doc_id, fused_score)] best first.

    >>> a = [("x", 9.0), ("y", 4.0)]
    >>> b = [("y", 0.9), ("z", 0.8)]
    >>> fused = reciprocal_rank_fusion({"bm25": a, "dense": b}, k=0)
    >>> [doc for doc, _ in fused]        # y is in both lists, so it wins
    ['y', 'x', 'z']
    """
    weights = weights or {}
    scores: dict[str, float] = {}
    for name, ranking in rankings.items():
        weight = weights.get(name, 1.0)
        for rank, (doc_id, _score) in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def minmax_normalize(ranking: Ranking) -> list[tuple[str, float]]:
    if not ranking:
        return []
    values = [score for _, score in ranking]
    low, high = min(values), max(values)
    span = high - low
    if span <= 0:
        return [(doc_id, 1.0) for doc_id, _ in ranking]
    return [(doc_id, (score - low) / span) for doc_id, score in ranking]


def score_fusion(
    rankings: Mapping[str, Ranking],
    weights: Mapping[str, float] | None = None,
) -> list[tuple[str, float]]:
    """Weighted sum of per-query min-max normalised scores.

    Documents missing from a retriever's list score 0 for that retriever, which
    is an assumption worth being explicit about: it treats "not retrieved" as
    "worst possible", when it really means "unknown, below the cutoff".
    """
    weights = weights or {}
    scores: dict[str, float] = {}
    for name, ranking in rankings.items():
        weight = weights.get(name, 1.0)
        for doc_id, score in minmax_normalize(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight * score
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
