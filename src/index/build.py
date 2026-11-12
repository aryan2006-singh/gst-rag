"""Build and load the index.

Kept deliberately boring: chunks to JSONL, embeddings to a .npz, and a manifest
recording exactly which embedder and chunking strategy produced them. The
manifest is not bureaucracy — loading an index built with `bge-small` and
querying it with `e5-small` produces plausible-looking garbage, and without a
recorded fingerprint you will lose a day to it.

    python -m src.index.build --docs data/processed/documents.jsonl \
        --strategy section --out data/index
"""

from __future__ import annotations

import argparse
import gzip
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from src.index.chunking import Chunk, chunk_corpus
from src.index.embedders import Embedder, HashingEmbedder


def load_documents(path: str | Path) -> list[tuple[str, str, dict]]:
    """JSONL (optionally .gz) with at least {doc_id, text}; anything else becomes chunk metadata."""
    documents: list[tuple[str, str, dict]] = []
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            doc_id = record.pop("doc_id")
            text = record.pop("text")
            documents.append((doc_id, text, record))
    return documents


def make_embedder(kind: str, model_name: str | None = None, cache: bool = True) -> Embedder:
    if kind == "hashing":
        return HashingEmbedder()
    if kind in ("sentence-transformers", "st"):
        from src.index.embedders import CachedEmbedder, SentenceTransformerEmbedder

        inner = SentenceTransformerEmbedder(model_name or "BAAI/bge-small-en-v1.5")
        return CachedEmbedder(inner) if cache else inner
    if kind == "fastembed":
        from src.index.embedders import FastEmbedEmbedder

        return FastEmbedEmbedder(model_name or "BAAI/bge-small-en-v1.5")
    raise ValueError(f"unknown embedder kind {kind!r}")


def build_index(
    documents: list[tuple[str, str, dict]],
    strategy: str,
    embedder: Embedder,
    out_dir: str | Path,
) -> tuple[list[Chunk], np.ndarray]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    chunks = chunk_corpus(documents, strategy)
    if not chunks:
        raise ValueError("chunking produced no chunks; check the document texts")

    lengths = sorted(c.n_words for c in chunks)
    print(
        f"{len(documents)} documents -> {len(chunks)} chunks "
        f"(median {lengths[len(lengths) // 2]} words, "
        f"p95 {lengths[int(len(lengths) * 0.95)]} words)"
    )

    start = time.perf_counter()
    embeddings = embedder.encode([c.text for c in chunks], is_query=False)
    elapsed = time.perf_counter() - start
    print(f"embedded in {elapsed:.1f}s ({len(chunks) / max(elapsed, 1e-9):.0f} chunks/s)")

    with open(out / "chunks.jsonl", "w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(asdict(chunk), ensure_ascii=False, default=str) + "\n")
    np.save(out / "embeddings.npy", embeddings)

    manifest = {
        "n_documents": len(documents),
        "n_chunks": len(chunks),
        "chunking_strategy": strategy,
        "embedder": embedder.name,
        "dim": int(embeddings.shape[1]),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if hasattr(embedder, "save"):
        embedder.save()
    print(f"wrote index to {out}")
    return chunks, embeddings


def load_index(
    index_dir: str | Path,
    embedder_kind: str = "sentence-transformers",
) -> tuple[list[Chunk], np.ndarray, Embedder]:
    path = Path(index_dir)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))

    chunks: list[Chunk] = []
    with open(path / "chunks.jsonl", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                chunks.append(Chunk(**json.loads(line)))
    embeddings = np.load(path / "embeddings.npy")

    if len(chunks) != embeddings.shape[0]:
        raise ValueError(
            f"index is corrupt: {len(chunks)} chunks but {embeddings.shape[0]} embeddings"
        )

    embedder = make_embedder(embedder_kind)
    if embedder.dim != embeddings.shape[1]:
        raise ValueError(
            f"embedder {embedder.name} has dim {embedder.dim} but the index was built "
            f"with {manifest['embedder']} at dim {embeddings.shape[1]}. Rebuild the "
            f"index or pass the matching embedder."
        )
    return chunks, embeddings, embedder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", default="data/processed/documents.jsonl")
    parser.add_argument("--strategy", default="section")
    parser.add_argument("--embedder", default="sentence-transformers")
    parser.add_argument("--model", default=None)
    parser.add_argument("--out", default="data/index")
    args = parser.parse_args()

    documents = load_documents(args.docs)
    embedder = make_embedder(args.embedder, args.model)
    build_index(documents, args.strategy, embedder, args.out)


if __name__ == "__main__":
    main()
