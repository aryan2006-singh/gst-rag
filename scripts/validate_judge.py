"""Validate an automatic judge against your own human labels.

This is the step that turns "my RAG scores 0.82 faithfulness" from a vibe into a
claim. Workflow:

  1. `python scripts/validate_judge.py sample --n 50`
     Samples answers from a run and writes `data/gold/human_labels.jsonl` with
     the judgement fields blank.

  2. Label them yourself. Read the question, the retrieved context, and the
     answer, then set "faithful" and "correct" to true/false. Budget an hour.
     Do this before you look at what the judge said — knowing the judge's answer
     contaminates your label, and the contamination inflates your kappa.

  3. `python scripts/validate_judge.py score`
     Runs the judge over the same examples and reports Cohen's kappa.

Report the kappa next to every judged metric in your README. If it comes out
below 0.4, say so and either fix the rubric or drop the judged metrics — a
faithfulness number from an unvalidated judge is worse than no number, because
it looks rigorous.

A useful extra: get a second person to label 20 of the same examples and report
inter-human agreement too. If two humans only reach 0.6, your judge at 0.6 is at
the ceiling, and that context is what makes the number interpretable.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.agreement import evaluate_judge, krippendorff_alpha_nominal

DEFAULT_PATH = "data/gold/human_labels.jsonl"


@dataclass
class LabelRecord:
    example_id: str
    question: str
    answer: str
    contexts: list[str]
    reference_answer: str | None = None
    # Human labels — fill these in by hand. null means "not yet labelled".
    faithful: bool | None = None
    correct: bool | None = None
    labeller: str = ""
    second_faithful: bool | None = None  # optional second annotator
    notes: str = ""
    # Filled by `score`, never by hand.
    judge_faithful: bool | None = None
    judge_correct: bool | None = None
    judge_rationale: str = ""


def cmd_sample(args: argparse.Namespace) -> None:
    source = Path(args.answers)
    if not source.exists():
        raise SystemExit(
            f"{source} not found. Produce it first by running your pipeline over "
            f"the gold set and dumping {{question, answer, contexts}} per line."
        )

    records = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    rng = random.Random(args.seed)
    rng.shuffle(records)
    sampled = records[: args.n]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        for index, record in enumerate(sampled):
            label = LabelRecord(
                example_id=record.get("question_id", f"ex{index}"),
                question=record["question"],
                answer=record["answer"],
                contexts=record.get("contexts", []),
                reference_answer=record.get("reference_answer"),
            )
            handle.write(json.dumps(label.__dict__, ensure_ascii=False) + "\n")

    print(f"wrote {len(sampled)} unlabelled examples to {out}")
    print("Now open it and set 'faithful' and 'correct' on each line.")
    print("Do NOT run `score` first — seeing the judge's answer will bias your labels.")


def cmd_score(args: argparse.Namespace) -> None:
    path = Path(args.labels)
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    labelled = [r for r in records if r.get("faithful") is not None]
    if len(labelled) < 30:
        print(
            f"WARNING: only {len(labelled)} labelled examples. A kappa on fewer "
            f"than ~30 is too noisy to mean much; aim for 50."
        )
    if not labelled:
        raise SystemExit("no labelled examples; fill in 'faithful' first")

    judge = build_judge(args.judge)
    print(f"judge: {judge.name}\n")

    for record in labelled:
        judgment = judge.judge(
            record["question"],
            record["answer"],
            record.get("contexts", []),
            record.get("reference_answer"),
        )
        record["judge_faithful"] = judgment.faithful
        record["judge_correct"] = judgment.correct
        record["judge_rationale"] = judgment.rationale

    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("=== FAITHFULNESS ===")
    report = evaluate_judge(
        [r["faithful"] for r in labelled], [r["judge_faithful"] for r in labelled]
    )
    print(report)
    print()

    with_correct = [r for r in labelled if r.get("correct") is not None]
    if with_correct:
        print("=== CORRECTNESS ===")
        print(
            evaluate_judge(
                [r["correct"] for r in with_correct],
                [r["judge_correct"] for r in with_correct],
            )
        )
        print()

    second = [r for r in labelled if r.get("second_faithful") is not None]
    if len(second) >= 10:
        alpha = krippendorff_alpha_nominal(
            [[r["faithful"], r["second_faithful"]] for r in second]
        )
        print(f"=== INTER-HUMAN (n={len(second)}) ===")
        print(f"Krippendorff's alpha = {alpha:.3f}")
        print(
            "This is the ceiling. A judge cannot meaningfully exceed the "
            "agreement two humans achieve on the same task."
        )
        print()

    print("--- disagreements worth reading ---")
    shown = 0
    for record in labelled:
        if record["faithful"] != record["judge_faithful"] and shown < 5:
            shown += 1
            print(f"\n[{record['example_id']}] human={record['faithful']} "
                  f"judge={record['judge_faithful']}")
            print(f"  Q: {record['question'][:110]}")
            print(f"  A: {record['answer'][:160]}")
            print(f"  judge said: {record['judge_rationale'][:160]}")

    verdict = (
        "USABLE — report the kappa alongside every judged metric"
        if report.trustworthy
        else "NOT USABLE — fix the rubric or drop judged metrics from your table"
    )
    print(f"\nverdict: {verdict}")


def build_judge(kind: str):
    from src.eval.judge import HeuristicJudge, NLIJudge

    if kind == "heuristic":
        return HeuristicJudge()
    if kind == "nli":
        return NLIJudge()
    if kind == "llm":
        raise SystemExit(
            "wire your local generator into LocalLLMJudge and add it here; "
            "see src/eval/judge.py"
        )
    raise SystemExit(f"unknown judge {kind!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sampler = sub.add_parser("sample", help="draw examples for human labelling")
    sampler.add_argument("--answers", default="results/answers.jsonl")
    sampler.add_argument("--n", type=int, default=50)
    sampler.add_argument("--seed", type=int, default=0)
    sampler.add_argument("--out", default=DEFAULT_PATH)
    sampler.set_defaults(func=cmd_sample)

    scorer = sub.add_parser("score", help="compare judge against human labels")
    scorer.add_argument("--labels", default=DEFAULT_PATH)
    scorer.add_argument("--judge", default="heuristic", choices=["heuristic", "nli", "llm"])
    scorer.set_defaults(func=cmd_score)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
