"""Build an extraction manifest from a folder of PDFs you already have.

The CBIC scraper (`cbic_scraper.py`) is one way to get documents; this is the
other. Download notifications or circulars by hand, or with
`scripts/fetch_cbic_starter.py`, put them in a folder, and this writes the same
`manifest.jsonl` the scraper writes, so `make extract` and `make build` work
unchanged.

    python -m src.ingest.local_pdfs --pdf-dir data/raw/pdfs --out data/raw/manifest.jsonl

Metadata comes from two places, best first:

  1. An optional `sources.jsonl` sidecar in the folder, one object per file:
     {"file": "circular-231.pdf", "url": "...", "title": "...",
      "doc_type": "circular", "published": "2024-09-10"}
     Every key except "file" is optional.
  2. The filename. "circular-231.pdf" becomes title "circular 231" and
     doc_type "circular". Weak, but better than nothing, and the sidecar
     overrides it.

A publication date missing here is filled from the document text at extraction
time (see `run_extract.infer_published`).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path

from src.ingest.cbic_scraper import (
    SourceDocument,
    extract_date,
    extract_identifier,
    make_doc_id,
)

log = logging.getLogger(__name__)

SIDECAR = "sources.jsonl"

# Checked in order; the first match wins. "corrigendum" before "circular" so a
# corrigendum to a circular isn't filed as the circular itself.
DOC_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("corrigendum", re.compile(r"corrigendum", re.I)),
    ("circular", re.compile(r"circular|\bcir\b", re.I)),
    ("notification", re.compile(r"notification|notfctn|\bnn\b|\bct\b", re.I)),
    ("instruction", re.compile(r"instruction|\bins\b", re.I)),
    ("order", re.compile(r"\border\b", re.I)),
    ("faq", re.compile(r"faq|guidance|guidnce", re.I)),
    ("rules", re.compile(r"rules?\b", re.I)),
    ("act", re.compile(r"\bact\b", re.I)),
    ("press_release", re.compile(r"press", re.I)),
]


def guess_doc_type(name: str) -> str:
    words = re.sub(r"[_\-.]+", " ", name)
    for doc_type, pattern in DOC_TYPE_PATTERNS:
        if pattern.search(words):
            return doc_type
    return "other"


def title_from_filename(path: Path) -> str:
    return re.sub(r"[_\-]+", " ", path.stem).strip()


def local_doc_id(doc_type: str, title: str, url: str) -> str:
    """Like `make_doc_id`, but a readable title slug instead of a URL hash.

    Doc ids show up in citations; "rules-cgst-rules-2017" says what it is,
    "rules-7f71c16128f2" does not.
    """
    if extract_identifier(title):
        return make_doc_id(doc_type, title, url)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-")
    prefix = re.sub(r"[^a-z0-9]+", "-", doc_type.lower()).strip("-")
    if slug.startswith(prefix + "-") or slug == prefix:
        return slug
    return f"{prefix}-{slug}" if slug else make_doc_id(doc_type, title, url)


def load_sidecar(pdf_dir: Path) -> dict[str, dict]:
    path = pdf_dir / SIDECAR
    if not path.exists():
        return {}
    entries: dict[str, dict] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON ({exc})") from exc
        if "file" not in entry:
            raise ValueError(f"{path}:{line_no}: missing 'file'")
        entries[entry["file"]] = entry
    return entries


def build_manifest(pdf_dir: str | Path) -> list[SourceDocument]:
    pdf_dir = Path(pdf_dir)
    if not pdf_dir.is_dir():
        raise FileNotFoundError(f"{pdf_dir} is not a directory")
    sidecar = load_sidecar(pdf_dir)

    documents: list[SourceDocument] = []
    used_ids: set[str] = set()
    pdfs = sorted(p for p in pdf_dir.rglob("*") if p.suffix.lower() == ".pdf")
    for path in pdfs:
        relative = path.relative_to(pdf_dir).as_posix()
        meta = sidecar.get(relative, {})
        title = meta.get("title") or title_from_filename(path)
        doc_type = meta.get("doc_type") or guess_doc_type(relative)
        url = meta.get("url") or f"file://{relative}"

        doc_id = local_doc_id(doc_type, title, url)
        # Two files can share an identifier (a circular and its corrigendum
        # filed under the same type, an English and Hindi copy). Doc ids key
        # the index, so they must be unique.
        base, n = doc_id, 2
        while doc_id in used_ids:
            doc_id = f"{base}-{n}"
            n += 1
        used_ids.add(doc_id)

        documents.append(
            SourceDocument(
                doc_id=doc_id,
                url=url,
                title=title,
                doc_type=doc_type,
                published=meta.get("published") or extract_date(path.stem),
                notification_id=meta.get("notification_id") or extract_identifier(title),
                local_path=str(path),
            )
        )

    unknown = set(sidecar) - {p.relative_to(pdf_dir).as_posix() for p in pdfs}
    for name in sorted(unknown):
        log.warning("%s lists %s but no such PDF is in %s", SIDECAR, name, pdf_dir)
    return documents


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pdf-dir", default="data/raw/pdfs")
    parser.add_argument("--out", default="data/raw/manifest.jsonl")
    args = parser.parse_args()

    documents = build_manifest(args.pdf_dir)
    if not documents:
        raise SystemExit(f"no PDFs found under {args.pdf_dir}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(asdict(document), ensure_ascii=False) + "\n")

    by_type: dict[str, int] = {}
    for document in documents:
        by_type[document.doc_type] = by_type.get(document.doc_type, 0) + 1
    summary = ", ".join(f"{n} {t}" for t, n in sorted(by_type.items()))
    print(f"wrote {len(documents)} entries to {out} ({summary})")


if __name__ == "__main__":
    main()
