"""Supersession-aware scoring — the part of this project that is specific to law.

Generic RAG treats every chunk as equally true. In GST that is actively
dangerous: Notification 13/2017-CT(R) has been amended repeatedly, and a
confidently-cited superseded rate is a wrong answer that *looks* well-grounded.
Retrieval quality and legal correctness come apart here, and handling that gap is
the most defensible thing in this project.

Three mechanisms, in increasing order of usefulness:

1. **Recency prior** — mild boost for newer documents. Cheap, crude, and wrong
   whenever the user is asking about a historical period.
2. **Supersession graph** — an explicit "X is amended/superseded by Y" edge set
   parsed from the documents themselves ("in supersession of Notification No.
   ..."). A superseded chunk gets demoted *and* carries a warning to the UI.
3. **As-of filtering** — the honest version. The user asks "what was the rate in
   FY 2019-20", and retrieval restricts to documents in force on that date.

Report these separately in your ablation. A recency prior that improves Recall@5
on a gold set written from today's perspective may simply be exploiting the fact
that your questions are all current — say so rather than claiming a general win.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

SUPERSESSION_RE = re.compile(
    r"in\s+supersession\s+of\s+(?:the\s+)?notification\s+(?:no\.?\s*)?"
    r"([\d]+/[\d]{4}\s*-?\s*[A-Za-z()\.]*)",
    re.IGNORECASE,
)
AMENDMENT_RE = re.compile(
    r"(?:seeks?\s+to\s+amend|amendment\s+to|further\s+amend)\s+"
    r"(?:the\s+)?notification\s+(?:no\.?\s*)?([\d]+/[\d]{4}\s*-?\s*[A-Za-z()\.]*)",
    re.IGNORECASE,
)


def normalize_notification_id(raw: str) -> str:
    """'13/2017 - CT (R)' and '13/2017-CT(R)' must be the same node."""
    cleaned = re.sub(r"\s+", "", raw).upper().rstrip(".")
    return cleaned


@dataclass
class SupersessionGraph:
    """Directed edges: superseded_id -> [superseding_ids]."""

    superseded_by: dict[str, list[str]] = field(default_factory=dict)
    amended_by: dict[str, list[str]] = field(default_factory=dict)

    def add_from_text(self, doc_id: str, text: str) -> None:
        for match in SUPERSESSION_RE.finditer(text):
            target = normalize_notification_id(match.group(1))
            self.superseded_by.setdefault(target, []).append(doc_id)
        for match in AMENDMENT_RE.finditer(text):
            target = normalize_notification_id(match.group(1))
            self.amended_by.setdefault(target, []).append(doc_id)

    def is_superseded(self, notification_id: str) -> bool:
        return normalize_notification_id(notification_id) in self.superseded_by

    def is_amended(self, notification_id: str) -> bool:
        return normalize_notification_id(notification_id) in self.amended_by

    def status(self, notification_id: str) -> str:
        key = normalize_notification_id(notification_id)
        if key in self.superseded_by:
            return "superseded"
        if key in self.amended_by:
            return "amended"
        return "in_force"

    def successors(self, notification_id: str) -> list[str]:
        key = normalize_notification_id(notification_id)
        return self.superseded_by.get(key, []) + self.amended_by.get(key, [])

    def __len__(self) -> int:
        return len(self.superseded_by) + len(self.amended_by)


def build_supersession_graph(documents: Sequence[tuple[str, str]]) -> SupersessionGraph:
    """`documents` is [(doc_id, text)]."""
    graph = SupersessionGraph()
    for doc_id, text in documents:
        graph.add_from_text(doc_id, text)
    return graph


def years_old(chunk_metadata: Mapping, today: date | None = None) -> float | None:
    published = chunk_metadata.get("published")
    if not published:
        return None
    if isinstance(published, str):
        try:
            published = date.fromisoformat(published[:10])
        except ValueError:
            return None
    reference = today or date.today()
    return max((reference - published).days / 365.25, 0.0)


def apply_recency_boost(
    ranked: Sequence[tuple[str, float]],
    chunks_by_id: Mapping[str, object],
    weight: float = 0.15,
    half_life_years: float = 4.0,
    today: date | None = None,
) -> list[tuple[str, float]]:
    """Multiplicative boost decaying with document age.

    Applied to *fused* scores, which are rank-derived and therefore already on a
    comparable scale — applying it to raw BM25 scores would let one long document
    dominate. Documents with no date are left untouched rather than penalised;
    missing metadata is not evidence of age.
    """
    if weight <= 0:
        return list(ranked)

    boosted: list[tuple[str, float]] = []
    for doc_id, score in ranked:
        chunk = chunks_by_id.get(doc_id)
        metadata = getattr(chunk, "metadata", {}) or {}
        age = years_old(metadata, today=today)
        if age is None:
            boosted.append((doc_id, score))
            continue
        freshness = 0.5 ** (age / half_life_years)  # 1.0 today, 0.5 at half-life
        boosted.append((doc_id, score * (1.0 + weight * freshness)))
    boosted.sort(key=lambda kv: (-kv[1], kv[0]))
    return boosted


def filter_as_of(
    ranked: Sequence[tuple[str, float]],
    chunks_by_id: Mapping[str, object],
    as_of: date,
) -> list[tuple[str, float]]:
    """Drop chunks published after `as_of`.

    This is what makes "what was the rate in FY 2019-20" answerable instead of
    confidently wrong. Note it can empty the result set — that is the correct
    behaviour, and the UI should say "no in-force provision found for that date"
    rather than falling back to current law.
    """
    kept: list[tuple[str, float]] = []
    for doc_id, score in ranked:
        chunk = chunks_by_id.get(doc_id)
        metadata = getattr(chunk, "metadata", {}) or {}
        published = metadata.get("published")
        if not published:
            kept.append((doc_id, score))
            continue
        if isinstance(published, str):
            try:
                published = date.fromisoformat(published[:10])
            except ValueError:
                kept.append((doc_id, score))
                continue
        if published <= as_of:
            kept.append((doc_id, score))
    return kept


def annotate_status(
    hits: Sequence, graph: SupersessionGraph
) -> list[tuple[object, str]]:
    """Attach an in_force / amended / superseded label to each hit for the UI.

    Showing this next to a citation is the difference between a demo and
    something a practitioner would risk using.
    """
    out = []
    for hit in hits:
        chunk = getattr(hit, "chunk", hit)
        metadata = getattr(chunk, "metadata", {}) or {}
        notification_id = metadata.get("notification_id")
        status = graph.status(notification_id) if notification_id else "unknown"
        out.append((hit, status))
    return out
