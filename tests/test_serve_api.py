"""HTTP-level tests for the FastAPI service, on the fixture corpus.

The app's lifespan loads a real on-disk index, so these tests skip it: the
TestClient is used without a `with` block (which is what runs the lifespan)
and STATE is filled in directly with a fixture pipeline. Offline, no downloads.
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from src.index.chunking import chunk_corpus  # noqa: E402
from src.index.embedders import HashingEmbedder  # noqa: E402
from src.retrieve.pipeline import ABLATION_LADDER, RetrievalPipeline  # noqa: E402
from src.retrieve.query_rewrite import rewrite  # noqa: E402
from src.retrieve.recency import build_supersession_graph  # noqa: E402
from src.retrieve.rerank import StubReranker  # noqa: E402
from src.serve import app as app_module  # noqa: E402
from tests.fixtures import DOCUMENTS  # noqa: E402


def make_state(reranker) -> dict:
    chunks = chunk_corpus(DOCUMENTS, "section")
    config = next(c for c in ABLATION_LADDER if c.name == "Hybrid + reranker")
    pipeline = RetrievalPipeline(
        chunks=chunks,
        embedder=HashingEmbedder(dim=256),
        config=config if reranker else ABLATION_LADDER[2],
        reranker=reranker,
        query_rewriter=rewrite,
    )
    return {
        "pipeline": pipeline,
        "graph": build_supersession_graph([(c.doc_id, c.text) for c in chunks]),
        "variants": {c.name: c for c in ABLATION_LADDER},
        "started": 0.0,
    }


@pytest.fixture
def client_with(monkeypatch):
    def build(state: dict) -> TestClient:
        monkeypatch.setattr(app_module, "STATE", state)
        return TestClient(app_module.app)

    return build


def test_query_handler_is_not_a_coroutine():
    # CPU-bound retrieval inside an `async def` would block the event loop.
    assert not inspect.iscoroutinefunction(app_module.query)


def test_query_returns_stage_scores_for_each_citation(client_with):
    client = client_with(make_state(StubReranker()))
    response = client.post("/query", json={"question": "input tax credit time limit"})
    assert response.status_code == 200
    body = response.json()
    assert body["citations"]
    for citation in body["citations"]:
        scores = citation["stage_scores"]
        assert "fusion" in scores
        assert "rerank" in scores
        assert {"bm25", "dense"} & scores.keys()
    assert body["trace"]["skipped_stages"] == []


def test_variant_needing_missing_reranker_is_reported(client_with):
    client = client_with(make_state(reranker=None))
    response = client.post(
        "/query",
        json={"question": "input tax credit time limit", "variant": "Hybrid + reranker"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trace"]["skipped_stages"] == ["rerank"]
    assert "rerank" not in body["trace"]["stage_latency_ms"]
    assert any("isn't loaded" in w for w in body["warnings"])
    for citation in body["citations"]:
        assert "rerank" not in citation["stage_scores"]


def test_health_reports_load_failure(client_with):
    client = client_with({"error": "FileNotFoundError: data/index", "started": 0.0})
    health = client.get("/health").json()
    assert health["status"] == "error"
    assert "FileNotFoundError" in health["error"]

    response = client.post("/query", json={"question": "input tax credit"})
    assert response.status_code == 503
    assert "failed to load" in response.json()["detail"]


def test_health_reports_loading_before_state_exists(client_with):
    client = client_with({})
    assert client.get("/health").json()["status"] == "loading"
    assert client.post("/query", json={"question": "input tax credit"}).status_code == 503


def test_lifespan_records_load_error_instead_of_crashing(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(app_module, "STATE", state)

    def boom() -> None:
        raise FileNotFoundError("data/index")

    monkeypatch.setattr(app_module, "load_state", boom)
    with TestClient(app_module.app) as client:
        assert client.get("/health").json()["status"] == "error"
    assert state["error"].startswith("FileNotFoundError")


def test_variants_mark_default_and_unavailable(client_with):
    client = client_with(make_state(reranker=None))
    rows = {v["name"]: v for v in client.get("/variants").json()}
    assert rows["Hybrid (RRF)"]["default"] is True
    assert sum(v["default"] for v in rows.values()) == 1
    assert rows["Hybrid + reranker"]["available"] is False
    assert rows["BM25 only"]["available"] is True


def test_default_variant_env_is_validated(monkeypatch):
    monkeypatch.setenv("DEFAULT_VARIANT", "no such variant")
    monkeypatch.setenv("RERANK", "0")
    monkeypatch.setattr(app_module, "STATE", {})
    import src.index.build as build

    monkeypatch.setattr(build, "load_index", lambda *a, **k: make_index())
    with pytest.raises(ValueError, match="DEFAULT_VARIANT"):
        app_module.load_state()


def test_default_variant_env_selects_the_pipeline(monkeypatch):
    monkeypatch.setenv("DEFAULT_VARIANT", "BM25 only")
    monkeypatch.setenv("RERANK", "0")
    state: dict = {}
    monkeypatch.setattr(app_module, "STATE", state)
    import src.index.build as build

    monkeypatch.setattr(build, "load_index", lambda *a, **k: make_index())
    app_module.load_state()
    assert state["pipeline"].config.name == "BM25 only"


def make_index():
    chunks = chunk_corpus(DOCUMENTS, "section")
    embedder = HashingEmbedder(dim=256)
    return chunks, embedder.encode([c.text for c in chunks]), embedder
