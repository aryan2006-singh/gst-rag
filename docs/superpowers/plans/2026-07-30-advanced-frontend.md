# gst-rag Advanced Frontend + Real Corpus Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline HTML page in `src/serve/app.py` with a React frontend that surfaces legal status, the pipeline variant selector, the retrieval trace, and as-of date filtering, then run the whole thing against a real scraped CBIC corpus.

**Architecture:** Two backend gaps get closed first (`as_of` filtering was a dead parameter; there's no way to list variants), each with its own unit tests. Then a Vite/React/TypeScript/Tailwind SPA is scaffolded and built out against the FastAPI API, initially served via Vite's dev proxy, finally built and served as static files by FastAPI itself on the same port as the API. Last, the real CBIC corpus is scraped, extracted, and indexed, and the whole stack is verified end to end in a browser.

**Tech Stack:** Python 3 / FastAPI / Pydantic (existing backend, unchanged shape), React 18 + TypeScript + Vite + Tailwind CSS (new frontend), pytest (existing test suite).

## Global Constraints

- No LLM-generated answers. `QueryResponse.answer` stays `null` — this project measures retrieval, not generation. (spec: Non-goals)
- Single process, single port (8000): FastAPI serves both the JSON API and the built frontend static files. No separate frontend server in production. (spec: Frontend)
- Frontend stack is React 18 + TypeScript + Vite + Tailwind CSS. No additional state management library, no client-side routing — this is one screen. (spec: Frontend / Tech notes)
- No new frontend test framework. Frontend correctness is verified by running it, not by an automated suite. (spec: Testing)
- Any new backend test that imports `fastapi`/`pydantic` must guard with `pytest.importorskip("fastapi")` so the README's `pip install numpy pytest && make test` quickstart keeps working without those packages installed.
- The scraper (`src/ingest/cbic_scraper.py`) enforces a 1 request / 2s delay, single-threaded, and refuses to run unless `check_robots()` returns `True`. Do not bypass this.
- Embedding/reranker models are unchanged from the existing project defaults: `BAAI/bge-small-en-v1.5` (embeddings), `cross-encoder/ms-marco-MiniLM-L-6-v2` (reranker), both CPU, no API keys.

---

## Task 1: Wire `as_of` filtering into `RetrievalPipeline.search`

**Files:**
- Modify: `src/retrieve/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `RetrievalPipeline.search(self, query: str, top_k: int | None = None, as_of: date | None = None) -> RetrievalResult`. New keyword-only-by-convention `as_of` param, default `None` (no filtering, fully backward compatible). When filtering removes every candidate, `RetrievalResult.hits == []`. When applied, `RetrievalResult.latency_ms` gains an `"as_of_filter"` key.
- Consumes: `filter_as_of(ranked: Sequence[tuple[str, float]], chunks_by_id: Mapping[str, object], as_of: date) -> list[tuple[str, float]]` from `src/retrieve/recency.py` (already exists, already tested by `test_as_of_filter_drops_future_documents` in `tests/test_pipeline.py`).

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/test_pipeline.py` (after `test_gold_set_chunk_ids_exist_in_the_index`, so it can use the module-scoped `pipeline` fixture already defined earlier in the file):

```python
def test_pipeline_search_as_of_excludes_documents_published_after(pipeline):
    from datetime import date

    result = pipeline.search(
        "GST rate on hotel accommodation above 7500 rupees",
        top_k=10,
        as_of=date(2018, 1, 1),
    )
    assert "notif-20-2019::fixed::0" not in result.ranked_ids
    assert "as_of_filter" in result.latency_ms


def test_pipeline_search_as_of_can_return_no_hits(pipeline):
    from datetime import date

    result = pipeline.search(
        "GST rate on hotel accommodation above 7500 rupees",
        top_k=10,
        as_of=date(2000, 1, 1),
    )
    assert result.hits == []
```

This relies on the fixture corpus in `tests/fixtures.py`: `notif-20-2019::fixed::0` is published `2019-09-30`, `notif-11-2017::fixed::0` is published `2017-06-28`, and every fixture document has a `published` date no earlier than `2017-06-28` — so `as_of=date(2000, 1, 1)` excludes the entire corpus.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "C:\Users\rsing\gst-rag" && python -m pytest tests/test_pipeline.py -v -k as_of`

Expected: the two new tests FAIL with `TypeError: search() got an unexpected keyword argument 'as_of'`. The pre-existing `test_as_of_filter_drops_future_documents` still passes (it doesn't touch `search`).

- [ ] **Step 3: Implement `as_of` filtering in the pipeline**

In `src/retrieve/pipeline.py`, add the import (after the existing `from dataclasses import dataclass, field, replace` line):

```python
from datetime import date
```

Change the `search` method signature (currently `def search(self, query: str, top_k: int | None = None) -> RetrievalResult:`) to:

```python
    def search(
        self, query: str, top_k: int | None = None, as_of: date | None = None
    ) -> RetrievalResult:
```

Insert the filtering step after the recency-boost block and before the rerank block (i.e. right after this existing code:

```python
        if config.recency_boost:
            from src.retrieve.recency import apply_recency_boost

            start = time.perf_counter()
            fused = apply_recency_boost(fused, self.by_id, weight=config.recency_boost)
            latency["recency"] = (time.perf_counter() - start) * 1000
```

) add:

```python
        if as_of is not None:
            from src.retrieve.recency import filter_as_of

            start = time.perf_counter()
            fused = filter_as_of(fused, self.by_id, as_of)
            latency["as_of_filter"] = (time.perf_counter() - start) * 1000
```

Leave the rest of the method (rerank block and the final `hits = fused[:k]` / `return RetrievalResult(...)`) unchanged — it already operates on `fused` regardless of how it got filtered, and an empty `fused` list correctly produces an empty `hits` list.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "C:\Users\rsing\gst-rag" && python -m pytest tests/test_pipeline.py -v`

Expected: all tests in the file PASS, including the two new ones and the full existing suite (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/retrieve/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire as_of filtering into RetrievalPipeline.search"
```

---

## Task 2: Wire `as_of` parsing and a `/variants` endpoint into the FastAPI app

**Files:**
- Modify: `src/serve/app.py`
- Test: `tests/test_serve.py` (new)

**Interfaces:**
- Consumes: `RetrievalPipeline.search(query, top_k=None, as_of=None)` (Task 1), `PipelineConfig` and `ABLATION_LADDER` from `src/retrieve/pipeline.py`.
- Produces: `empty_result_warning(as_of: date | None) -> str`, `variant_summary(config: PipelineConfig) -> dict`, and a `GET /variants` route returning `list[dict]` (one entry per `ABLATION_LADDER` row). `/query` now honors `request.as_of` and returns `400` for an invalid date string.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_serve.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "C:\Users\rsing\gst-rag" && python -m pytest tests/test_serve.py -v`

Expected: FAIL with `ImportError: cannot import name 'empty_result_warning' from 'src.serve.app'` (neither helper exists yet). If `fastapi`/`pydantic` aren't installed in this environment, expected instead is the whole file SKIPPED via `importorskip` — install them first (`pip install fastapi pydantic`) so this task can actually be verified.

- [ ] **Step 3: Implement the helpers and wire them into the app**

In `src/serve/app.py`:

1. Add `from datetime import date` to the imports, and change:

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
```

to:

```python
from datetime import date

from fastapi import FastAPI, HTTPException
```

(the `HTMLResponse` import and the inline `/` route it powers are removed in Task 6, not here — leave the `/` route as-is for now, just drop nothing yet if that would break it; only add the `datetime` import in this step).

2. Add a top-level import so `ABLATION_LADDER`/`PipelineConfig` are available outside `lifespan` (add this line near the top, with the other top-level code, before `app = FastAPI(...)`):

```python
from src.retrieve.pipeline import ABLATION_LADDER, PipelineConfig
```

3. In the `lifespan` function, simplify its existing import line from:

```python
    from src.retrieve.pipeline import ABLATION_LADDER, RetrievalPipeline
```

to:

```python
    from src.retrieve.pipeline import RetrievalPipeline
```

(now that `ABLATION_LADDER` is imported at module level).

4. Add the two pure helper functions and the `/variants` route. Place them after the `/health` route and before `/query`:

```python
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


def empty_result_warning(as_of: date | None) -> str:
    if as_of is not None:
        return f"no in-force provision found for {as_of.isoformat()}"
    return "no passages retrieved; the system should abstain"
```

5. In the `query` handler, parse `as_of` and pass it through. Change:

```python
    if request.variant:
        config = STATE["variants"].get(request.variant)
        if config is None:
            raise HTTPException(400, f"unknown variant; have {sorted(STATE['variants'])}")
        pipeline = pipeline.with_config(config)

    started = time.perf_counter()
    result = pipeline.search(request.question, top_k=request.top_k)
    graph = STATE["graph"]
```

to:

```python
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
```

6. Change the existing empty-hits warning. Replace:

```python
    if not result.hits:
        warnings.append("no passages retrieved; the system should abstain")
```

with:

```python
    if not result.hits:
        warnings.append(empty_result_warning(as_of_date))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "C:\Users\rsing\gst-rag" && python -m pytest tests/test_serve.py tests/test_pipeline.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/serve/app.py tests/test_serve.py
git commit -m "feat: wire as_of parsing and add GET /variants to the API"
```

---

## Task 3: Scaffold the frontend project (Vite + React + TypeScript + Tailwind)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/.gitignore`
- Create: `frontend/src/index.css`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

**Interfaces:**
- Produces: a `frontend/` project buildable with `npm run build` (outputs `frontend/dist/`) and runnable in dev mode with `npm run dev` (Vite on `localhost:5173`, proxying `/query`, `/health`, `/variants` to `localhost:8000`).

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "gst-rag-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.4",
    "typescript": "^5.5.3",
    "vite": "^5.3.1"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/query": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/variants": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
```

- [ ] **Step 3: Create `frontend/tsconfig.json` and `frontend/tsconfig.node.json`**

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Create `frontend/tailwind.config.js` and `frontend/postcss.config.js`**

`frontend/tailwind.config.js`:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {},
  },
  plugins: [],
};
```

`frontend/postcss.config.js`:

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>gst-rag</title>
  </head>
  <body class="bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `frontend/.gitignore`**

```
node_modules
dist
```

- [ ] **Step 7: Create `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html {
  color-scheme: light dark;
}
```

- [ ] **Step 8: Create `frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 9: Create `frontend/src/App.tsx`** (minimal, real, replaced fully in Task 5)

```tsx
export default function App() {
  return (
    <div className="min-h-screen bg-white p-10 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <h1 className="text-xl font-semibold">gst-rag</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400">
        frontend scaffold ready
      </p>
    </div>
  );
}
```

- [ ] **Step 10: Install dependencies**

Run: `cd "C:\Users\rsing\gst-rag\frontend" && npm install`

Expected: completes without error, creates `frontend/node_modules` and `frontend/package-lock.json`.

- [ ] **Step 11: Verify it builds**

Run: `cd "C:\Users\rsing\gst-rag\frontend" && npm run build`

Expected: succeeds, creates `frontend/dist/index.html` and `frontend/dist/assets/`.

- [ ] **Step 12: Commit**

```bash
cd "C:\Users\rsing\gst-rag"
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.json frontend/tsconfig.node.json frontend/tailwind.config.js frontend/postcss.config.js frontend/index.html frontend/.gitignore frontend/src/index.css frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat: scaffold Vite + React + TypeScript + Tailwind frontend"
```

---

## Task 4: API client and shared TypeScript types

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`

**Interfaces:**
- Consumes: the JSON shapes returned by `GET /variants` and `POST /query` (from Task 2 and the pre-existing `/query` handler in `src/serve/app.py`).
- Produces: `Citation`, `QueryTrace`, `QueryResponse`, `QueryRequest`, `Variant` TypeScript interfaces; `fetchVariants(): Promise<Variant[]>`, `runQuery(request: QueryRequest): Promise<QueryResponse>` functions, both used by Task 5's `App.tsx`.

- [ ] **Step 1: Create `frontend/src/types.ts`**

```typescript
export interface Citation {
  chunk_id: string;
  doc_id: string;
  score: number;
  status: "in_force" | "amended" | "superseded" | "unknown";
  snippet: string;
  section: string | null;
  published: string | null;
}

export interface QueryTrace {
  stage_latency_ms: Record<string, number>;
  total_ms: number;
  config: string;
}

export interface QueryResponse {
  question: string;
  rewritten_query: string;
  answer: string | null;
  citations: Citation[];
  trace: QueryTrace;
  warnings: string[];
}

export interface QueryRequest {
  question: string;
  top_k?: number;
  as_of?: string;
  variant?: string;
}

export interface Variant {
  name: string;
  use_bm25: boolean;
  use_dense: boolean;
  rerank: boolean;
  query_rewrite: boolean;
  recency_boost: number;
}
```

- [ ] **Step 2: Create `frontend/src/api.ts`**

```typescript
import type { QueryRequest, QueryResponse, Variant } from "./types";

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchVariants(): Promise<Variant[]> {
  const response = await fetch("/variants");
  return parseJsonOrThrow<Variant[]>(response);
}

export async function runQuery(request: QueryRequest): Promise<QueryResponse> {
  const response = await fetch("/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseJsonOrThrow<QueryResponse>(response);
}
```

- [ ] **Step 3: Verify it type-checks and builds**

Run: `cd "C:\Users\rsing\gst-rag\frontend" && npm run build`

Expected: succeeds (these modules aren't imported by `App.tsx` yet, but `tsc -b` type-checks every file under `src/` regardless).

- [ ] **Step 4: Commit**

```bash
cd "C:\Users\rsing\gst-rag"
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat: add typed API client for the gst-rag backend"
```

---

## Task 5: Build the search UI and wire it to the live API

**Files:**
- Create: `frontend/src/components/SearchBar.tsx`
- Create: `frontend/src/components/ControlsBar.tsx`
- Create: `frontend/src/components/TracePanel.tsx`
- Create: `frontend/src/components/WarningsBanner.tsx`
- Create: `frontend/src/components/CitationCard.tsx`
- Create: `frontend/src/components/ResultsList.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `scripts/build_dev_index.py` (backend-side dev helper, not shipped to production, used only to verify this task locally)

**Interfaces:**
- Consumes: `Citation`, `QueryTrace`, `QueryResponse`, `Variant` types and `fetchVariants`/`runQuery` from Task 4 (`frontend/src/api.ts`, `frontend/src/types.ts`).
- Produces: the complete single-page UI. No other task consumes these components directly.

- [ ] **Step 1: Create a fixture-backed dev index so the backend can run without a real scrape**

Create `scripts/build_dev_index.py`:

```python
"""Build a tiny hashing-embedder index from the test fixtures, for local
frontend development only. The numbers and even the retrieval quality are
meaningless here -- see scripts/demo_ablation.py for why. This exists purely
so `uvicorn src.serve.app:app` has something to load while the frontend is
being built, before the real corpus (see Makefile: scrape/extract/build) is
ready.

    python scripts/build_dev_index.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.index.build import build_index
from src.index.embedders import HashingEmbedder
from tests.fixtures import DOCUMENTS

if __name__ == "__main__":
    build_index(DOCUMENTS, "section", HashingEmbedder(), "data/index_dev")
```

Run: `cd "C:\Users\rsing\gst-rag" && python scripts/build_dev_index.py`

Expected: prints chunk/embedding stats and `wrote index to data\index_dev`; creates `data/index_dev/chunks.jsonl`, `data/index_dev/embeddings.npy`, `data/index_dev/manifest.json`.

- [ ] **Step 2: Start the backend against the dev index in one terminal**

Run (leave running): `cd "C:\Users\rsing\gst-rag" && EMBEDDER=hashing RERANK=0 INDEX_DIR=data/index_dev python -m uvicorn src.serve.app:app --port 8000`

Expected: starts without error; `RERANK=0` skips loading the cross-encoder (no torch/download needed for this dev loop). Leave it running for the rest of this task.

- [ ] **Step 3: Create `frontend/src/components/SearchBar.tsx`**

```tsx
import { FormEvent, useState } from "react";

interface SearchBarProps {
  onSearch: (question: string) => void;
  loading: boolean;
}

const EXAMPLE_QUERIES = [
  "Can I claim ITC on hotel stay?",
  "What was the rate on hotel accommodation in FY 2019-20?",
  "What is the late fee for not filing a return on time?",
  "When can the proper officer cancel a GST registration?",
];

export default function SearchBar({ onSearch, loading }: SearchBarProps) {
  const [question, setQuestion] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (question.trim()) {
      onSearch(question.trim());
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Can I claim ITC on hotel stay?"
          className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-2.5
                     text-sm text-slate-900 placeholder:text-slate-400
                     focus:border-slate-500 focus:outline-none
                     dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white
                     disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLE_QUERIES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => {
              setQuestion(example);
              onSearch(example);
            }}
            className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600
                       hover:border-slate-400 dark:border-slate-700 dark:text-slate-400"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/ControlsBar.tsx`**

```tsx
import type { Variant } from "../types";

interface ControlsBarProps {
  variants: Variant[];
  selectedVariant: string;
  onVariantChange: (name: string) => void;
  asOf: string;
  onAsOfChange: (value: string) => void;
}

export default function ControlsBar({
  variants,
  selectedVariant,
  onVariantChange,
  asOf,
  onAsOfChange,
}: ControlsBarProps) {
  const active = variants.find((variant) => variant.name === selectedVariant);

  return (
    <div className="mt-4 flex flex-wrap items-center gap-4 text-sm">
      <label className="flex items-center gap-2">
        <span className="text-slate-500 dark:text-slate-400">Variant</span>
        <select
          value={selectedVariant}
          onChange={(event) => onVariantChange(event.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1
                     dark:border-slate-700 dark:bg-slate-900"
        >
          {variants.map((variant) => (
            <option key={variant.name} value={variant.name}>
              {variant.name}
            </option>
          ))}
        </select>
      </label>
      {active && (
        <span className="text-xs text-slate-400">
          {[
            active.use_bm25 && "BM25",
            active.use_dense && "dense",
            active.rerank && "reranker",
            active.query_rewrite && "rewrite",
          ]
            .filter(Boolean)
            .join(" + ")}
        </span>
      )}
      <label className="flex items-center gap-2">
        <span className="text-slate-500 dark:text-slate-400">As of</span>
        <input
          type="date"
          value={asOf}
          onChange={(event) => onAsOfChange(event.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1
                     dark:border-slate-700 dark:bg-slate-900"
        />
        {asOf && (
          <button
            type="button"
            onClick={() => onAsOfChange("")}
            className="text-xs text-slate-400 underline"
          >
            clear
          </button>
        )}
      </label>
    </div>
  );
}
```

- [ ] **Step 5: Create `frontend/src/components/TracePanel.tsx`**

```tsx
import type { QueryTrace } from "../types";

interface TracePanelProps {
  question: string;
  rewrittenQuery: string;
  trace: QueryTrace;
}

export default function TracePanel({ question, rewrittenQuery, trace }: TracePanelProps) {
  const stages = Object.entries(trace.stage_latency_ms);
  const maxMs = Math.max(...stages.map(([, ms]) => ms), 1);

  return (
    <div
      className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs
                 font-mono text-slate-500 dark:border-slate-800 dark:bg-slate-900/50
                 dark:text-slate-400"
    >
      {rewrittenQuery !== question && (
        <div className="mb-2">
          rewritten: <span className="text-slate-700 dark:text-slate-300">{rewrittenQuery}</span>
        </div>
      )}
      <div className="space-y-1">
        {stages.map(([stage, ms]) => (
          <div key={stage} className="flex items-center gap-2">
            <span className="w-20 shrink-0">{stage}</span>
            <div className="h-1.5 flex-1 rounded-full bg-slate-200 dark:bg-slate-800">
              <div
                className="h-1.5 rounded-full bg-slate-500 dark:bg-slate-400"
                style={{ width: `${(ms / maxMs) * 100}%` }}
              />
            </div>
            <span className="w-16 shrink-0 text-right">{ms.toFixed(1)}ms</span>
          </div>
        ))}
      </div>
      <div className="mt-2">
        total {trace.total_ms.toFixed(1)}ms · {trace.config}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create `frontend/src/components/WarningsBanner.tsx`**

```tsx
interface WarningsBannerProps {
  warnings: string[];
}

export default function WarningsBanner({ warnings }: WarningsBannerProps) {
  if (warnings.length === 0) return null;

  return (
    <div className="mt-4 space-y-2">
      {warnings.map((warning) => {
        const severe = warning.includes("superseded") || warning.includes("no in-force");
        return (
          <div
            key={warning}
            className={
              "rounded-lg border-l-4 px-3 py-2 text-sm " +
              (severe
                ? "border-red-500 bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-300"
                : "border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300")
            }
          >
            {warning}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 7: Create `frontend/src/components/CitationCard.tsx`**

```tsx
import type { Citation } from "../types";

const STATUS_STYLES: Record<Citation["status"], string> = {
  in_force:
    "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300",
  amended:
    "border-amber-500 bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300",
  superseded:
    "border-red-500 bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300",
  unknown:
    "border-slate-400 bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-400",
};

export default function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div className="rounded-lg border-l-4 border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[citation.status]}`}>
          {citation.status}
        </span>
        <span className="font-semibold text-slate-800 dark:text-slate-100">{citation.doc_id}</span>
        {citation.section && (
          <span className="text-slate-500 dark:text-slate-400">section {citation.section}</span>
        )}
        <span className="ml-auto font-mono text-xs text-slate-400">
          score {citation.score.toFixed(3)}
          {citation.published ? ` · ${citation.published}` : ""}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        {citation.snippet}
      </p>
    </div>
  );
}
```

- [ ] **Step 8: Create `frontend/src/components/ResultsList.tsx`**

```tsx
import type { Citation } from "../types";
import CitationCard from "./CitationCard";

export default function ResultsList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return (
      <p className="mt-6 text-sm text-slate-500 dark:text-slate-400">
        No passages retrieved.
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-3">
      {citations.map((citation) => (
        <CitationCard key={citation.chunk_id} citation={citation} />
      ))}
    </div>
  );
}
```

- [ ] **Step 9: Rewrite `frontend/src/App.tsx`**

```tsx
import { useEffect, useState } from "react";
import SearchBar from "./components/SearchBar";
import ControlsBar from "./components/ControlsBar";
import TracePanel from "./components/TracePanel";
import WarningsBanner from "./components/WarningsBanner";
import ResultsList from "./components/ResultsList";
import { fetchVariants, runQuery } from "./api";
import type { QueryResponse, Variant } from "./types";

function useDarkMode(): [boolean, () => void] {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem("gst-rag-theme");
    if (stored) return stored === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("gst-rag-theme", dark ? "dark" : "light");
  }, [dark]);

  return [dark, () => setDark((value) => !value)];
}

export default function App() {
  const [dark, toggleDark] = useDarkMode();
  const [variants, setVariants] = useState<Variant[]>([]);
  const [selectedVariant, setSelectedVariant] = useState("");
  const [asOf, setAsOf] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVariants()
      .then((fetched) => {
        setVariants(fetched);
        const preferred = fetched.find((v) => v.name === "Hybrid + reranker");
        setSelectedVariant((preferred ?? fetched[0])?.name ?? "");
      })
      .catch((err) => setError(String(err)));
  }, []);

  async function handleSearch(question: string) {
    setLoading(true);
    setError(null);
    try {
      const response = await runQuery({
        question,
        variant: selectedVariant || undefined,
        as_of: asOf || undefined,
      });
      setResult(response);
    } catch (err) {
      setError(String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="mx-auto max-w-3xl px-4 py-10">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">GST retrieval</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Retrieval only — citations carry legal status, no generated answer.
            </p>
          </div>
          <button
            type="button"
            onClick={toggleDark}
            className="rounded-full border border-slate-300 px-3 py-1 text-xs dark:border-slate-700"
          >
            {dark ? "light" : "dark"}
          </button>
        </header>

        <SearchBar onSearch={handleSearch} loading={loading} />
        <ControlsBar
          variants={variants}
          selectedVariant={selectedVariant}
          onVariantChange={setSelectedVariant}
          asOf={asOf}
          onAsOfChange={setAsOf}
        />

        {error && (
          <div
            className="mt-4 rounded-lg border-l-4 border-red-500 bg-red-50 px-3 py-2
                       text-sm text-red-800 dark:bg-red-950/40 dark:text-red-300"
          >
            {error}
          </div>
        )}

        {result && (
          <>
            <TracePanel
              question={result.question}
              rewrittenQuery={result.rewritten_query}
              trace={result.trace}
            />
            <WarningsBanner warnings={result.warnings} />
            <ResultsList citations={result.citations} />
          </>
        )}

        {!result && !error && !loading && (
          <p className="mt-8 text-sm text-slate-500 dark:text-slate-400">
            Try a question above, or pick one of the examples.
          </p>
        )}

        <footer className="mt-16 border-t border-slate-200 pt-4 text-xs text-slate-400 dark:border-slate-800">
          Data from cbic.gov.in, redistributed as derived indices. Research project — not legal advice.
        </footer>
      </div>
    </div>
  );
}
```

- [ ] **Step 10: Verify it builds**

Run: `cd "C:\Users\rsing\gst-rag\frontend" && npm run build`

Expected: succeeds with no TypeScript errors.

- [ ] **Step 11: Verify it works against the live dev backend**

In a second terminal (leaving the Task 5 Step 2 `uvicorn` running):

Run: `cd "C:\Users\rsing\gst-rag\frontend" && npm run dev`

Open `http://localhost:5173` in a browser and check:
- The variant dropdown populates (proves `GET /variants` round-trips).
- Clicking an example query returns citation cards with colored status badges and a trace panel.
- Setting "As of" to `2018-01-01` and re-running the hotel-accommodation example excludes the 2019 notification and/or shows the "no in-force provision" warning if it empties the results for a given question.
- The dark-mode toggle flips the page and survives a refresh (persisted via `localStorage`).

Stop both the `npm run dev` process and the Step 2 `uvicorn` process once confirmed (Ctrl+C in each terminal).

- [ ] **Step 12: Commit**

```bash
cd "C:\Users\rsing\gst-rag"
git add scripts/build_dev_index.py frontend/src/components frontend/src/App.tsx
git commit -m "feat: build search UI and wire it to the live retrieval API"
```

Note: `data/index_dev/` is developer-local scratch output from Step 1, not part of the deliverable — confirm it's covered by `.gitignore` before committing (see Task 6, which also touches `.gitignore` if needed) rather than adding it here.

---

## Task 6: Serve the built frontend from FastAPI

**Files:**
- Modify: `src/serve/app.py`
- Modify: `.gitignore` (repo root, if `data/index_dev/` isn't already excluded)

**Interfaces:**
- Produces: FastAPI serves `frontend/dist/` as static files at `/` (mounted after all API routes), with `html=True` so `/` returns `frontend/dist/index.html`. The old inline-HTML `/` route is removed.

- [ ] **Step 1: Check `.gitignore` covers the dev index**

Read the repo-root `.gitignore`. If it does not already exclude `data/index_dev/` and `data/index/`, add:

```
data/index_dev/
data/index/
```

- [ ] **Step 2: Remove the inline HTML route and add static file serving**

In `src/serve/app.py`, remove this entire route (it's replaced by the built frontend):

```python
@app.get("/", response_class=HTMLResponse)
async def index_page():
    return """<!doctype html>
...
</script></body></html>"""
```

Remove the now-unused `from fastapi.responses import HTMLResponse` import if nothing else in the file uses `HTMLResponse` (it doesn't, after this removal).

Add near the top of the file, with the other imports:

```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles
```

At the very end of the file (after the `/query` route, and after `variant_summary`/`empty_result_warning`/`/variants` from Task 2), add:

```python
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
```

The `.exists()` guard matters: it keeps `import src.serve.app` (and therefore `tests/test_serve.py`) working even when `frontend/dist/` hasn't been built yet, since `StaticFiles` raises at construction time if its directory is missing.

- [ ] **Step 3: Verify the existing backend tests still pass**

Run: `cd "C:\Users\rsing\gst-rag" && python -m pytest tests/ -v`

Expected: all tests PASS (this task doesn't change any tested logic, only routing/imports).

- [ ] **Step 4: Verify the built frontend is served**

Run: `cd "C:\Users\rsing\gst-rag\frontend" && npm run build`

Then, from the repo root: `cd "C:\Users\rsing\gst-rag" && EMBEDDER=hashing RERANK=0 INDEX_DIR=data/index_dev python -m uvicorn src.serve.app:app --port 8000`

In another terminal: `curl -s http://localhost:8000/ | head -c 200` should show the built `index.html` (containing `<title>gst-rag</title>`), and `curl -s http://localhost:8000/health` should still return the JSON health payload. Stop the server (Ctrl+C).

- [ ] **Step 5: Commit**

```bash
git add src/serve/app.py .gitignore
git commit -m "feat: serve the built frontend as static files from FastAPI"
```

---

## Task 7: Run the real CBIC ingestion pipeline

**Files:** none (this task produces data under `data/`, not source changes)

**Interfaces:**
- Produces: `data/raw/manifest.jsonl` + cached PDFs/HTML under `data/raw/cache/`, `data/processed/documents.jsonl`, `results/extraction_report.md`, and a real index at `data/index/` (`chunks.jsonl`, `embeddings.npy`, `manifest.json`) built with `BAAI/bge-small-en-v1.5`.

- [ ] **Step 1: Install the full dependency set**

Run: `cd "C:\Users\rsing\gst-rag" && pip install -r requirements.txt`

Then: `pip install torch --index-url https://download.pytorch.org/whl/cpu`

Expected: both complete without error. This is a real download (sentence-transformers, torch CPU wheels) — expect several minutes depending on connection speed.

- [ ] **Step 2: Check robots.txt before doing anything else**

Run: `python -m src.ingest.cbic_scraper --check-robots`

Expected output: `robots.txt allows this crawler: True`. If it prints `False`, STOP — do not proceed to scraping. Report this back rather than working around it; `cbic_scraper.py`'s `main()` already refuses to scrape in that case.

- [ ] **Step 3: Scrape**

Run (in the background, since this is rate-limited to 1 request/2s and the corpus size — and therefore the runtime — isn't known until the index pages are fetched): `make scrape`

Monitor progress (the scraper logs one line per index page and prints a summary at the end: `N documents, M failed`). If the total document count turns out to be in the thousands (multi-hour runtime), stop and reassess with a `--limit` rather than waiting indefinitely — e.g. `python -m src.ingest.cbic_scraper --out data/raw/manifest.jsonl --delay 2.0 --limit 400`.

Expected: `data/raw/manifest.jsonl` exists, `data/raw/cache/` contains cached `.html`/`.pdf` files, most documents have no `fetch_error`.

- [ ] **Step 4: Extract**

Run: `make extract`

Expected: `data/processed/documents.jsonl` exists, `results/extraction_report.md` is written. Skim the report for a high failure rate (which would indicate the PDF parser is choking on this batch) before moving on.

- [ ] **Step 5: Build the real index**

Run: `make build`

Expected: prints chunk count and embedding throughput, writes `data/index/chunks.jsonl`, `data/index/embeddings.npy`, `data/index/manifest.json`. This step downloads `BAAI/bge-small-en-v1.5` on first run (a few hundred MB) and then embeds every chunk on CPU — expect this to take a while for a few hundred documents.

No commit for this task — everything it produces lives under `data/`, which `.gitignore` already excludes (raw/processed corpus and the index are regenerable, not source).

---

## Task 8: End-to-end verification against the real corpus

**Files:** none

- [ ] **Step 1: Serve the real index**

Run: `cd "C:\Users\rsing\gst-rag" && make serve`

This uses the Makefile's defaults (`INDEX=data/index`, and `app.py`'s own defaults `EMBEDDER=sentence-transformers`, `RERANK=1`), so it loads the real index built in Task 7 and the real cross-encoder reranker (another model download on first run: `cross-encoder/ms-marco-MiniLM-L-6-v2`).

Expected: starts without error, logs that it's listening on `0.0.0.0:8000`.

- [ ] **Step 2: Verify in a browser**

Open `http://localhost:8000/`. Confirm:
- The page loads the real React frontend (not the old inline HTML).
- Running one of the example queries returns real CBIC citations with plausible snippets.
- The variant dropdown lists all `ABLATION_LADDER` rows and switching variants changes the results.
- Setting an "as of" date in the past (e.g. a date before a known amendment) changes or empties the results, with the appropriate warning shown.
- A citation whose underlying notification has been superseded or amended shows the corresponding badge and warning banner.
- Dark mode toggles correctly.

- [ ] **Step 3: Run the full test suite one more time**

Run: `cd "C:\Users\rsing\gst-rag" && python -m pytest tests/ -v`

Expected: all tests PASS (unchanged from Task 6 — this is a final regression check now that the real corpus exists on disk alongside the dev fixtures).

- [ ] **Step 4: Report results back**

Summarize what's running, the corpus size (`n_chunks`, `n_documents` from `data/index/manifest.json`), and any warnings encountered during scrape/extract/build (Task 7) that are worth flagging — e.g. a nonzero `fetch_error` count or a high PDF-extraction failure rate.

No commit for this task — it's verification only.
