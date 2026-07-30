"""BM25, implemented rather than imported.

`rank_bm25` would do, but writing it yourself is 60 lines, removes a dependency,
lets you fix the tokenizer for legal text, and means you can answer "how does
BM25 handle document length?" in an interview from memory rather than from
vibes.

    score(q, d) = sum over terms t in q of
        IDF(t) * ( f(t,d) * (k1 + 1) ) / ( f(t,d) + k1 * (1 - b + b * |d|/avgdl) )

    IDF(t) = ln( 1 + (N - n(t) + 0.5) / (n(t) + 0.5) )

The `+1` inside the log is the Robertson-Sparck-Jones IDF with the standard
correction that keeps it non-negative — without it, a term appearing in more
than half the corpus gets a negative score and can push a document *down* for
matching the query.

Domain note: GST text is dense with tokens like "section 16(2)(c)",
"notification 13/2017-CT(R)", and "ITC". A whitespace tokenizer shatters those
into useless pieces, so `tokenize` keeps them intact. This is why the tokenizer
lives here and not in a utility module — it is a retrieval-quality decision.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence

# Keep intact: section refs 16(2)(c), notification numbers 13/2017-CT(R),
# rule refs 42, dates, and ordinary words. Split on everything else.
_TOKEN_RE = re.compile(
    r"""
    \d+/\d+(?:-[A-Za-z()]+)?      # 13/2017-CT(R)  notification numbers
  | \d+\([0-9a-zA-Z]+\)(?:\([0-9a-zA-Z]+\))*   # 16(2)(c) sub-section refs
  | [A-Za-z]+(?:['’][A-Za-z]+)?   # words
  | \d+(?:\.\d+)?                 # numbers
    """,
    re.VERBOSE,
)

# Deliberately short. "not", "no" and "any" carry meaning in statutory text
# ("shall not be entitled to credit"), so the usual English stop list is wrong here.
STOPWORDS = frozenset(
    """a an the of in on at to for by with and or as is are was were be been
    from that this these those it its""".split()
)


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens


class BM25:
    def __init__(
        self,
        corpus: Sequence[Sequence[str]],
        ids: Sequence[str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """`corpus` is a list of token lists, aligned with `ids`."""
        if len(corpus) != len(ids):
            raise ValueError("corpus and ids must be the same length")
        if not corpus:
            raise ValueError("empty corpus")

        self.ids = list(ids)
        self.k1 = k1
        self.b = b
        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_len) / len(corpus)
        self.n_docs = len(corpus)

        self.term_freqs: list[Counter] = [Counter(doc) for doc in corpus]
        doc_freq: Counter = Counter()
        for tf in self.term_freqs:
            doc_freq.update(tf.keys())
        self.doc_freq = doc_freq

        # Inverted index so scoring touches only documents containing a query term.
        self.postings: dict[str, list[int]] = {}
        for index, tf in enumerate(self.term_freqs):
            for term in tf:
                self.postings.setdefault(term, []).append(index)

        self._idf = {
            term: math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))
            for term, df in doc_freq.items()
        }

    def idf(self, term: str) -> float:
        return self._idf.get(term, 0.0)

    def score_all(self, query_tokens: Iterable[str]) -> dict[str, float]:
        scores: dict[int, float] = {}
        for term in query_tokens:
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self._idf[term]
            for index in postings:
                freq = self.term_freqs[index][term]
                norm = 1.0 - self.b + self.b * (self.doc_len[index] / self.avgdl)
                contribution = idf * (freq * (self.k1 + 1.0)) / (freq + self.k1 * norm)
                scores[index] = scores.get(index, 0.0) + contribution
        return {self.ids[i]: s for i, s in scores.items()}

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        scores = self.score_all(tokenize(query))
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:k]

    def __len__(self) -> int:
        return self.n_docs
