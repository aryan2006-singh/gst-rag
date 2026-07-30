"""The ablation runner: pipelines x gold set -> the results table.

What makes this different from `for variant in variants: print(recall)`:

  * Every variant runs on the *same* index, the *same* questions, in the same
    process. Nothing is comparable otherwise.
  * Per-question scores are kept, not just means, so we can run paired
    significance tests between rows.
  * Every non-baseline row is tested against the baseline with a paired
    permutation test and Holm-Bonferroni correction across the family.
  * Latency percentiles are measured per stage, so "the reranker bought 4 points
    of recall for 380ms" is a sentence you can actually write.
  * Results serialise to JSON, and the markdown table is generated from that
    JSON — so the table in your README is reproducible rather than typed.

    python -m src.eval.run_eval --index data/index --gold data/gold/gold_set.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.eval import metrics as M
from src.eval.goldset import GoldQuestion, load_gold_set, validate_gold_set
from src.eval.stats import Comparison, bootstrap_ci, compare, holm_bonferroni
from src.retrieve.pipeline import PipelineConfig, RetrievalPipeline

REPORT_METRICS = ["recall@5", "recall@10", "recall@20", "mrr", "ndcg@10", "map"]


@dataclass
class VariantResult:
    name: str
    config: dict
    n_questions: int
    means: dict[str, float]
    cis: dict[str, tuple[float, float]]
    per_question: dict[str, list[float]] = field(default_factory=dict)
    latency_ms: dict[str, float] = field(default_factory=dict)
    stage_latency_ms: dict[str, float] = field(default_factory=dict)
    comparison: dict | None = None

    def summary_line(self) -> str:
        parts = [f"{name}={self.means[name]:.3f}" for name in REPORT_METRICS if name in self.means]
        return f"{self.name:<32} " + "  ".join(parts)


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    low, high = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)


def evaluate_variant(
    pipeline: RetrievalPipeline,
    config: PipelineConfig,
    questions: Sequence[GoldQuestion],
    top_k: int = 20,
) -> VariantResult:
    variant = pipeline.with_config(config)

    per_question: dict[str, list[float]] = {name: [] for name in REPORT_METRICS}
    latencies: list[float] = []
    stage_totals: dict[str, list[float]] = {}
    scored = 0

    for question in questions:
        if not question.is_answerable:
            continue
        start = time.perf_counter()
        result = variant.search(question.question, top_k=top_k)
        latencies.append((time.perf_counter() - start) * 1000)
        for stage, value in result.latency_ms.items():
            stage_totals.setdefault(stage, []).append(value)

        scores = M.score_one(result.ranked_ids, question.relevance(), REPORT_METRICS)
        if not scores:
            continue
        scored += 1
        for name in REPORT_METRICS:
            per_question[name].append(scores[name])

    means = {name: statistics.fmean(values) for name, values in per_question.items() if values}
    cis = {}
    for name, values in per_question.items():
        if values:
            interval = bootstrap_ci(values, iterations=2000)
            cis[name] = (interval.low, interval.high)

    return VariantResult(
        name=config.name,
        config=asdict(config),
        n_questions=scored,
        means=means,
        cis=cis,
        per_question=per_question,
        latency_ms={
            "p50": round(percentile(latencies, 0.5), 1),
            "p95": round(percentile(latencies, 0.95), 1),
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        },
        stage_latency_ms={
            stage: round(statistics.fmean(values), 2)
            for stage, values in sorted(stage_totals.items())
        },
    )


def run_ablation(
    pipeline: RetrievalPipeline,
    configs: Sequence[PipelineConfig],
    questions: Sequence[GoldQuestion],
    primary_metric: str = "recall@5",
    baseline_name: str | None = None,
    top_k: int = 20,
) -> list[VariantResult]:
    results = [evaluate_variant(pipeline, config, questions, top_k) for config in configs]
    if not results:
        return results

    baseline = next(
        (r for r in results if r.name == baseline_name), results[0]
    )
    base_scores = baseline.per_question.get(primary_metric, [])

    raw_p: dict[str, float] = {}
    comparisons: dict[str, Comparison] = {}
    for result in results:
        if result is baseline:
            continue
        variant_scores = result.per_question.get(primary_metric, [])
        if len(variant_scores) != len(base_scores) or not base_scores:
            continue
        comparison = compare(base_scores, variant_scores, iterations=5000)
        comparisons[result.name] = comparison
        raw_p[result.name] = comparison.p_value

    corrected = holm_bonferroni(raw_p) if raw_p else {}
    for result in results:
        comparison = comparisons.get(result.name)
        if comparison is None:
            continue
        result.comparison = {
            "vs": baseline.name,
            "metric": primary_metric,
            "delta": round(comparison.delta, 4),
            "ci": [round(comparison.delta_ci.low, 4), round(comparison.delta_ci.high, 4)],
            "p_value": round(comparison.p_value, 5),
            "significant_raw": comparison.significant,
            "significant_holm": corrected.get(result.name, False),
        }
    return results


# --------------------------------------------------------------------------- #
#  Reporting
# --------------------------------------------------------------------------- #

def to_markdown(
    results: Sequence[VariantResult],
    primary_metric: str = "recall@5",
    title: str = "Retrieval ablation",
) -> str:
    header = (
        "| Pipeline variant | "
        + " | ".join(REPORT_METRICS)
        + " | p95 latency (ms) | vs baseline |"
    )
    divider = "|" + "|".join(["---"] * (len(REPORT_METRICS) + 3)) + "|"

    rows = []
    for result in results:
        cells = [result.name]
        for name in REPORT_METRICS:
            mean = result.means.get(name)
            if mean is None:
                cells.append("—")
                continue
            low, high = result.cis.get(name, (float("nan"), float("nan")))
            cells.append(f"{mean:.3f}<br><sub>[{low:.3f}, {high:.3f}]</sub>")
        cells.append(f"{result.latency_ms.get('p95', 0):.0f}")

        comparison = result.comparison
        if comparison is None:
            cells.append("_baseline_")
        else:
            mark = "**yes**" if comparison["significant_holm"] else "no"
            cells.append(
                f"{comparison['delta']:+.3f}, p={comparison['p_value']:.3f}, sig: {mark}"
            )
        rows.append("| " + " | ".join(cells) + " |")

    n = results[0].n_questions if results else 0
    return f"""## {title}

n = {n} answerable gold questions. Values are macro-averaged with 95% bootstrap
confidence intervals. Significance is a paired permutation test on
`{primary_metric}` against the baseline row, Holm-Bonferroni corrected across
{max(len(results) - 1, 0)} comparisons.

{header}
{divider}
{chr(10).join(rows)}

**How to read this.** A row whose CI overlaps the baseline's CI is not an
improvement, no matter what the point estimate says. The "vs baseline" column is
the one that matters: an unsignificant +0.02 is noise, and reporting it as a win
is the most common way RAG projects overstate their results.
"""


def stage_latency_table(results: Sequence[VariantResult]) -> str:
    stages = sorted({s for r in results for s in r.stage_latency_ms})
    if not stages:
        return ""
    header = "| Variant | " + " | ".join(stages) + " | total |"
    divider = "|" + "|".join(["---"] * (len(stages) + 2)) + "|"
    rows = []
    for result in results:
        values = [result.stage_latency_ms.get(stage, 0.0) for stage in stages]
        cells = [result.name] + [f"{v:.1f}" for v in values] + [f"{sum(values):.1f}"]
        rows.append("| " + " | ".join(cells) + " |")
    return "## Mean latency by stage (ms)\n\n" + header + "\n" + divider + "\n" + "\n".join(rows)


def save_results(results: Sequence[VariantResult], path: str | Path) -> None:
    payload = []
    for result in results:
        record = asdict(result)
        # Per-question vectors are large; keep them, they are what makes the
        # significance tests reproducible without rerunning retrieval.
        payload.append(record)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="run the retrieval ablation")
    parser.add_argument("--index", default="data/index", help="directory from build.py")
    parser.add_argument("--gold", default="data/gold/gold_set.jsonl")
    parser.add_argument("--split", default="test", choices=["dev", "test", "all"])
    parser.add_argument("--primary-metric", default="recall@5")
    parser.add_argument("--baseline", default="Dense only")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--out-json", default="results/ablation.json")
    parser.add_argument("--out-md", default="RESULTS.md")
    parser.add_argument("--embedder", default="sentence-transformers")
    parser.add_argument("--no-rerank", action="store_true")
    args = parser.parse_args()

    from src.index.build import load_index
    from src.retrieve.pipeline import ABLATION_LADDER
    from src.retrieve.query_rewrite import rewrite

    chunks, embeddings, embedder = load_index(args.index, embedder_kind=args.embedder)

    reranker = None
    if not args.no_rerank:
        from src.retrieve.rerank import CrossEncoderReranker

        reranker = CrossEncoderReranker()

    questions = load_gold_set(args.gold)
    report = validate_gold_set(questions, known_chunk_ids=[c.chunk_id for c in chunks])
    print(report)
    if not report.ok:
        raise SystemExit("gold set validation failed; fix the errors above")

    if args.split != "all":
        questions = [q for q in questions if q.split == args.split]
    print(f"\nevaluating on {len(questions)} '{args.split}' questions\n")

    pipeline = RetrievalPipeline(
        chunks=chunks,
        embedder=embedder,
        config=ABLATION_LADDER[0],
        reranker=reranker,
        query_rewriter=rewrite,
        embeddings=embeddings,
    )

    configs = [c for c in ABLATION_LADDER if reranker is not None or not c.rerank]
    results = run_ablation(
        pipeline,
        configs,
        questions,
        primary_metric=args.primary_metric,
        baseline_name=args.baseline,
        top_k=args.top_k,
    )

    for result in results:
        print(result.summary_line())

    save_results(results, args.out_json)
    markdown = to_markdown(results, args.primary_metric) + "\n\n" + stage_latency_table(results)
    Path(args.out_md).write_text(markdown, encoding="utf-8")
    print(f"\nwrote {args.out_json} and {args.out_md}")


if __name__ == "__main__":
    main()
