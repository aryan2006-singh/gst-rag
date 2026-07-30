"""Retrieval metrics.

Every number your project reports comes through this file, so it is the one
place where a bug is unrecoverable — a wrong nDCG makes every row of your
ablation table a lie, and the table is the entire deliverable.

Consequently: no library, no vectorisation tricks, explicit formulas, and a test
for each metric against a value computed by hand in the docstring.

Conventions
-----------
`ranked` is a list of chunk ids, best first, no duplicates.
`relevant` is either
    * a set of chunk ids (binary relevance), or
    * a dict {chunk_id: gain} for graded relevance (nDCG only).

A question with no relevant chunks in the gold set is *skipped*, not scored 0 —
scoring it 0 silently punishes pipelines for a gold-set gap.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence


def _dedupe(ranked: Sequence[str]) -> list[str]:
    """Keep first occurrence. A pipeline returning duplicates would otherwise
    inflate recall for free."""
    seen: set[str] = set()
    out: list[str] = []
    for item in ranked:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def recall_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of relevant chunks that appear in the top k.

    >>> recall_at_k(["a", "b", "c"], {"a", "d"}, 3)   # found 1 of 2
    0.5
    """
    relevant = set(relevant)
    if not relevant:
        raise ValueError("no relevant items; caller should skip this question")
    top = _dedupe(ranked)[:k]
    return len(relevant & set(top)) / len(relevant)


def precision_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant = set(relevant)
    if k <= 0:
        raise ValueError("k must be positive")
    top = _dedupe(ranked)[:k]
    if not top:
        return 0.0
    return len(relevant & set(top)) / min(k, len(top))


def hit_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """1.0 if any relevant chunk is in the top k. Blunt, but it is what a user
    of a citation UI actually experiences."""
    return 1.0 if set(_dedupe(ranked)[:k]) & set(relevant) else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    """1 / rank of the first relevant chunk, 0 if none.

    >>> reciprocal_rank(["x", "y", "a"], {"a"})
    0.3333333333333333
    """
    relevant = set(relevant)
    for index, item in enumerate(_dedupe(ranked), start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def average_precision(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    """Mean of precision@i over the positions i where a relevant chunk appears.

    Divided by the total number of relevant chunks (not the number retrieved),
    so failing to retrieve a relevant chunk is penalised.

    >>> # relevant {a, b}; ranked [a, x, b]  -> (1/1 + 2/3) / 2
    >>> round(average_precision(["a", "x", "b"], {"a", "b"}), 6)
    0.833333
    """
    relevant = set(relevant)
    if not relevant:
        raise ValueError("no relevant items; caller should skip this question")
    hits = 0
    total = 0.0
    for index, item in enumerate(_dedupe(ranked), start=1):
        if item in relevant:
            hits += 1
            total += hits / index
    return total / len(relevant)


def dcg(gains: Sequence[float]) -> float:
    """Discounted cumulative gain with the standard log2(i+1) discount."""
    return sum(gain / math.log2(index + 1) for index, gain in enumerate(gains, start=1))


def ndcg_at_k(
    ranked: Sequence[str],
    relevant: Iterable[str] | Mapping[str, float],
    k: int,
) -> float:
    """Normalised DCG.

    Graded relevance is supported by passing a mapping of id -> gain. For binary
    relevance every gain is 1.

    The ideal ranking is computed over *all* known relevant chunks truncated to
    k — not over the chunks the pipeline happened to return. Normalising against
    the retrieved set is a common bug that makes a pipeline that misses
    everything look perfect.

    >>> # relevant {a: 1, b: 1}; ranked [x, a, b]
    >>> # DCG  = 1/log2(3) + 1/log2(4) = 0.63093 + 0.5 = 1.13093
    >>> # IDCG = 1/log2(2) + 1/log2(3) = 1.0     + 0.63093 = 1.63093
    >>> round(ndcg_at_k(["x", "a", "b"], {"a", "b"}, 3), 5)
    0.69343
    """
    if isinstance(relevant, Mapping):
        gains_by_id = dict(relevant)
    else:
        gains_by_id = {item: 1.0 for item in relevant}
    if not gains_by_id:
        raise ValueError("no relevant items; caller should skip this question")

    top = _dedupe(ranked)[:k]
    actual = dcg([gains_by_id.get(item, 0.0) for item in top])
    ideal = dcg(sorted(gains_by_id.values(), reverse=True)[:k])
    return actual / ideal if ideal > 0 else 0.0


# --------------------------------------------------------------------------- #
#  Aggregation
# --------------------------------------------------------------------------- #

METRIC_SPECS: dict[str, tuple[str, int | None]] = {
    "recall@1": ("recall", 1),
    "recall@5": ("recall", 5),
    "recall@10": ("recall", 10),
    "recall@20": ("recall", 20),
    "hit@5": ("hit", 5),
    "precision@5": ("precision", 5),
    "mrr": ("mrr", None),
    "map": ("map", None),
    "ndcg@10": ("ndcg", 10),
}


def score_one(
    ranked: Sequence[str],
    relevant: Iterable[str] | Mapping[str, float],
    metrics: Iterable[str] = tuple(METRIC_SPECS),
) -> dict[str, float]:
    """Per-question scores. Returns {} if the question has no gold labels."""
    keys = set(relevant.keys()) if isinstance(relevant, Mapping) else set(relevant)
    if not keys:
        return {}

    out: dict[str, float] = {}
    for name in metrics:
        kind, k = METRIC_SPECS[name]
        if kind == "recall":
            out[name] = recall_at_k(ranked, keys, k)
        elif kind == "precision":
            out[name] = precision_at_k(ranked, keys, k)
        elif kind == "hit":
            out[name] = hit_at_k(ranked, keys, k)
        elif kind == "mrr":
            out[name] = reciprocal_rank(ranked, keys)
        elif kind == "map":
            out[name] = average_precision(ranked, keys)
        elif kind == "ndcg":
            out[name] = ndcg_at_k(ranked, relevant, k)
        else:  # pragma: no cover
            raise ValueError(f"unknown metric kind: {kind}")
    return out


def aggregate(per_question: Sequence[Mapping[str, float]]) -> dict[str, float]:
    """Macro-average across questions. Empty dicts (unlabelled) are dropped."""
    scored = [row for row in per_question if row]
    if not scored:
        return {}
    names = scored[0].keys()
    return {name: sum(row[name] for row in scored) / len(scored) for name in names}
