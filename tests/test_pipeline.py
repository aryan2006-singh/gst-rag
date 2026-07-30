"""End-to-end pipeline tests on the fixture corpus. Offline, no downloads."""

from __future__ import annotations

import os
import sys
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.index.bm25 import BM25, tokenize  # noqa: E402
from src.index.chunking import chunk_corpus, fixed_window, section_aware, split_sentences  # noqa: E402
from src.index.embedders import HashingEmbedder  # noqa: E402
from src.retrieve.fusion import reciprocal_rank_fusion, score_fusion  # noqa: E402
from src.retrieve.pipeline import ABLATION_LADDER, PipelineConfig, RetrievalPipeline  # noqa: E402
from src.retrieve.query_rewrite import expand_acronyms, normalize_citations, rewrite  # noqa: E402
from src.retrieve.recency import (  # noqa: E402
    SupersessionGraph,
    build_supersession_graph,
    filter_as_of,
    normalize_notification_id,
)
from src.retrieve.rerank import StubReranker  # noqa: E402
from tests.fixtures import DOCUMENTS, gold_questions  # noqa: E402


# ------------------------------------------------------------------ tokenizer
def test_tokenizer_keeps_section_references_intact():
    tokens = tokenize("credit under section 16(2)(c) is denied")
    assert "16(2)(c)" in tokens


def test_tokenizer_keeps_notification_numbers_intact():
    tokens = tokenize("see Notification 13/2017-CT(R) for rates")
    assert "13/2017-ct(r)" in tokens


def test_tokenizer_keeps_negations():
    """'not' carries meaning in statutory text; the usual stop list would drop it."""
    assert "not" in tokenize("shall not be entitled to credit")


# ----------------------------------------------------------------------- BM25
def test_bm25_idf_is_non_negative_for_common_terms():
    corpus = [["tax"] * 3 for _ in range(10)]
    index = BM25(corpus, [f"d{i}" for i in range(10)])
    # Present in 100% of documents; without the +1 correction this goes negative
    # and matching the term would *hurt* a document's score.
    assert index.idf("tax") >= 0


def test_bm25_prefers_rarer_term():
    corpus = [tokenize(t) for t in ["tax credit", "tax refund", "tax invoice", "tax cess"]]
    index = BM25(corpus, ["a", "b", "c", "d"])
    assert index.idf("cess") > index.idf("tax")


def test_bm25_length_normalisation_penalises_padding():
    short = tokenize("input tax credit")
    padded = short + tokenize("filler " * 200)
    index = BM25([short, padded], ["short", "long"])
    scores = index.score_all(tokenize("input tax credit"))
    assert scores["short"] > scores["long"]


def test_bm25_unknown_term_scores_nothing():
    index = BM25([tokenize("input tax credit")], ["a"])
    assert index.score_all(tokenize("zzzznotaword")) == {}


# --------------------------------------------------------------------- fusion
def test_rrf_rewards_appearing_in_both_lists():
    bm25 = [("x", 9.0), ("y", 4.0)]
    dense = [("y", 0.9), ("z", 0.8)]
    fused = reciprocal_rank_fusion({"bm25": bm25, "dense": dense}, k=0)
    assert [doc for doc, _ in fused][0] == "y"


def test_rrf_ignores_score_magnitude():
    """The property that makes RRF the right default: BM25's 900.0 and cosine's
    0.9 are not comparable, and RRF never compares them."""
    a = [("x", 900.0), ("y", 1.0)]
    b = [("x", 0.9), ("y", 0.001)]
    assert reciprocal_rank_fusion({"a": a}, k=60) == reciprocal_rank_fusion({"b": b}, k=60)


def test_rrf_weights_shift_the_order():
    bm25 = [("x", 1.0)]
    dense = [("y", 1.0)]
    biased = reciprocal_rank_fusion(
        {"bm25": bm25, "dense": dense}, k=60, weights={"bm25": 5.0, "dense": 1.0}
    )
    assert biased[0][0] == "x"


def test_score_fusion_normalises_per_retriever():
    fused = score_fusion({"a": [("x", 100.0), ("y", 0.0)], "b": [("y", 1.0), ("x", 0.0)]})
    assert dict(fused)["x"] == pytest.approx(1.0)
    assert dict(fused)["y"] == pytest.approx(1.0)


def test_empty_ranking_is_harmless():
    assert reciprocal_rank_fusion({"a": [], "b": []}) == []


# ------------------------------------------------------------------- chunking
def test_fixed_window_overlap():
    text = " ".join(str(i) for i in range(100))
    chunks = fixed_window(text, "d", size=30, overlap=10)
    assert chunks[0].text.split()[20] == chunks[1].text.split()[0]


def test_fixed_window_rejects_overlap_ge_size():
    with pytest.raises(ValueError):
        fixed_window("a b c", "d", size=10, overlap=10)


def test_section_aware_splits_on_section_numbers():
    text = "16. Eligibility for credit. Text here.\n17. Blocked credits. More text."
    chunks = section_aware(text, "act")
    assert len(chunks) == 2
    assert chunks[0].metadata["section"] == "16"
    assert chunks[1].metadata["section"] == "17"


def test_section_aware_falls_back_when_no_sections():
    chunks = section_aware("just some prose with no numbering at all", "d")
    assert len(chunks) >= 1
    assert chunks[0].metadata["strategy"] == "fixed"


def test_section_header_repeated_in_split_fragments():
    """A long section split into fragments must keep its citable number in each."""
    body = "16. Eligibility. " + " ".join(["word"] * 900)
    chunks = section_aware(body, "act", max_words=100)
    assert len(chunks) > 1
    assert all("Section 16" in c.text or c.text.startswith("16.") for c in chunks)


def test_sentence_splitter_survives_legal_abbreviations():
    sentences = split_sentences("See Notification No. 13/2017. It was amended later.")
    assert len(sentences) == 2
    assert "No. 13/2017" in sentences[0]


def test_chunk_corpus_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        chunk_corpus(DOCUMENTS, "nonexistent")


# ------------------------------------------------------------- query rewriting
def test_acronym_expansion_keeps_the_original():
    out = expand_acronyms("can I claim ITC")
    assert "ITC" in out and "input tax credit" in out


def test_citation_normalisation():
    assert "section 16" in normalize_citations("what does sec 16 say")
    assert "rule 42" in normalize_citations("Rule 42 reversal")


def test_rewrite_is_idempotent_enough_to_be_safe():
    once = rewrite("ITC on hotel")
    twice = rewrite(once)
    # Expansions are not re-added once present.
    assert twice.count("input tax credit") == once.count("input tax credit")


# ------------------------------------------------------------- supersession
def test_notification_id_normalisation():
    assert normalize_notification_id("13/2017 - CT (R)") == normalize_notification_id(
        "13/2017-CT(R)"
    )


def test_supersession_graph_detects_amendment():
    graph = build_supersession_graph(
        [(doc_id, text) for doc_id, text, _ in DOCUMENTS]
    )
    assert graph.status("11/2017-CT(R)") in ("amended", "superseded")
    assert graph.status("99/2099-CT(R)") == "in_force"


def test_supersession_graph_records_successor():
    graph = SupersessionGraph()
    graph.add_from_text(
        "notif-20-2019",
        "Seeks to amend Notification No. 11/2017-CT(R) so as to revise rates.",
    )
    assert "notif-20-2019" in graph.successors("11/2017-CT(R)")


def test_as_of_filter_drops_future_documents():
    from datetime import date

    class FakeChunk:
        def __init__(self, published):
            self.metadata = {"published": published}

    chunks = {"old": FakeChunk("2017-06-28"), "new": FakeChunk("2019-09-30")}
    kept = filter_as_of([("old", 1.0), ("new", 2.0)], chunks, as_of=date(2018, 1, 1))
    assert [doc for doc, _ in kept] == ["old"]


# ----------------------------------------------------------- end-to-end search
@pytest.fixture(scope="module")
def pipeline():
    chunks = chunk_corpus(DOCUMENTS, "section")
    embedder = HashingEmbedder(dim=256)
    return RetrievalPipeline(
        chunks=chunks,
        embedder=embedder,
        config=ABLATION_LADDER[2],  # Hybrid (RRF)
        reranker=StubReranker(),
        query_rewriter=rewrite,
    )


def test_pipeline_returns_requested_number_of_hits(pipeline):
    result = pipeline.search("input tax credit time limit", top_k=5)
    assert len(result.hits) == 5
    assert len(set(result.ranked_ids)) == 5


def test_pipeline_finds_the_obvious_answer(pipeline):
    result = pipeline.search("interest on delayed payment of tax", top_k=3)
    assert any("s50" in chunk_id for chunk_id in result.ranked_ids)


def test_pipeline_records_stage_latencies(pipeline):
    result = pipeline.search("late fee for late return", top_k=5)
    assert "bm25" in result.latency_ms and "dense" in result.latency_ms
    assert result.total_ms > 0


def test_every_ablation_variant_runs(pipeline):
    """The ablation is worthless if a variant crashes halfway through the sweep."""
    for config in ABLATION_LADDER:
        variant = pipeline.with_config(config)
        result = variant.search("can I claim ITC on hotel accommodation", top_k=10)
        assert result.hits, f"{config.name} returned nothing"
        assert len(result.ranked_ids) == len(set(result.ranked_ids))


def test_variants_share_the_index(pipeline):
    """with_config must not rebuild BM25 or re-embed — otherwise the sweep is
    both slow and no longer a controlled comparison."""
    variant = pipeline.with_config(ABLATION_LADDER[0])
    assert variant.bm25 is pipeline.bm25
    assert variant.embeddings is pipeline.embeddings


def test_bm25_only_and_dense_only_differ(pipeline):
    bm25_only = pipeline.with_config(replace(ABLATION_LADDER[0], top_k=10))
    dense_only = pipeline.with_config(replace(ABLATION_LADDER[1], top_k=10))
    query = "blocked credit motor vehicle"
    assert bm25_only.search(query).ranked_ids != dense_only.search(query).ranked_ids


def test_reranker_reorders_without_losing_candidates(pipeline):
    plain = pipeline.with_config(replace(ABLATION_LADDER[2], top_k=10))
    reranked = pipeline.with_config(replace(ABLATION_LADDER[4], top_k=10))
    query = "cancellation of registration notice"
    before = plain.search(query, top_k=20).ranked_ids
    after = reranked.search(query, top_k=20).ranked_ids
    assert set(after) == set(before), "reranking must not drop candidates"


def test_config_rejects_rerank_depth_below_top_k():
    with pytest.raises(ValueError):
        PipelineConfig(name="bad", rerank=True, rerank_depth=5, top_k=10)


def test_config_rejects_no_retriever():
    with pytest.raises(ValueError):
        PipelineConfig(name="bad", use_bm25=False, use_dense=False)


def test_gold_set_chunk_ids_exist_in_the_index(pipeline):
    """Catches the single most common gold-set bug: a chunk id that no longer
    exists after you changed the chunking strategy."""
    known = set(pipeline.by_id)
    for question in gold_questions():
        missing = [c for c in question.relevant_chunk_ids if c not in known]
        assert not missing, f"{question.question_id} references missing chunks: {missing}"


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
