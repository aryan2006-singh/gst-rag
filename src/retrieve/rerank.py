"""Cross-encoder reranking.

A bi-encoder embeds query and passage independently, so it can never model
interactions between them — it only ever compares two frozen summaries. A
cross-encoder concatenates query and passage and runs full attention across
both, which is far more accurate and far too slow to run over the whole corpus.

Hence the standard two-stage design: retrieve 30-50 candidates cheaply, rerank
them expensively. The reranker cannot fix a bad first stage — anything the
retriever missed is gone — so always report Recall@candidates alongside your
reranked metrics. If Recall@50 is 0.72, no reranker will ever get you past 0.72.

`StubReranker` makes the pipeline testable offline.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Reranker(Protocol):
    name: str

    def rerank(
        self, query: str, candidates: Sequence[tuple[str, str]]
    ) -> list[tuple[str, float]]:
        """`candidates` is [(doc_id, text)]. Returns [(doc_id, score)] best first."""
        ...


class CrossEncoderReranker:
    """Local cross-encoder on CPU. No API key.

    Model options, all CPU-viable:
      * cross-encoder/ms-marco-MiniLM-L-6-v2   fastest, English, solid baseline
      * cross-encoder/ms-marco-MiniLM-L-12-v2  ~2x slower, a couple points better
      * BAAI/bge-reranker-base                 stronger, ~4x slower on CPU

    Budget check before you commit: on a laptop CPU, MiniLM-L-6 reranks roughly
    30-80 passages/second. At depth 30 that is well under a second per query,
    which is fine for a demo and fine for a 250-question eval sweep.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "cpu",
        batch_size: int = 32,
        max_length: int = 512,
    ) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, device=device, max_length=max_length)
        self.name = model_name
        self.batch_size = batch_size

    def rerank(
        self, query: str, candidates: Sequence[tuple[str, str]]
    ) -> list[tuple[str, float]]:
        if not candidates:
            return []
        pairs = [(query, text) for _, text in candidates]
        scores = self.model.predict(pairs, batch_size=self.batch_size)
        ranked = [
            (doc_id, float(score)) for (doc_id, _), score in zip(candidates, scores)
        ]
        ranked.sort(key=lambda kv: (-kv[1], kv[0]))
        return ranked


class StubReranker:
    """Deterministic lexical-overlap reranker: no weights, no downloads.

    Scores by Jaccard overlap of token sets. Good enough to exercise the pipeline
    in tests and to serve as the "does a real reranker beat trivial overlap?"
    control in your ablation — a question worth actually answering.
    """

    name = "stub-jaccard"

    def rerank(
        self, query: str, candidates: Sequence[tuple[str, str]]
    ) -> list[tuple[str, float]]:
        from src.index.bm25 import tokenize

        query_tokens = set(tokenize(query))
        scored: list[tuple[str, float]] = []
        for doc_id, text in candidates:
            doc_tokens = set(tokenize(text))
            union = query_tokens | doc_tokens
            score = len(query_tokens & doc_tokens) / len(union) if union else 0.0
            scored.append((doc_id, score))
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return scored
