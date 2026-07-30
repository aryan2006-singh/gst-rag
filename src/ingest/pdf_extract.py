"""PDF extraction with an explicit failure taxonomy.

This is the 40% of the project nobody writes about, so it is the part worth
writing about. The deliverable here is not "I extracted the text" — it is the
table of *how extraction failed and how often*, which is a genuinely interesting
artifact and something almost no portfolio RAG project has.

Failure modes actually present in CBIC PDFs, in rough order of frequency:

  scanned          no text layer at all; needs OCR
  broken_tables    rate schedules flatten into unreadable token soup
  multi_column     two-column layouts interleave lines from both columns
  header_noise     page headers/footers repeat into every chunk
  ligature_damage  "notification" arrives as "noti cation" (fi ligature lost)
  hindi_mixed      Devanagari and English interleaved
  empty            downloaded fine, parses to nothing

Each is detected, counted, and reported. `ExtractionReport` is what you turn
into a chart for your write-up.

Backends, in preference order — all optional, degrade gracefully:
  pymupdf4llm   best default; markdown output preserves table structure
  pymupdf       fast plain text
  pdfplumber    slower, best explicit table extraction
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Repeated page furniture that pollutes every chunk if not stripped.
HEADER_PATTERNS = [
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*F\.\s*No\.[^\n]{0,60}$", re.MULTILINE),
    re.compile(r"^\s*Government of India\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*Ministry of Finance\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*\[?To be published in the Gazette[^\n]*$", re.MULTILINE | re.IGNORECASE),
]

LIGATURE_FIXES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ",
}

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
# "noti cation", "speci ed" — an fi/fl ligature dropped rather than mapped.
BROKEN_LIGATURE_RE = re.compile(
    r"\b(noti|speci|classi|identi|certi|noti|justi)\s(cation|ed|cate|es)\b",
    re.IGNORECASE,
)


@dataclass
class ExtractedDocument:
    doc_id: str
    text: str
    n_pages: int
    n_tables: int
    backend: str
    failures: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.text.strip()) and "scanned" not in self.failures


@dataclass
class ExtractionReport:
    total: int = 0
    succeeded: int = 0
    failure_counts: Counter = field(default_factory=Counter)
    per_doc: dict[str, list[str]] = field(default_factory=dict)

    def add(self, document: ExtractedDocument) -> None:
        self.total += 1
        if document.ok:
            self.succeeded += 1
        for failure in document.failures:
            self.failure_counts[failure] += 1
        if document.failures:
            self.per_doc[document.doc_id] = document.failures

    def markdown(self) -> str:
        if not self.total:
            return "no documents processed"
        lines = [
            "## PDF extraction failure modes",
            "",
            f"{self.succeeded}/{self.total} documents "
            f"({self.succeeded / self.total:.0%}) extracted cleanly.",
            "",
            "| Failure mode | Documents | Share |",
            "|---|---|---|",
        ]
        for mode, count in self.failure_counts.most_common():
            lines.append(f"| `{mode}` | {count} | {count / self.total:.0%} |")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Cleaning and detection
# --------------------------------------------------------------------------- #

def fix_ligatures(text: str) -> str:
    for bad, good in LIGATURE_FIXES.items():
        text = text.replace(bad, good)
    # Rejoin words split by a lost ligature: "noti cation" -> "notification"
    return BROKEN_LIGATURE_RE.sub(lambda m: m.group(1) + "fi" + m.group(2), text)


def strip_headers(text: str) -> str:
    for pattern in HEADER_PATTERNS:
        text = pattern.sub("", text)
    return text


def dehyphenate(text: str) -> str:
    """Rejoin words broken across line ends: 'regis-\\ntration' -> 'registration'."""
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean(text: str) -> str:
    return normalize_whitespace(strip_headers(dehyphenate(fix_ligatures(text))))


def detect_failures(text: str, n_pages: int, n_tables: int) -> list[str]:
    failures: list[str] = []
    stripped = text.strip()

    if not stripped:
        failures.append("empty")
        return failures

    words = stripped.split()
    # A text-layer PDF yields on the order of hundreds of words per page. Far
    # fewer means we got only the OCR-less furniture.
    if n_pages > 0 and len(words) / n_pages < 40:
        failures.append("scanned")

    if DEVANAGARI_RE.search(stripped):
        failures.append("hindi_mixed")

    if BROKEN_LIGATURE_RE.search(stripped):
        failures.append("ligature_damage")

    # Rate schedules: many short numeric lines and no detected table structure.
    lines = [line for line in stripped.split("\n") if line.strip()]
    if lines:
        numeric_short = sum(
            1 for line in lines if len(line.split()) <= 4 and re.search(r"\d", line)
        )
        if numeric_short / len(lines) > 0.35 and n_tables == 0:
            failures.append("broken_tables")

    # Two-column interleaving leaves an unusual number of lines ending mid-clause.
    if lines and len(lines) > 20:
        no_terminator = sum(1 for line in lines if not re.search(r"[.;:,)]\s*$", line))
        if no_terminator / len(lines) > 0.75:
            failures.append("multi_column")

    if any(pattern.search(text) for pattern in HEADER_PATTERNS):
        failures.append("header_noise")

    return failures


# --------------------------------------------------------------------------- #
#  Backends
# --------------------------------------------------------------------------- #

def extract_pymupdf4llm(path: Path) -> tuple[str, int, int]:
    import pymupdf
    import pymupdf4llm

    with pymupdf.open(path) as doc:
        n_pages = doc.page_count
    text = pymupdf4llm.to_markdown(str(path))
    # Markdown pipe tables are how pymupdf4llm represents detected tables.
    n_tables = text.count("\n|---")
    return text, n_pages, n_tables


def extract_pymupdf(path: Path) -> tuple[str, int, int]:
    import pymupdf

    parts = []
    with pymupdf.open(path) as doc:
        for page in doc:
            parts.append(page.get_text())
        n_pages = doc.page_count
    return "\n\n".join(parts), n_pages, 0


def extract_pdfplumber(path: Path) -> tuple[str, int, int]:
    import pdfplumber

    parts: list[str] = []
    n_tables = 0
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
            for table in page.extract_tables():
                n_tables += 1
                parts.append(render_table(table))
        n_pages = len(pdf.pages)
    return "\n\n".join(parts), n_pages, n_tables


def render_table(table: list[list]) -> str:
    """Tables as markdown, because that is what survives chunking.

    A rate table rendered as pipe-delimited markdown keeps the row association
    between "description of service" and "rate", which is the entire information
    content. Flattened to prose it becomes noise.
    """
    rows = [
        "| " + " | ".join((cell or "").replace("\n", " ").strip() for cell in row) + " |"
        for row in table
        if any(cell for cell in row)
    ]
    if not rows:
        return ""
    header, *body = rows
    divider = "|" + "|".join(["---"] * (header.count("|") - 1)) + "|"
    return "\n".join([header, divider, *body])


BACKENDS = {
    "pymupdf4llm": extract_pymupdf4llm,
    "pymupdf": extract_pymupdf,
    "pdfplumber": extract_pdfplumber,
}


def extract(
    path: str | Path,
    doc_id: str,
    backend: str = "auto",
    metadata: dict | None = None,
) -> ExtractedDocument:
    path = Path(path)
    order = (
        ["pymupdf4llm", "pdfplumber", "pymupdf"] if backend == "auto" else [backend]
    )

    last_error = None
    for name in order:
        try:
            raw, n_pages, n_tables = BACKENDS[name](path)
        except ImportError as exc:
            last_error = f"{name} not installed ({exc})"
            continue
        except Exception as exc:  # noqa: BLE001
            last_error = f"{name} raised {type(exc).__name__}: {exc}"
            log.warning("%s: %s", doc_id, last_error)
            continue

        text = clean(raw)
        return ExtractedDocument(
            doc_id=doc_id,
            text=text,
            n_pages=n_pages,
            n_tables=n_tables,
            backend=name,
            failures=detect_failures(text, n_pages, n_tables),
            metadata=dict(metadata or {}),
        )

    return ExtractedDocument(
        doc_id=doc_id,
        text="",
        n_pages=0,
        n_tables=0,
        backend="none",
        failures=["empty", f"all_backends_failed: {last_error}"],
        metadata=dict(metadata or {}),
    )
