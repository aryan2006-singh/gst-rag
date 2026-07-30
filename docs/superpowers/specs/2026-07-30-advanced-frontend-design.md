# gst-rag: advanced frontend + real end-to-end run

Date: 2026-07-30
Status: approved

## Goal

Replace the current ~40-line inline HTML/JS page served by `src/serve/app.py`
with a proper React frontend, and run the system against a real scraped CBIC
corpus instead of the fixture data, so there's a working, presentable app to
look at end to end.

## Non-goals

- No answer generation. The project intentionally returns `answer: null` —
  retrieval quality is what's being measured, and an ungrounded generated
  answer over legal text is a liability. Not changing that.
- No new automated frontend test framework. Backend already has 110 offline
  tests; a couple more cover the new wiring. Frontend correctness is verified
  by running it and trying example queries, not a test suite.
- No multi-page routing, no user accounts, no query history persistence
  beyond the current session.

## Backend changes

Two features selected for the frontend aren't fully wired on the backend today.

**1. `as_of` filtering.** `QueryRequest.as_of` is accepted by the `/query`
endpoint but never used — dead parameter. `src/retrieve/recency.py` already
has `filter_as_of(ranked, chunks_by_id, as_of)`, it's just never called.

- Add an `as_of: date | None` parameter to `RetrievalPipeline.search()`.
  Apply `filter_as_of` after fusion + recency boost, before rerank — same
  slot `recency_boost` occupies, so reranking only ever sees valid
  candidates.
- In `app.py`, parse `request.as_of` (ISO date string) and pass it through.
  Invalid date strings → 400.
- If filtering empties the result set, return `hits: []` with a warning
  string: `"no in-force provision found for {as_of}"`. Do not fall back to
  current law — that's the whole point of the feature per the module's own
  docstring.

**2. `GET /variants`.** The only way to discover valid `variant` values today
is triggering the 400 error on `/query` and reading its message. Add an
endpoint returning, for each entry in `ABLATION_LADDER`:

```json
{"name": "Hybrid + reranker", "use_bm25": true, "use_dense": true,
 "rerank": true, "query_rewrite": false, "recency_boost": 0.0}
```

The frontend uses this to populate the variant dropdown and show what each
variant actually does (e.g. a small "BM25 + dense + reranker" caption).

No other backend changes. `/query`'s citation/trace/warnings shape is
unchanged.

## Frontend

New `frontend/` directory at repo root: Vite + React 18 + TypeScript +
Tailwind CSS. Build output (`frontend/dist`) is served by FastAPI as static
files — `StaticFiles(directory="frontend/dist", html=True)` mounted at `/`,
registered *after* `/health`, `/query`, and `/variants` so the API routes
still take priority. The existing inline-HTML `/` route in `app.py` is
deleted. One process, one port (8000) — matches the existing `make serve`
workflow.

### Layout (single view, no client-side routing)

- **Header** — title, dark-mode toggle. Toggle persists to `localStorage`,
  defaults to `prefers-color-scheme`.
- **Search bar** — text input + submit, Enter-to-search, a row of clickable
  example queries (pulled from the README's own examples, e.g. "Can I claim
  ITC on hotel stay?", "What was the rate in FY 2019-20?").
- **Controls row** — variant dropdown (from `GET /variants`, default
  "Hybrid + reranker"), optional as-of date picker (clears to "current law").
- **Trace panel** — rewritten query (shown only if it differs from the
  input), per-stage latency as a small horizontal breakdown, total ms,
  active variant name.
- **Warnings banner(s)** — amber for `amended`, red for `superseded`/
  abstain cases, rendered above the results list.
- **Citation cards** — colored status badge (green `in_force` / amber
  `amended` / red `superseded`), doc id, section, published date, score,
  snippet text.
- **States** — empty state on first load (examples + one-paragraph
  explainer), loading spinner during search, error banner for network
  failures or the backend's `503 index still loading`.
- **Footer** — the README's "not legal advice" / CBIC-sourcing line.

### Tech notes

- Plain `fetch` via a small typed API client module mirroring the Pydantic
  models (`QueryRequest`, `QueryResponse`, `Citation`). No state library —
  it's one screen, `useState`/`useReducer` is enough.
- Component breakdown: `SearchBar`, `ControlsBar`, `TracePanel`,
  `WarningsBanner`, `CitationCard`, `ResultsList`, `App`.
- Styling: neutral palette, semantic colors reserved for legal status
  (green/amber/red) so they stay meaningful and aren't reused decoratively
  elsewhere.

## Data: real CBIC corpus

`make check-robots` → `make scrape` → `make extract` → `make build`
(`bge-small-en-v1.5` embeddings, CPU) → `make serve`.

Risk to flag: the scraper has no document cap by default, and CBIC's
circular + notification indices go back to 2017, so this could be several
hundred PDFs. At the mandated 2s/request delay that's potentially tens of
minutes or more. Runs in the background with progress checked periodically;
if it proves impractically large, fall back to `--limit` on
`cbic_scraper.py` rather than waiting indefinitely.

## Testing

- Backend: add tests for `as_of` filtering (empty-result warning case
  included) and `GET /variants`, in the same style as the existing
  `tests/test_pipeline.py` / `test_eval_harness.py`.
- Frontend: manual verification only — run the dev server, execute the
  example queries, check dark mode, check the as-of and variant controls
  change results.

## Rollout

1. Backend wiring (`as_of`, `/variants`) + tests.
2. Scaffold `frontend/`, build out components against a running backend
   (fixture or partial corpus is fine while iterating).
3. Wire FastAPI static serving, remove the old inline HTML route.
4. Run the real scrape → extract → build pipeline.
5. `make serve` end to end against the real corpus; verify in browser.
