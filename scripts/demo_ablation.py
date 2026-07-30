"""Run the full ablation on the built-in fixture corpus. No downloads, no keys.

    python scripts/demo_ablation.py

This exists so a reader can clone the repo and see the machinery work in five
seconds, before committing to scraping CBIC and hand-labelling 250 questions.
The numbers are meaningless — 10 fixture questions and a hashing embedder — and
the script says so loudly, because a demo table quietly mistaken for a result is
worse than no demo at all.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.eval.goldset import validate_gold_set
from src.eval.run_eval import run_ablation, save_results, stage_latency_table, to_markdown
from src.index.chunking import chunk_corpus
from src.index.embedders import HashingEmbedder
from src.retrieve.pipeline import ABLATION_LADDER, RetrievalPipeline
from src.retrieve.query_rewrite import rewrite
from src.retrieve.rerank import StubReranker
from tests.fixtures import DOCUMENTS, gold_questions

BANNER = """
+---------------------------------------------------------------------------+
|  DEMO RUN — these numbers are NOT results.                                 |
|  10 synthetic questions, 10 fixture documents, a hashing embedder and a    |
|  Jaccard "reranker". Confidence intervals will be enormous and nothing     |
|  will be significant. That is the correct behaviour at n=9.                |
|  Replace with the real corpus and a 150-300 question gold set.             |
+---------------------------------------------------------------------------+
"""


def main() -> None:
    print(BANNER)

    questions = gold_questions()
    chunks = chunk_corpus(DOCUMENTS, "section")
    print(f"corpus: {len(DOCUMENTS)} documents -> {len(chunks)} chunks")

    report = validate_gold_set(
        questions, known_chunk_ids=[c.chunk_id for c in chunks], min_questions=150
    )
    print(report)
    if not report.ok:
        raise SystemExit("gold set validation failed")

    pipeline = RetrievalPipeline(
        chunks=chunks,
        embedder=HashingEmbedder(dim=256),
        config=ABLATION_LADDER[0],
        reranker=StubReranker(),
        query_rewriter=rewrite,
    )

    print("\nrunning ablation...\n")
    results = run_ablation(
        pipeline, ABLATION_LADDER, questions, primary_metric="recall@5",
        baseline_name="Dense only",
    )

    for result in results:
        print(result.summary_line())

    markdown = to_markdown(results, title="Retrieval ablation (DEMO — fixture corpus)")
    markdown += "\n\n" + stage_latency_table(results)

    Path("results").mkdir(exist_ok=True)
    Path("results/demo_ablation.md").write_text(markdown, encoding="utf-8")
    save_results(results, "results/demo_ablation.json")

    significant = [
        r.name for r in results if r.comparison and r.comparison["significant_holm"]
    ]
    print(f"\nsignificant improvements over baseline: {significant or 'none'}")
    print("(none is the expected answer at this sample size)")
    print("\nwrote results/demo_ablation.md and results/demo_ablation.json")


if __name__ == "__main__":
    main()
