# gst-rag

Retrieval over Indian GST law, built around an evaluation harness rather than a
chatbot.

> **Headline (fill in from your own run):** hybrid BM25 + dense retrieval with
> cross-encoder reranking improved Recall@5 from _A_ to _B_ (+_D_, 95% CI
> [_lo_, _hi_], p=_p_) over a dense-only baseline on _N_ hand-labelled questions.
> LLM-judge faithfulness validated at Cohen's kappa = _k_ against 50 human labels.

```
CBIC PDFs ──▶ extract ──▶ chunk ──▶ ┌── BM25 ────┐
              (failure     (3        │            ├─▶ RRF ─▶ rerank ─▶ top-k
               taxonomy)   strategies)└── dense ──┘                      │
                                                                          ▼
   gold set (150-300 hand-labelled Qs) ──▶ EVAL HARNESS ◀─────────────────┘
                                              │
                    Recall@k · MRR · nDCG · bootstrap CI · paired permutation
                    test · Holm-Bonferroni · judge validated by Cohen's kappa
```

---

## Why this repo is not another RAG chatbot

There are tens of thousands of "chat with your PDF" projects. The thing that is
actually scarce is a retrieval system with an evaluation you can trust. So the
centre of gravity here is `src/eval/`, and the retrieval pipeline exists to give
it something to measure.

Three commitments, enforced by tests:

**1. No number without a confidence interval.** On 250 questions the standard
error of Recall@5 is about 0.032. A pipeline at 0.71 and one at 0.74 are
indistinguishable. Every cell in the results table carries a bootstrap CI, and
every non-baseline row carries a paired permutation test with Holm-Bonferroni
correction across the family of comparisons.

**2. No judged metric without a validated judge.** An LLM-judge faithfulness
score is meaningless until you show it tracks human labels on *your* data.
`scripts/validate_judge.py` runs that check and reports Cohen's kappa — not raw
agreement, because a judge that says "faithful" every time scores 85% raw
agreement on an 85%-faithful dataset and is worthless. Kappa catches that; it
scores 0.

**3. No gold set you can fool yourself with.** The validator rejects gold sets
that are mostly LLM-generated (synthetic questions are paraphrases of chunks you
already indexed, so retrieval on them is trivially easy), rejects chunk ids that
don't exist in the index, and warns when there's no held-out test split.

---

## Quickstart — 5 seconds, no downloads

```bash
pip install numpy pytest        # that's all the demo needs
make test                       # 117 tests, offline
make demo                       # full ablation on a built-in fixture corpus
```

`make demo` output, verbatim from a real run:

```
BM25 only                    recall@5=0.889  mrr=0.889  ndcg@10=0.889
Dense only                   recall@5=0.833  mrr=0.528  ndcg@10=0.647
Hybrid (RRF)                 recall@5=1.000  mrr=0.856  ndcg@10=0.885
Hybrid + reranker            recall@5=1.000  mrr=0.926  ndcg@10=0.944
Hybrid + reranker + rewrite  recall@5=1.000  mrr=1.000  ndcg@10=1.000

significant improvements over baseline: none
(none is the expected answer at this sample size)
```

Recall@5 goes 0.833 → 1.000 and **nothing is significant**, because n=9. That is
the entire lesson of this project rendered in one command. A bare table would
have reported a 20-point win.

---

## The real pipeline

```bash
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU is fine

make check-robots      # do this first, and honour the answer
make scrape            # rate-limited 1 req / 2s, everything cached to disk
make extract           # PDFs -> text, plus results/extraction_report.md
make build             # chunk + embed  (bge-small on CPU)
make eval              # -> RESULTS.md
make serve             # builds frontend/ (npm install && npm run build), then https://gst-rag-dv7x.onrender.com
```

Everything runs on CPU with no API keys. Embeddings are `BAAI/bge-small-en-v1.5`,
reranking is `cross-encoder/ms-marco-MiniLM-L-6-v2`, and the judge is either
heuristic or a small local NLI cross-encoder.

---

## What's domain-specific (and why that matters)

A generic RAG stack applied to tax law produces confident, well-cited, *wrong*
answers. Three places this repo diverges from the tutorial version:

**Tokenizer.** `section 16(2)(c)` and `13/2017-CT(R)` survive tokenization
intact. A whitespace tokenizer shatters them, and those tokens are exactly what
users search for. The stopword list is also short on purpose — "not" carries
meaning in "shall not be entitled to credit".

**Supersession graph.** Notifications amend and supersede each other.
`src/retrieve/recency.py` parses "in supersession of Notification No. ..."
directly out of the corpus, builds the graph, and labels every citation
`in_force` / `amended` / `superseded`. There is also as-of-date filtering, so
"what was the rate in FY 2019-20" is answerable rather than confidently wrong.
The fixture gold set includes a temporal question where the 2017 notification
says 18% and the 2019 amendment says 12% — retrieving the older one is a
correctness failure, not a ranking failure.

**Query rewriting.** Users write "can I claim ITC on hotel stay". The corpus says
"input tax credit shall not be available in respect of ... accommodation".
A 40-line acronym table closes most of that gap for zero latency, and it is its
own ablation row — if the dictionary beats an LLM rewriter, that is the finding.

---

## Building the gold set (the hard part)

Nothing in this repo will save you from labelling. Budget 10-15 hours.

| | |
|---|---|
| **Size** | 150-300 questions. `required_sample_size(0.03)` says you need >500 to detect a 3-point improvement — so accept that only large effects will be detectable, and say so. |
| **Sources** | Real questions: CAclubindia and Taxfull forum threads, official CBIC FAQs, CA Inter/Final exam papers. Cap `llm_generated` at 30%; the validator enforces it. |
| **Labels** | For each question, the chunk ids that actually answer it. Graded gains (3/2/1) where some passages are better than others — nDCG uses them. |
| **Splits** | dev for tuning chunk size / `rrf_k` / rerank depth, test for the numbers you report. Tuning and reporting on the same questions is reporting your training accuracy. |
| **Question types** | Include `temporal` (supersession matters) and `unanswerable` (does the system abstain?). Abstention is the failure mode that matters most in law, and you cannot measure it without questions the corpus doesn't cover. |

Schema and every validation rule: `src/eval/goldset.py`.

---

## Judge validation workflow

```bash
python scripts/validate_judge.py sample --n 50     # writes blank label file
#  ... label them by hand, BEFORE looking at what the judge said ...
python scripts/validate_judge.py score --judge nli
```

Output includes Cohen's kappa, per-label precision/recall, the five most
interesting disagreements, and a blunt verdict:

```
verdict: NOT USABLE — fix the rubric or drop judged metrics from your table
```

If you can get a second person to label 20 of the same examples, the script also
reports inter-human Krippendorff's alpha. That is the **ceiling**: if two humans
only agree at 0.6, a judge at 0.6 is already at the noise floor and chasing a
higher number is wasted effort. Saying that in an interview is worth more than
any number in the table.

---

## Results table format

`make eval` generates `RESULTS.md`:

| Pipeline variant | recall@5 | mrr | ndcg@10 | p95 latency | vs baseline |
|---|---|---|---|---|---|
| Dense only | 0.712<br><sub>[0.655, 0.768]</sub> | ... | ... | 41 | _baseline_ |
| Hybrid (RRF) | 0.781<br><sub>[0.728, 0.833]</sub> | ... | ... | 68 | +0.069, p=0.002, sig: **yes** |
| Hybrid + reranker | 0.804<br><sub>[0.754, 0.854]</sub> | ... | ... | 447 | +0.092, p=0.001, sig: **yes** |
| + query rewriting | 0.809<br><sub>[0.759, 0.858]</sub> | ... | ... | 449 | +0.097, p=0.061, sig: no |

Two things to do with this table that most people don't:

- **Report a row that didn't help.** The ablation ladder includes score fusion
  and a recency boost precisely so you have honest negatives to show. "Score
  fusion was worse than RRF because BM25 and cosine scores aren't commensurable"
  is a better interview answer than any win.
- **Report Recall@candidates.** If Recall@50 is 0.79, no reranker will ever get
  you past 0.79. The reranker's ceiling is the retriever's recall, and stating
  that ceiling shows you understand the two-stage design.

---

## Layout

```
src/eval/          ← the project
  metrics.py       recall@k, MRR, nDCG, MAP — every formula tested by hand
  stats.py         bootstrap CI, paired permutation test, Holm-Bonferroni
  agreement.py     Cohen's kappa, Krippendorff's alpha
  judge.py         heuristic / NLI / local-LLM judges + rubric
  goldset.py       schema and the validation rules that stop self-deception
  run_eval.py      ablation runner -> RESULTS.md
src/index/         chunking (3 strategies), BM25 (own impl), embedders, build
src/retrieve/      fusion, reranking, query rewriting, supersession/recency
src/ingest/        CBIC scraper (rate-limited, cached), PDF extraction taxonomy
src/serve/         FastAPI + traced retrieval + status-labelled citations
frontend/          React + Vite + TypeScript + Tailwind UI, served by src/serve/
tests/             117 tests, all offline
```

## Test suite

```
tests/test_metrics.py            24  every metric vs a hand-computed value
tests/test_stats_and_agreement.py 25  CIs, permutation tests, kappa properties
tests/test_pipeline.py            38  tokenizer, BM25, fusion, chunking, e2e, as_of
tests/test_eval_harness.py        25  gold-set guardrails, ablation, judges
tests/test_serve.py               5  request helpers, warnings, route precedence
```

The tests worth reading first, because they encode the ideas:

- `test_ndcg_ideal_uses_all_relevant_not_just_retrieved` — the nDCG bug that
  makes a pipeline that misses everything look perfect.
- `test_kappa_zero_for_degenerate_always_yes_judge` — why raw agreement lies.
- `test_tiny_improvement_on_small_n_is_not_significant` — the whole thesis.
- `test_holm_bonferroni_is_stricter_than_raw_alpha` — five variants at p=0.04
  each, none survive correction.

## Data and licence

CBIC circulars and notifications are Government of India publications, fetched
from cbic.gov.in and redistributed here only as derived indices, not as bulk
copies. Check `robots.txt` before crawling and keep the 2s delay. This is a
research project and is **not legal advice**.

Code: MIT.
