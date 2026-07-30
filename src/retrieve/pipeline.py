"""Composable retrieval pipelines — the surface the ablation sweeps over.

Design constraint: every variant in the results table must be the *same code*
with different flags. If "hybrid + reranker" is a separate script from "dense
only", the two rows are not comparable and the ablation proves nothing.

So there is one `RetrievalPipeline` with switchable stages, and each row of
BENCHMARKS is a `PipelineConfig`.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date

import numpy as np

from src.index.bm25 import BM25, tokenize
from src.index.chunking import Chunk
from src.index.embedders import Embedder
from src.retrieve.fusion import reciprocal_rank_fusion, score_fusion


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    use_bm25: bool = True
    use_dense: bool = True
    fusion: str = "rrf"  # "rrf" | "score"
    rrf_k: int = 60
    bm25_weight: float = 1.0
    dense_weight: float = 1.0
    candidates: int = 50  # depth pulled from each retriever before fusion
    rerank: bool = False
    rerank_depth: int = 30
    query_rewrite: bool = False
    recency_boost: float = 0.0  # domain-specific; see recency.py
    top_k: int = 10

    def __post_init__(self) -> None:
        if not (self.use_bm25 or self.use_dense):
            raise ValueError("pipeline must use at least one retriever")
        if self.fusion not in ("rrf", "score"):
            raise ValueError(f"unknown fusion {self.fusion!r}")
        if self.rerank_depth < self.top_k:
            raise ValueError("rerank_depth must be >= top_k or reranking cannot help")


@dataclass
class RetrievedChunk:
    chunk_id: str
    score: float
    chunk: Chunk
    stage_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    query: str
    rewritten_query: str
    hits: list[RetrievedChunk]
    latency_ms: dict[str, float]

    @property
    def ranked_ids(self) -> list[str]:
        return [hit.chunk_id for hit in self.hits]

    @property
    def total_ms(self) -> float:
        return sum(self.latency_ms.values())


class RetrievalPipeline:
    def __init__(
        self,
        chunks: Sequence[Chunk],
        embedder: Embedder,
        config: PipelineConfig,
        reranker=None,
        query_rewriter=None,
        embeddings: np.ndarray | None = None,
    ) -> None:
        self.chunks = list(chunks)
        self.by_id = {c.chunk_id: c for c in self.chunks}
        self.config = config
        self.embedder = embedder
        self.reranker = reranker
        self.query_rewriter = query_rewriter

        self.bm25 = BM25(
            corpus=[tokenize(c.text) for c in self.chunks],
            ids=[c.chunk_id for c in self.chunks],
        )
        if embeddings is not None:
            if embeddings.shape[0] != len(self.chunks):
                raise ValueError("embeddings row count must match chunk count")
            self.embeddings = embeddings
        else:
            self.embeddings = embedder.encode([c.text for c in self.chunks], is_query=False)
        self.chunk_ids = [c.chunk_id for c in self.chunks]

    # ------------------------------------------------------------------ stages
    def _dense_search(self, query: str, k: int) -> list[tuple[str, float]]:
        vector = self.embedder.encode([query], is_query=True)[0]
        # Embeddings are L2-normalised, so a dot product is cosine similarity.
        scores = self.embeddings @ vector
        if k >= len(scores):
            order = np.argsort(-scores)
        else:
            # argpartition is O(n); sorting the whole corpus per query is not
            # something you want at 40k chunks x 250 gold questions x 6 variants.
            top = np.argpartition(-scores, k)[:k]
            order = top[np.argsort(-scores[top])]
        return [(self.chunk_ids[i], float(scores[i])) for i in order[:k]]

    def _bm25_search(self, query: str, k: int) -> list[tuple[str, float]]:
        return self.bm25.search(query, k=k)

    # -------------------------------------------------------------------- main
    def search(
        self, query: str, top_k: int | None = None, as_of: date | None = None
    ) -> RetrievalResult:
        config = self.config
        k = top_k or config.top_k
        latency: dict[str, float] = {}

        effective_query = query
        if config.query_rewrite and self.query_rewriter is not None:
            start = time.perf_counter()
            effective_query = self.query_rewriter(query)
            latency["rewrite"] = (time.perf_counter() - start) * 1000

        rankings: dict[str, list[tuple[str, float]]] = {}
        if config.use_bm25:
            start = time.perf_counter()
            rankings["bm25"] = self._bm25_search(effective_query, config.candidates)
            latency["bm25"] = (time.perf_counter() - start) * 1000
        if config.use_dense:
            start = time.perf_counter()
            rankings["dense"] = self._dense_search(effective_query, config.candidates)
            latency["dense"] = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        if len(rankings) == 1:
            fused = list(next(iter(rankings.values())))
        elif config.fusion == "rrf":
            fused = reciprocal_rank_fusion(
                rankings,
                k=config.rrf_k,
                weights={"bm25": config.bm25_weight, "dense": config.dense_weight},
            )
        else:
            fused = score_fusion(
                rankings,
                weights={"bm25": config.bm25_weight, "dense": config.dense_weight},
            )
        latency["fusion"] = (time.perf_counter() - start) * 1000

        if config.recency_boost:
            from src.retrieve.recency import apply_recency_boost

            start = time.perf_counter()
            fused = apply_recency_boost(fused, self.by_id, weight=config.recency_boost)
            latency["recency"] = (time.perf_counter() - start) * 1000

        if as_of is not None:
            from src.retrieve.recency import filter_as_of

            start = time.perf_counter()
            fused = filter_as_of(fused, self.by_id, as_of)
            latency["as_of_filter"] = (time.perf_counter() - start) * 1000

        if config.rerank and self.reranker is not None:
            start = time.perf_counter()
            head = fused[: config.rerank_depth]
            tail = fused[config.rerank_depth :]
            reranked = self.reranker.rerank(
                effective_query, [(doc_id, self.by_id[doc_id].text) for doc_id, _ in head]
            )
            # Keep the un-reranked tail below the reranked head so recall@large-k
            # is never *worse* than the fusion baseline.
            fused = reranked + tail
            latency["rerank"] = (time.perf_counter() - start) * 1000

        hits = [
            RetrievedChunk(chunk_id=doc_id, score=score, chunk=self.by_id[doc_id])
            for doc_id, score in fused[:k]
        ]
        return RetrievalResult(
            query=query,
            rewritten_query=effective_query,
            hits=hits,
            latency_ms=latency,
        )

    def with_config(self, config: PipelineConfig) -> RetrievalPipeline:
        """Reuse the built index and embeddings for a different variant.

        Rebuilding the index per ablation row would make the sweep unbearably
        slow and, worse, would let index nondeterminism leak into the comparison.
        """
        clone = object.__new__(RetrievalPipeline)
        clone.chunks = self.chunks
        clone.by_id = self.by_id
        clone.embedder = self.embedder
        clone.reranker = self.reranker
        clone.query_rewriter = self.query_rewriter
        clone.bm25 = self.bm25
        clone.embeddings = self.embeddings
        clone.chunk_ids = self.chunk_ids
        clone.config = config
        return clone


# --------------------------------------------------------------------------- #
#  The ablation ladder. Each row isolates one change from the row above it.
# --------------------------------------------------------------------------- #

BASE = PipelineConfig(name="base", candidates=50, top_k=10)

ABLATION_LADDER: list[PipelineConfig] = [
    replace(BASE, name="BM25 only", use_dense=False),
    replace(BASE, name="Dense only", use_bm25=False),
    replace(BASE, name="Hybrid (RRF)"),
    replace(BASE, name="Hybrid (score fusion)", fusion="score"),
    replace(BASE, name="Hybrid + reranker", rerank=True),
    replace(BASE, name="Hybrid + reranker + rewrite", rerank=True, query_rewrite=True),
    replace(
        BASE,
        name="Hybrid + reranker + recency",
        rerank=True,
        recency_boost=0.15,
    ),
]
