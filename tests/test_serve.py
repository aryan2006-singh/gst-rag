"""Unit tests for the pure helpers in src.serve.app.

The FastAPI layer itself isn't integration-tested here -- spinning up the app
loads a real index via its lifespan, which needs a built index on disk. These
tests cover the small pieces of logic that sit in the request handlers and are
cheap to check directly, without starting the app.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("fastapi")

from src.retrieve.pipeline import ABLATION_LADDER, PipelineConfig  # noqa: E402
from src.serve.app import empty_result_warning, variant_summary  # noqa: E402


def test_empty_result_warning_without_as_of():
    assert (
        empty_result_warning(None)
        == "no passages retrieved; the system should abstain"
    )


def test_empty_result_warning_with_as_of():
    assert (
        empty_result_warning(date(2018, 1, 1))
        == "no in-force provision found for 2018-01-01"
    )


def test_variant_summary_reports_config_flags():
    config = PipelineConfig(name="test-variant", rerank=True, query_rewrite=True)
    assert variant_summary(config) == {
        "name": "test-variant",
        "use_bm25": True,
        "use_dense": True,
        "rerank": True,
        "query_rewrite": True,
        "recency_boost": 0.0,
    }


def test_variant_summary_covers_every_ablation_row():
    names = {variant_summary(c)["name"] for c in ABLATION_LADDER}
    assert names == {c.name for c in ABLATION_LADDER}


def test_api_routes_are_registered_before_the_static_mount():
    # Guards against the frontend's StaticFiles mount at "/" ever being
    # registered ahead of the API routes, which would shadow /health,
    # /variants, and /query. No HTTP client or built index required -- just
    # inspects the route list FastAPI already built at import time.
    from starlette.routing import Mount

    from src.serve.app import app

    paths = [getattr(route, "path", None) for route in app.routes]
    mount_index = next(i for i, route in enumerate(app.routes) if isinstance(route, Mount))
    for api_path in ("/health", "/variants", "/query"):
        assert paths.index(api_path) < mount_index
