"""Local-PDF ingest: manifest building, identifiers and header-date inference.

No real PDFs are parsed here: `build_manifest` only looks at file names and the
sidecar, so empty placeholder files are enough. Offline.
"""

from __future__ import annotations

import gzip
import json

import pytest

from src.index.build import load_documents
from src.ingest.cbic_scraper import extract_identifier, make_doc_id
from src.ingest.local_pdfs import build_manifest, guess_doc_type, local_doc_id
from src.ingest.run_extract import infer_published


# ---------------------------------------------------------------- identifiers
def test_gst_circular_identifier_keeps_its_serial_number():
    # Used to come back as "23/2024-GST", which drops the 229 and collides
    # with every other circular in series 23.
    assert extract_identifier("Circular No. 229/23/2024-GST") == "229/23/2024-GST"
    assert extract_identifier("Circular No. 229/23 /2024-GST") == "229/23/2024-GST"


def test_older_identifier_forms_still_parse():
    assert extract_identifier("Circular 183/15/2022-GST") == "183/15/2022-GST"
    assert extract_identifier("Notification 13/2017-CT(R)") == "13/2017-CT(R)"


def test_distinct_circulars_get_distinct_doc_ids():
    a = make_doc_id("circular", "Circular No. 230/24/2024-GST", "u1")
    b = make_doc_id("circular", "Circular No. 330/24/2024-GST", "u2")
    assert a == "circular-230-24-2024-gst"
    assert a != b


# ------------------------------------------------------------------- doc type
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("circular-231.pdf", "circular"),
        ("cir-cgst-246-03-2025.pdf", "circular"),
        ("corrigendum-Circular-237-31-2024-GST.pdf", "corrigendum"),
        ("notfctn-3-central-tax-english.pdf", "notification"),
        ("ins-gst-02-2025.pdf", "instruction"),
        ("faq-manual/faqs-registration.pdf", "faq"),
        ("itc-rules-17052017.pdf", "rules"),
        ("CGST-Amendment-Act-2023.pdf", "act"),
        ("something-else.pdf", "other"),
    ],
)
def test_guess_doc_type_from_filename(name, expected):
    assert guess_doc_type(name) == expected


def test_local_doc_id_is_readable_without_an_identifier():
    assert local_doc_id("rules", "CGST Rules, 2017", "u") == "rules-cgst-rules-2017"
    assert local_doc_id("rules", "Rules", "u") == "rules"
    assert local_doc_id("circular", "Circular No. 231/25/2024-GST: ITC", "u") == (
        "circular-231-25-2024-gst"
    )


# ------------------------------------------------------------------- manifest
def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n")


def test_manifest_uses_sidecar_over_filename(tmp_path):
    touch(tmp_path / "circular-231.pdf")
    touch(tmp_path / "faq-manual" / "faqs-registration.pdf")
    (tmp_path / "sources.jsonl").write_text(
        json.dumps(
            {
                "file": "circular-231.pdf",
                "url": "https://example.gov.in/circular-231.pdf",
                "title": "Circular No. 231/25/2024-GST: ITC on demo vehicles",
                "doc_type": "circular",
                "published": "2024-09-10",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    docs = {d.local_path.replace("\\", "/").split(str(tmp_path).replace("\\", "/") + "/")[1]: d
            for d in build_manifest(tmp_path)}

    circular = docs["circular-231.pdf"]
    assert circular.doc_id == "circular-231-25-2024-gst"
    assert circular.notification_id == "231/25/2024-GST"
    assert circular.published == "2024-09-10"
    assert circular.url.startswith("https://")

    faq = docs["faq-manual/faqs-registration.pdf"]
    assert faq.doc_type == "faq"
    assert faq.title == "faqs registration"
    assert faq.url == "file://faq-manual/faqs-registration.pdf"
    assert faq.published is None


def test_manifest_doc_ids_are_unique(tmp_path):
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "b.pdf")
    (tmp_path / "sources.jsonl").write_text(
        "\n".join(
            json.dumps({"file": f, "title": "Circular No. 237/31/2024-GST"})
            for f in ("a.pdf", "b.pdf")
        ),
        encoding="utf-8",
    )
    ids = [d.doc_id for d in build_manifest(tmp_path)]
    assert len(ids) == len(set(ids)) == 2


def test_manifest_rejects_bad_sidecar(tmp_path):
    touch(tmp_path / "a.pdf")
    (tmp_path / "sources.jsonl").write_text('{"title": "no file key"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'file'"):
        build_manifest(tmp_path)


def test_manifest_requires_a_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_manifest(tmp_path / "missing")


# ------------------------------------------------------------ published dates
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Circular No. 230/24/2024-GST ... dated the 10<sup>th</sup> September, 2024", "2024-09-10"),
        ("**North Block, New Delhi Date: 15**<sup>**th**</sup> **July, 2024**", "2024-07-15"),
        ("New Delhi, the 27th March, 2025. G.S.R...", "2025-03-27"),
        ("Dated the 28<sup>th</sup> of January, 2025", "2025-01-28"),
        ("New Delhi, Dated - 09-06-2025. Subject", "2025-06-09"),
        ("Dated: 24th Sept, 2025", "2025-09-24"),
    ],
)
def test_infer_published_from_header(header, expected):
    assert infer_published(header) == expected


def test_infer_published_prefers_the_issue_date_over_cited_dates():
    header = (
        "Circular No. 249/06/2025-GST New Delhi, Dated - 09-06-2025. Attention is "
        "invited to Circular No. 122/41/2019-GST dated 05<sup>th</sup> November 2019"
    )
    assert infer_published(header) == "2025-06-09"


def test_infer_published_ignores_the_body_and_bad_dates():
    assert infer_published("x" * 2000 + " dated 1st January, 2020") is None
    assert infer_published("dated 31st February, 2024") is None
    assert infer_published("no dates here") is None


# --------------------------------------------------------------- corpus file
def test_load_documents_reads_gzip(tmp_path):
    path = tmp_path / "docs.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"doc_id": "d1", "text": "hello", "published": "2024-01-01"}) + "\n")
    assert load_documents(path) == [("d1", "hello", {"published": "2024-01-01"})]


def test_committed_starter_corpus_is_well_formed():
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "corpus" / "cbic_gst_starter.documents.jsonl.gz"
    if not path.exists():
        pytest.skip("starter corpus not present")
    docs = load_documents(path)
    ids = [doc_id for doc_id, _, _ in docs]
    assert len(docs) >= 30
    assert len(ids) == len(set(ids))
    assert all(len(text.split()) >= 50 for _, text, _ in docs)
    assert all(meta.get("url", "").startswith("https://cbic-gst.gov.in/") for _, _, meta in docs)
