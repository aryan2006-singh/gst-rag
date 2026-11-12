"""Batch PDF extraction -> documents.jsonl + a failure-mode report.

The report is a deliverable, not a log file. "83% of CBIC circulars extracted
cleanly; the remaining 17% were scanned pre-2018 notifications with no text
layer" is a concrete, specific thing to say about your corpus, and it is the
kind of detail that separates someone who has handled real documents from
someone who has run `PyPDFLoader` on three files.

    python -m src.ingest.run_extract --manifest data/raw/manifest.jsonl \
        --out data/processed/documents.jsonl --report results/extraction_report.md
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

from src.ingest.pdf_extract import ExtractionReport, extract
from src.retrieve.recency import build_supersession_graph

log = logging.getLogger(__name__)

MONTHS = {
    name: number
    for number, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
         ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
         ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
         ("dec", "december")],
        start=1,
    )
    for name in names
}

# "dated the 10th September, 2024", "Dated: 24th June, 2025", "New Delhi, the
# 27th March, 2025", "Dated - 09-06-2025". Only the document header is searched
# (see infer_published), because the body cites other documents' dates.
_DAY_MONTH_YEAR_RE = re.compile(
    r"(?:dated?|new delhi)\W{0,6}(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?"
    r"([a-z]{3,9})\.?,?\s+(\d{4})",
    re.IGNORECASE,
)
_NUMERIC_RE = re.compile(
    r"(?:dated?|new delhi)\W{0,6}(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", re.IGNORECASE
)


def infer_published(text: str, header_chars: int = 1500) -> str | None:
    """Issue date from a CBIC document header, as YYYY-MM-DD, or None.

    Fallback for documents whose manifest entry has no date (hand-downloaded
    PDFs, mostly). Without a date a document can't take part in as-of
    filtering or the recency boost, so a conservative guess from the header is
    worth having; anything that doesn't parse cleanly returns None.
    """
    header = re.sub(r"<[^>]+>|\*+", "", text[:header_chars])
    # The issue date comes first; later dates in the header are usually the
    # dates of earlier circulars being cited. So take the earliest match of
    # either form, not the first form that matches anywhere.
    candidates: list[tuple[int, str]] = []
    for match in _DAY_MONTH_YEAR_RE.finditer(header):
        day, month_name, year = match.groups()
        month = MONTHS.get(month_name.lower())
        iso = _iso(int(year), month, int(day)) if month else None
        if iso:
            candidates.append((match.start(), iso))
    for match in _NUMERIC_RE.finditer(header):
        day, month, year = (int(g) for g in match.groups())
        iso = _iso(year, month, day)
        if iso:
            candidates.append((match.start(), iso))
    return min(candidates)[1] if candidates else None


def _iso(year: int, month: int, day: int) -> str | None:
    from datetime import date

    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/raw/manifest.jsonl")
    parser.add_argument("--out", default="data/processed/documents.jsonl")
    parser.add_argument("--report", default="results/extraction_report.md")
    parser.add_argument("--backend", default="auto")
    parser.add_argument("--min-words", type=int, default=50,
                        help="drop documents shorter than this; they are usually cover pages")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(f"{manifest_path} not found — run `make scrape` first")

    entries = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    report = ExtractionReport()
    documents = []
    dropped_short = 0

    for entry in entries:
        if not entry.get("local_path"):
            continue
        extracted = extract(
            entry["local_path"],
            entry["doc_id"],
            backend=args.backend,
            metadata={
                "title": entry.get("title"),
                "url": entry.get("url"),
                "doc_type": entry.get("doc_type"),
                "published": entry.get("published"),
                "notification_id": entry.get("notification_id"),
            },
        )
        report.add(extracted)

        if not extracted.ok:
            continue
        if len(extracted.text.split()) < args.min_words:
            dropped_short += 1
            continue

        if not extracted.metadata.get("published"):
            inferred = infer_published(extracted.text)
            if inferred:
                extracted.metadata["published"] = inferred
                extracted.metadata["published_source"] = "document_header"

        documents.append(
            {
                "doc_id": extracted.doc_id,
                "text": extracted.text,
                "n_pages": extracted.n_pages,
                "n_tables": extracted.n_tables,
                "extraction_backend": extracted.backend,
                **{k: v for k, v in extracted.metadata.items() if v is not None},
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=False) + "\n")

    graph = build_supersession_graph([(d["doc_id"], d["text"]) for d in documents])

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    body = report.markdown()
    body += f"\n\n{dropped_short} documents dropped as too short (< {args.min_words} words).\n"
    body += (
        f"\n## Supersession graph\n\n"
        f"{len(graph.superseded_by)} notifications explicitly superseded, "
        f"{len(graph.amended_by)} amended, parsed from the document text.\n\n"
        f"Every one of these is a chunk that can produce a confidently-cited "
        f"wrong answer if retrieved without its status. See `src/retrieve/recency.py`.\n"
    )
    report_path.write_text(body, encoding="utf-8")

    print(body)
    print(f"\nwrote {len(documents)} documents to {out_path}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
