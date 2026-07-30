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

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

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


class QueryResponse(BaseModel):
    question: str
    rewritten_query: str
    answer: str | None
    citations: list[Citation]
    trace: dict
    warnings: list[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.index.build import load_index
    from src.retrieve.pipeline import ABLATION_LADDER, RetrievalPipeline
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
    yield


app = FastAPI(title="gst-rag", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    pipeline = STATE.get("pipeline")
    return {
        "status": "ok" if pipeline else "loading",
        "n_chunks": len(pipeline.chunks) if pipeline else 0,
        "uptime_s": round(time.time() - STATE.get("started", time.time()), 1),
    }


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    pipeline = STATE.get("pipeline")
    if pipeline is None:
        raise HTTPException(503, "index still loading")

    if request.variant:
        config = STATE["variants"].get(request.variant)
        if config is None:
            raise HTTPException(400, f"unknown variant; have {sorted(STATE['variants'])}")
        pipeline = pipeline.with_config(config)

    started = time.perf_counter()
    result = pipeline.search(request.question, top_k=request.top_k)
    graph = STATE["graph"]

    warnings: list[str] = []
    citations: list[Citation] = []
    for hit in result.hits:
        metadata = hit.chunk.metadata or {}
        notification_id = metadata.get("notification_id")
        status = graph.status(notification_id) if notification_id else "unknown"
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
            )
        )

    if not result.hits:
        warnings.append("no passages retrieved; the system should abstain")

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
        },
        warnings=sorted(set(warnings)),
    )


@app.get("/", response_class=HTMLResponse)
async def index_page():
    return """<!doctype html>
<html><head><meta charset="utf-8"><title>gst-rag</title>
<style>
 body{font:15px/1.55 system-ui,sans-serif;max-width:820px;margin:40px auto;padding:0 16px}
 input,button{font:inherit;padding:8px}
 input{width:74%} button{width:22%}
 .hit{border-left:3px solid #ccc;padding:8px 12px;margin:12px 0;background:#fafafa}
 .superseded{border-color:#c00} .amended{border-color:#e90}
 .badge{font-size:12px;padding:2px 6px;border-radius:3px;background:#eee}
 .trace{color:#666;font-size:13px;font-family:ui-monospace,monospace}
 .warn{background:#fff4e5;border-left:3px solid #e90;padding:8px 12px;margin:8px 0}
</style></head><body>
<h1>GST retrieval</h1>
<p>Retrieval only — citations with legal status, no generated answer.</p>
<div><input id="q" placeholder="Can I claim ITC on hotel accommodation?"
 onkeydown="if(event.key==='Enter')go()"><button onclick="go()">Search</button></div>
<div id="out"></div>
<script>
async function go(){
  const q=document.getElementById('q').value; if(!q)return;
  const out=document.getElementById('out'); out.innerHTML='searching...';
  const r=await fetch('/query',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({question:q,top_k:5})});
  const d=await r.json();
  let html=`<p class=trace>rewritten: ${d.rewritten_query}<br>`+
    `${JSON.stringify(d.trace.stage_latency_ms)} total ${d.trace.total_ms}ms `+
    `(${d.trace.config})</p>`;
  for(const w of d.warnings) html+=`<div class=warn>${w}</div>`;
  for(const c of d.citations){
    html+=`<div class="hit ${c.status}"><span class=badge>${c.status}</span> `+
      `<b>${c.doc_id}</b>${c.section?' section '+c.section:''} `+
      `<span class=trace>score ${c.score}${c.published?' · '+c.published:''}</span>`+
      `<p>${c.snippet}</p></div>`;
  }
  out.innerHTML=html;
}
</script></body></html>"""
