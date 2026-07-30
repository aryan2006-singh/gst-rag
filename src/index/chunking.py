"""Chunking strategies, as an experiment rather than a guess.

Chunking is the highest-leverage and least-measured decision in RAG. Everyone
picks 512 tokens with 50 overlap because a tutorial said so. On statutory text
that is often wrong: a GST section is a self-contained unit of meaning with a
number that users cite directly ("section 16(2)"), and splitting it mid-proviso
produces chunks that answer nothing.

Three strategies, all returning the same `Chunk` type so the ablation runner can
swap them and measure the difference.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    ordinal: int
    metadata: dict = field(default_factory=dict)

    @property
    def n_words(self) -> int:
        return len(self.text.split())


# Matches "Section 16.", "16. Eligibility...", "Rule 42", "(2)", "(c)"
SECTION_RE = re.compile(
    r"^\s*(?:(?:Section|Rule|Para(?:graph)?)\s+)?(\d+[A-Z]?)\s*[.:]\s+(?=[A-Z\"'])",
    re.MULTILINE,
)


def fixed_window(
    text: str,
    doc_id: str,
    size: int = 300,
    overlap: int = 50,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Word-count windows with overlap. The baseline everyone starts from.

    Overlap is not free: it inflates your index, and duplicated content means one
    passage can occupy several top-k slots, crowding out genuinely different
    material. Measure that rather than assuming overlap helps.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    words = text.split()
    chunks: list[Chunk] = []
    stride = size - overlap
    for ordinal, start in enumerate(range(0, max(len(words), 1), stride)):
        window = words[start : start + size]
        if not window:
            break
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}::fixed::{ordinal}",
                doc_id=doc_id,
                text=" ".join(window),
                ordinal=ordinal,
                metadata=dict(metadata or {}, strategy="fixed", start_word=start),
            )
        )
        if start + size >= len(words):
            break
    return chunks


def section_aware(
    text: str,
    doc_id: str,
    max_words: int = 400,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split on statutory section boundaries; only fall back to windows when a
    section is too long.

    The section number is carried in metadata *and* prepended to the chunk text.
    Prepending matters: a user asking "what does section 16(2)(c) say" produces a
    query whose strongest lexical signal is the section number, and if that
    number only lives in metadata, BM25 cannot see it.
    """
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return fixed_window(text, doc_id, size=max_words, overlap=50, metadata=metadata)

    chunks: list[Chunk] = []
    ordinal = 0
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        section = match.group(1)
        base_meta = dict(metadata or {}, strategy="section", section=section)

        if len(body.split()) <= max_words:
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}::sec{section}::{ordinal}",
                    doc_id=doc_id,
                    text=body,
                    ordinal=ordinal,
                    metadata=base_meta,
                )
            )
            ordinal += 1
        else:
            header = f"Section {section}. "
            for part in fixed_window(body, doc_id, size=max_words, overlap=60):
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_id}::sec{section}::{ordinal}",
                        doc_id=doc_id,
                        # Repeat the section header in every fragment so the
                        # citable identifier survives the split.
                        text=header + part.text,
                        ordinal=ordinal,
                        metadata=dict(base_meta, split=True),
                    )
                )
                ordinal += 1
    return chunks


def sentence_window(
    text: str,
    doc_id: str,
    window: int = 3,
    stride: int = 2,
    context: int = 1,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Embed a small window of sentences, but store neighbours for the answer.

    The retrieval unit and the generation unit do not have to be the same size.
    Small units embed more precisely; the generator still wants surrounding
    context. `metadata["context_text"]` holds the expanded version.
    """
    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[Chunk] = []
    for ordinal, start in enumerate(range(0, len(sentences), stride)):
        core = sentences[start : start + window]
        if not core:
            break
        low = max(0, start - context)
        high = min(len(sentences), start + window + context)
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}::sw::{ordinal}",
                doc_id=doc_id,
                text=" ".join(core),
                ordinal=ordinal,
                metadata=dict(
                    metadata or {},
                    strategy="sentence_window",
                    context_text=" ".join(sentences[low:high]),
                ),
            )
        )
        if start + window >= len(sentences):
            break
    return chunks


_ABBREVIATIONS = ("No.", "Nos.", "Sec.", "vs.", "Ltd.", "Pvt.", "Rs.", "cl.", "i.e.", "e.g.")


def split_sentences(text: str) -> list[str]:
    """Regex sentence splitter that survives legal abbreviations.

    "Notification No. 13/2017" must not become two sentences. A full NLP splitter
    is better; this has no dependencies and handles the cases that actually occur
    in CBIC text.
    """
    protected = text
    for index, abbreviation in enumerate(_ABBREVIATIONS):
        protected = protected.replace(abbreviation, f"\x00{index}\x00")
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", protected)
    out = []
    for part in parts:
        for index, abbreviation in enumerate(_ABBREVIATIONS):
            part = part.replace(f"\x00{index}\x00", abbreviation)
        part = part.strip()
        if part:
            out.append(part)
    return out


STRATEGIES = {
    "fixed_300_50": lambda text, doc_id, meta: fixed_window(text, doc_id, 300, 50, meta),
    "fixed_150_0": lambda text, doc_id, meta: fixed_window(text, doc_id, 150, 0, meta),
    "fixed_600_100": lambda text, doc_id, meta: fixed_window(text, doc_id, 600, 100, meta),
    "section": lambda text, doc_id, meta: section_aware(text, doc_id, 400, meta),
    "sentence_window": lambda text, doc_id, meta: sentence_window(text, doc_id, 3, 2, 1, meta),
}


def chunk_corpus(
    documents: Sequence[tuple[str, str, dict]],
    strategy: str,
) -> list[Chunk]:
    """`documents` is [(doc_id, text, metadata)]."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; have {sorted(STRATEGIES)}")
    fn = STRATEGIES[strategy]
    chunks: list[Chunk] = []
    for doc_id, text, metadata in documents:
        chunks.extend(fn(text, doc_id, metadata))
    return chunks
