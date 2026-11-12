"""FastAPI service with traced retrieval and paragraph-level citations.

Two things here are worth more than the UI:

  * **Every response carries its trace** — per-stage latency, the rewritten
    query, and the score each candidate got at each stage. You will spend most
    of your debugging time asking "why did it retrieve *that*", and a response
    that answers the question is worth more than a prettier front end.

  * **Every citation carries a legal status** — in_force / amended / superseded,
    from the supersession graph. Showing a user a superseded rate without
    flagging it is the failure mode that makes a legal RAG system dangerous
    rather than merely unhelpful.

    uvicorn src.serve.app:app --reload
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.retrieve.pipeline import ABLATION_LADDER, PipelineConfig

STATE: dict = {}


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=50)
    as_of: str | None = None
    variant: str | None = None


class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    score: float
    status: str
    snippet: str
    section: str | None = None
    published: str | None = None
    # Score this chunk got at each stage it appeared in (bm25, dense, fusion,
    # recency, rerank). A stage is missing when the chunk wasn't in that
    # stage's candidate list.
    stage_scores: dict[str, float] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    question: str
    rewritten_query: str
    answer: str | None
    citations: list[Citation]
    trace: dict
    warnings: list[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A failed index load should be visible on /health, not hidden behind a
    # status that says "loading" forever or a container that crash-loops
    # without telling anyone why.
    try:
        load_state()
    except Exception as exc:  # noqa: BLE001 - surfaced via /health and /query
        STATE["error"] = f"{type(exc).__name__}: {exc}"
        STATE["started"] = time.time()
        print(f"index load failed: {STATE['error']}")
    yield


def load_state() -> None:
    from src.index.build import load_index
    from src.retrieve.pipeline import RetrievalPipeline
    from src.retrieve.query_rewrite import rewrite
    from src.retrieve.recency import build_supersession_graph

    index_dir = os.environ.get("INDEX_DIR", "data/index")
    embedder_kind = os.environ.get("EMBEDDER", "sentence-transformers")

    chunks, embeddings, embedder = load_index(index_dir, embedder_kind=embedder_kind)

    reranker = None
    if os.environ.get("RERANK", "1") == "1":
        from src.retrieve.rerank import CrossEncoderReranker

        reranker = CrossEncoderReranker()

    best = next(c for c in ABLATION_LADDER if c.name == "Hybrid + reranker")
    STATE["pipeline"] = RetrievalPipeline(
        chunks=chunks,
        embedder=embedder,
        config=best if reranker else ABLATION_LADDER[2],
        reranker=reranker,
        query_rewriter=rewrite,
        embeddings=embeddings,
    )
    STATE["graph"] = build_supersession_graph(
        [(c.doc_id, c.text) for c in chunks]
    )
    STATE["variants"] = {c.name: c for c in ABLATION_LADDER}
    STATE["started"] = time.time()


app = FastAPI(title="gst-rag", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    pipeline = STATE.get("pipeline")
    if STATE.get("error"):
        return {
            "status": "error",
            "error": STATE["error"],
            "n_chunks": 0,
            "uptime_s": round(time.time() - STATE.get("started", time.time()), 1),
        }
    return {
        "status": "ok" if pipeline else "loading",
        "n_chunks": len(pipeline.chunks) if pipeline else 0,
        "uptime_s": round(time.time() - STATE.get("started", time.time()), 1),
    }


def variant_summary(config: PipelineConfig) -> dict:
    return {
        "name": config.name,
        "use_bm25": config.use_bm25,
        "use_dense": config.use_dense,
        "rerank": config.rerank,
        "query_rewrite": config.query_rewrite,
        "recency_boost": config.recency_boost,
    }


@app.get("/variants")
async def variants():
    return [variant_summary(c) for c in ABLATION_LADDER]


# NOTE: the exact wording of the warning strings below (here and in the
# supersession/amendment branch in `query()`) is a UI contract with
# frontend/src/components/WarningsBanner.tsx, which substring-matches these
# messages to decide red (severe) vs amber styling. Changing the wording
# without updating that component's substring checks will silently change a
# warning's rendered severity.
def empty_result_warning(as_of: date | None) -> str:
    if as_of is not None:
        return f"no in-force provision found for {as_of.isoformat()}"
    return "no passages retrieved; the system should abstain"


def skipped_stage_warning(config_name: str, skipped: list[str]) -> str:
    return (
        f"variant '{config_name}' asked for {', '.join(skipped)} but it isn't "
        "loaded on this server; results come from the stages that did run"
    )


# Deliberately a plain `def`: retrieval and reranking are CPU-bound, and an
# `async def` handler would run them on the event loop and stall every other
# request (including /health) until the search finished. FastAPI runs plain
# handlers in a worker thread.
@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    if STATE.get("error"):
        raise HTTPException(503, f"index failed to load: {STATE['error']}")
    pipeline = STATE.get("pipeline")
    if pipeline is None:
        raise HTTPException(503, "index still loading")

    if request.variant:
        config = STATE["variants"].get(request.variant)
        if config is None:
            raise HTTPException(400, f"unknown variant; have {sorted(STATE['variants'])}")
        pipeline = pipeline.with_config(config)

    as_of_date: date | None = None
    if request.as_of:
        try:
            as_of_date = date.fromisoformat(request.as_of)
        except ValueError:
            raise HTTPException(
                400, f"invalid as_of date: {request.as_of!r}; expected YYYY-MM-DD"
            )

    started = time.perf_counter()
    result = pipeline.search(request.question, top_k=request.top_k, as_of=as_of_date)
    graph = STATE["graph"]

    warnings: list[str] = []
    citations: list[Citation] = []
    for hit in result.hits:
        metadata = hit.chunk.metadata or {}
        notification_id = metadata.get("notification_id")
        status = graph.status(notification_id) if notification_id else "unknown"
        # Wording here is also a WarningsBanner.tsx substring-matching contract
        # (see the note above empty_result_warning) — keep "superseded" and
        # "amended" in these messages if you edit them.
        if status == "superseded":
            warnings.append(
                f"{notification_id} has been superseded; check the successor before relying on it"
            )
        elif status == "amended":
            warnings.append(f"{notification_id} has been amended since publication")
        citations.append(
            Citation(
                chunk_id=hit.chunk_id,
                doc_id=hit.chunk.doc_id,
                score=round(hit.score, 5),
                status=status,
                snippet=hit.chunk.text[:400],
                section=metadata.get("section"),
                published=metadata.get("published"),
                stage_scores={k: round(v, 5) for k, v in hit.stage_scores.items()},
            )
        )

    if not result.hits:
        warnings.append(empty_result_warning(as_of_date))

    if result.skipped_stages:
        warnings.append(skipped_stage_warning(pipeline.config.name, result.skipped_stages))

    if as_of_date is not None:
        undated = sum(1 for c in citations if c.published is None)
        if undated:
            warnings.append(
                f"{undated} result(s) have no publication date and were not filtered by as-of"
            )

    return QueryResponse(
        question=request.question,
        rewritten_query=result.rewritten_query,
        # Generation is intentionally not wired by default: an ungrounded
        # generated answer over legal text is a liability, and the retrieval
        # quality is what this project is actually measuring.
        answer=None,
        citations=citations,
        trace={
            "stage_latency_ms": {k: round(v, 2) for k, v in result.latency_ms.items()},
            "total_ms": round((time.perf_counter() - started) * 1000, 2),
            "config": pipeline.config.name,
            "skipped_stages": result.skipped_stages,
        },
        warnings=sorted(set(warnings)),
    )


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    print(
        f"frontend/dist not found at {FRONTEND_DIST} — API only; "
        "run 'make frontend' or 'cd frontend && npm install && npm run build'"
    )
