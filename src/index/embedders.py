"""Embedding backends behind one protocol.

`HashingEmbedder` exists so the entire pipeline — indexing, fusion, reranking,
the eval harness — is testable offline in milliseconds with no model download.
That is not a toy: it means CI can run the full ablation on a fixture corpus and
fail the build if a refactor changes retrieval behaviour. A project whose eval
only runs when someone remembers to run it is a project whose eval rots.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Embedder(Protocol):
    dim: int
    name: str

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        """Return L2-normalised embeddings, shape [len(texts), dim]."""
        ...


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class HashingEmbedder:
    """Deterministic bag-of-ngrams hashing. Offline, instant, no weights.

    Real semantic quality is poor — that is fine and expected. Its job is to make
    the plumbing testable and to give you a *lexical-ish* dense baseline that any
    real embedding model must beat. If your fancy model doesn't beat hashing on
    your gold set, that is a finding worth reporting.
    """

    def __init__(self, dim: int = 256, ngram: int = 3, seed: int = 0) -> None:
        self.dim = dim
        self.ngram = ngram
        self.seed = seed
        self.name = f"hashing-{dim}d"

    def _features(self, text: str) -> list[str]:
        words = re.findall(r"[a-z0-9()/]+", text.lower())
        grams = list(words)
        for size in (2, 3):
            grams += [" ".join(words[i : i + size]) for i in range(len(words) - size + 1)]
        return grams

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature in self._features(text):
                digest = hashlib.blake2b(
                    f"{self.seed}:{feature}".encode(), digest_size=8
                ).digest()
                value = int.from_bytes(digest, "little")
                out[row, value % self.dim] += 1.0 if (value >> 63) & 1 else -1.0
        return l2_normalize(out)


class SentenceTransformerEmbedder:
    """CPU-friendly local embeddings. No API key, no per-query cost.

    Model notes for this domain:
      * BAAI/bge-small-en-v1.5   384d, fast, needs the query prefix below.
      * intfloat/e5-small-v2     384d, needs "query: " / "passage: " prefixes.
      * BAAI/bge-base-en-v1.5    768d, ~3x slower on CPU, usually +2-4 pts recall.

    The asymmetric query prefix is not optional. bge and e5 are trained with it,
    and dropping it costs several points of recall — a silent, easy mistake that
    makes people conclude "dense retrieval doesn't work on my domain".
    """

    QUERY_PREFIXES = {
        "bge": "Represent this sentence for searching relevant passages: ",
        "e5": "query: ",
    }
    PASSAGE_PREFIXES = {"bge": "", "e5": "passage: "}

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        batch_size: int = 32,
        device: str = "cpu",
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device=device)
        self.model_name = model_name
        self.name = model_name
        self.batch_size = batch_size
        self.dim = self.model.get_sentence_embedding_dimension()
        self.family = self._family(model_name)

    @staticmethod
    def _family(model_name: str) -> str:
        lowered = model_name.lower()
        if "bge" in lowered:
            return "bge"
        if "e5" in lowered:
            return "e5"
        return "none"

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        prefix = ""
        if self.family != "none":
            table = self.QUERY_PREFIXES if is_query else self.PASSAGE_PREFIXES
            prefix = table[self.family]
        prepared = [prefix + t for t in texts] if prefix else texts
        vectors = self.model.encode(
            prepared,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(prepared) > 512,
        )
        return vectors.astype(np.float32)


class CachedEmbedder:
    """Disk-backed cache keyed by (model name, text).

    Re-embedding 40k chunks on CPU every time you tweak a chunking parameter is
    how a 3-week project becomes a 6-week one.
    """

    def __init__(self, inner: Embedder, path: str = "data/cache/embeddings.npz") -> None:
        import os

        self.inner = inner
        self.dim = inner.dim
        self.name = f"cached({inner.name})"
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._cache: dict[str, np.ndarray] = {}
        if os.path.exists(path):
            with np.load(path, allow_pickle=True) as data:
                keys = data["keys"]
                values = data["values"]
                self._cache = {str(k): v for k, v in zip(keys, values)}
        self._dirty = False

    def _key(self, text: str, is_query: bool) -> str:
        digest = hashlib.blake2b(text.encode(), digest_size=16).hexdigest()
        return f"{self.inner.name}|{int(is_query)}|{digest}"

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        keys = [self._key(t, is_query) for t in texts]
        missing = [i for i, key in enumerate(keys) if key not in self._cache]
        if missing:
            fresh = self.inner.encode([texts[i] for i in missing], is_query=is_query)
            for slot, i in enumerate(missing):
                self._cache[keys[i]] = fresh[slot]
            self._dirty = True
        return np.stack([self._cache[key] for key in keys])

    def save(self) -> None:
        if not self._dirty:
            return
        np.savez_compressed(
            self.path,
            keys=np.array(list(self._cache.keys())),
            values=np.stack(list(self._cache.values())),
        )
        self._dirty = False
