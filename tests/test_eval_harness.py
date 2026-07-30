"""The eval harness end to end, plus the gold-set guardrails.

These tests are the reason the harness can be trusted: they check that the
validator actually blocks the ways you would otherwise fool yourself, and that
the ablation runner produces comparable, significance-tested output.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.eval.goldset import (  # noqa: E402
    GoldQuestion,
    load_gold_set,
    save_gold_set,
    validate_gold_set,
)
from src.eval.judge import HeuristicJudge, StubJudge, detect_abstention, split_claims  # noqa: E402
from src.eval.run_eval import (  # noqa: E402
    evaluate_variant,
    run_ablation,
    stage_latency_table,
    to_markdown,
)
from src.index.chunking import chunk_corpus  # noqa: E402
from src.index.embedders import HashingEmbedder  # noqa: E402
from src.retrieve.pipeline import ABLATION_LADDER, RetrievalPipeline  # noqa: E402
from src.retrieve.query_rewrite import rewrite  # noqa: E402
from src.retrieve.rerank import StubReranker  # noqa: E402
from tests.fixtures import DOCUMENTS, gold_questions  # noqa: E402


@pytest.fixture(scope="module")
def pipeline():
    return RetrievalPipeline(
        chunks=chunk_corpus(DOCUMENTS, "section"),
        embedder=HashingEmbedder(dim=256),
        config=ABLATION_LADDER[2],
        reranker=StubReranker(),
        query_rewriter=rewrite,
    )


# ------------------------------------------------------------ gold set schema
def test_valid_gold_set_passes():
    report = validate_gold_set(gold_questions(), min_questions=5)
    assert report.ok, report.errors


def test_missing_chunk_id_is_an_error():
    questions = gold_questions()
    report = validate_gold_set(questions, known_chunk_ids={"nothing-matches"}, min_questions=5)
    assert not report.ok
    assert any("not in index" in error for error in report.errors)


def test_too_many_llm_generated_questions_is_an_error():
    """Synthetic questions are paraphrases of chunks you already indexed, so a
    gold set dominated by them measures paraphrase matching, not retrieval."""
    questions = [
        GoldQuestion(f"q{i}", f"question number {i}", ["c1"], "llm_generated")
        for i in range(10)
    ]
    report = validate_gold_set(questions, min_questions=5)
    assert not report.ok
    assert any("llm_generated" in error for error in report.errors)


def test_duplicate_question_text_is_an_error():
    questions = [
        GoldQuestion("q1", "What is the GST rate?", ["c1"], "faq"),
        GoldQuestion("q2", "what is the gst rate", ["c2"], "faq"),
    ]
    report = validate_gold_set(questions, min_questions=1)
    assert not report.ok
    assert any("duplicate question text" in error for error in report.errors)


def test_answerable_question_needs_gold_chunks():
    questions = [GoldQuestion("q1", "anything", [], "faq")]
    report = validate_gold_set(questions, min_questions=1)
    assert any("no relevant_chunk_ids" in error for error in report.errors)


def test_unanswerable_question_must_not_have_gold_chunks():
    questions = [GoldQuestion("q1", "x", ["c1"], "faq", question_type="unanswerable")]
    report = validate_gold_set(questions, min_questions=1)
    assert any("should have no gold chunks" in error for error in report.errors)


def test_graded_relevance_must_reference_listed_chunks():
    questions = [
        GoldQuestion("q1", "x", ["c1"], "faq", graded_relevance={"c9": 2.0})
    ]
    report = validate_gold_set(questions, min_questions=1)
    assert any("not in relevant list" in error for error in report.errors)


def test_small_gold_set_warns_about_statistical_power():
    questions = [GoldQuestion(f"q{i}", f"q {i}", ["c1"], "faq") for i in range(20)]
    report = validate_gold_set(questions, min_questions=150)
    assert any("CI on Recall@5" in warning for warning in report.warnings)


def test_missing_test_split_warns():
    questions = [GoldQuestion(f"q{i}", f"q {i}", ["c1"], "faq", split="dev") for i in range(5)]
    report = validate_gold_set(questions, min_questions=1)
    assert any("no test split" in warning for warning in report.warnings)


def test_gold_set_roundtrips_through_disk(tmp_path):
    path = tmp_path / "gold.jsonl"
    save_gold_set(gold_questions(), path)
    reloaded = load_gold_set(path)
    assert [q.question_id for q in reloaded] == [q.question_id for q in gold_questions()]
    assert reloaded[8].graded_relevance  # q9 keeps its graded gains


# ------------------------------------------------------------------- ablation
def test_evaluate_variant_produces_metrics(pipeline):
    result = evaluate_variant(pipeline, ABLATION_LADDER[2], gold_questions())
    assert result.n_questions == 9  # 10 questions, one unanswerable
    assert 0.0 <= result.means["recall@5"] <= 1.0
    assert result.latency_ms["p95"] >= 0


def test_unanswerable_questions_are_excluded_from_scoring(pipeline):
    result = evaluate_variant(pipeline, ABLATION_LADDER[2], gold_questions())
    # q10 has no gold chunks; scoring it would drag every variant down equally
    # and mask real differences.
    assert result.n_questions == len([q for q in gold_questions() if q.is_answerable])


def test_ablation_runs_every_variant_and_compares(pipeline):
    results = run_ablation(
        pipeline, ABLATION_LADDER, gold_questions(), baseline_name="Dense only"
    )
    assert len(results) == len(ABLATION_LADDER)

    baseline = next(r for r in results if r.name == "Dense only")
    assert baseline.comparison is None

    others = [r for r in results if r.name != "Dense only"]
    assert all(r.comparison is not None for r in others)
    for result in others:
        assert "p_value" in result.comparison
        assert "significant_holm" in result.comparison


def test_all_variants_scored_the_same_questions(pipeline):
    """If variants disagree on n, the rows are not comparable and the paired
    tests are invalid."""
    results = run_ablation(pipeline, ABLATION_LADDER, gold_questions())
    assert len({r.n_questions for r in results}) == 1


def test_markdown_table_has_a_row_per_variant(pipeline):
    results = run_ablation(pipeline, ABLATION_LADDER, gold_questions())
    markdown = to_markdown(results)
    for result in results:
        assert result.name in markdown
    assert "_baseline_" in markdown
    assert "recall@5" in markdown


def test_stage_latency_table_lists_stages(pipeline):
    results = run_ablation(pipeline, ABLATION_LADDER[:3], gold_questions())
    table = stage_latency_table(results)
    assert "bm25" in table and "dense" in table


def test_results_serialise_to_json(pipeline, tmp_path):
    from src.eval.run_eval import save_results

    results = run_ablation(pipeline, ABLATION_LADDER[:3], gold_questions())
    path = tmp_path / "ablation.json"
    save_results(results, path)
    payload = json.loads(path.read_text())
    assert len(payload) == 3
    # Per-question vectors must survive so significance tests are reproducible
    # without rerunning retrieval.
    assert payload[0]["per_question"]["recall@5"]


def test_identical_configs_produce_identical_scores(pipeline):
    """Determinism check. If two runs of the same config differ, every delta in
    the table is partly noise from the pipeline itself."""
    config = replace(ABLATION_LADDER[2], name="dup")
    first = evaluate_variant(pipeline, config, gold_questions())
    second = evaluate_variant(pipeline, config, gold_questions())
    assert first.per_question == second.per_question


# ---------------------------------------------------------------------- judge
def test_abstention_detected():
    assert detect_abstention("I don't know based on the provided context.")
    assert not detect_abstention("The rate is 12 per cent.")


def test_split_claims_drops_fragments():
    claims = split_claims("Yes. The rate of tax on such accommodation is twelve per cent.")
    assert len(claims) == 1


def test_heuristic_judge_flags_a_hallucinated_rate():
    judge = HeuristicJudge()
    contexts = ["The rate of central tax on such accommodation shall be twelve per cent."]
    result = judge.judge(
        "What is the rate?",
        "The applicable rate of central tax on such accommodation is 28 per cent.",
        contexts,
        reference="12 per cent",
    )
    assert not result.faithful
    assert result.unsupported_claims
    assert "ungrounded number" in result.unsupported_claims[0]


def test_heuristic_judge_accepts_a_grounded_answer():
    judge = HeuristicJudge()
    contexts = [
        "A registered person shall pay a late fee of one hundred rupees for every "
        "day subject to a maximum of five thousand rupees."
    ]
    result = judge.judge(
        "What is the late fee?",
        "A registered person shall pay a late fee of one hundred rupees for every day.",
        contexts,
        reference="one hundred rupees per day",
    )
    assert result.faithful
    assert result.faithfulness_score == pytest.approx(1.0)


def test_heuristic_judge_flags_a_hallucinated_section_citation():
    judge = HeuristicJudge()
    contexts = ["Input tax credit is governed by section 16 of the Act."]
    result = judge.judge(
        "Which section?",
        "This is governed by section 16 and also by section 99 of the Act.",
        contexts,
        reference=None,
    )
    assert not result.faithful


def test_judge_treats_abstention_as_faithful_but_not_correct():
    result = StubJudge().judge("q", "I don't know.", ["ctx"], reference="12%")
    assert result.abstained
    assert result.faithful
    assert not result.correct


def test_correctness_requires_matching_the_reference_number():
    judge = HeuristicJudge()
    contexts = ["The rate shall be 12 per cent and the threshold is 7500 rupees."]
    right = judge.judge("q", "The rate is 12 per cent.", contexts, reference="12 per cent")
    wrong = judge.judge("q", "The rate is 7500 per cent.", contexts, reference="12 per cent")
    assert right.correct
    assert not wrong.correct
