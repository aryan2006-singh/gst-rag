"""Query rewriting for GST questions.

Real user queries look like "can I claim ITC on hotel stay for business trip".
The corpus says "input tax credit shall not be available in respect of ...
accommodation". Neither BM25 nor a general-purpose embedding model bridges
"ITC" to "input tax credit" reliably, because that abbreviation is domain
jargon that appears in neither's training distribution with this meaning.

A hand-built expansion table fixes the largest share of that gap for zero cost
and zero latency, which is why it comes before anything clever. Report it as its
own ablation row — if a 40-line dictionary beats your LLM-based rewriter, that
is the finding.
"""

from __future__ import annotations

import re

# Expansions are additive: the original term is kept, so an exact-match query for
# "ITC" still scores. Removing the acronym would lose the documents that use it.
GST_EXPANSIONS: dict[str, str] = {
    "itc": "input tax credit",
    "gst": "goods and services tax",
    "cgst": "central goods and services tax",
    "sgst": "state goods and services tax",
    "igst": "integrated goods and services tax",
    "utgst": "union territory goods and services tax",
    "rcm": "reverse charge mechanism",
    "hsn": "harmonised system of nomenclature classification code",
    "sac": "services accounting code",
    "gstr": "goods and services tax return",
    "gstin": "goods and services tax identification number",
    "eway": "electronic way bill",
    "e-way": "electronic way bill",
    "tds": "tax deducted at source",
    "tcs": "tax collected at source",
    "isd": "input service distributor",
    "cbic": "central board of indirect taxes and customs",
    "aar": "authority for advance ruling",
    "aaar": "appellate authority for advance ruling",
    "itat": "income tax appellate tribunal",
    "lut": "letter of undertaking",
    "sez": "special economic zone",
    "composition": "composition scheme levy",
    "b2b": "business to business registered recipient",
    "b2c": "business to consumer unregistered recipient",
}

# Statutory phrasing differs from how people speak.
PHRASE_HINTS: dict[str, str] = {
    "claim credit": "entitled to take input tax credit",
    "cannot claim": "shall not be available blocked credit",
    "due date": "time limit prescribed period",
    "late fee": "late fee payable under section 47",
    "interest": "interest payable under section 50",
    "refund": "refund of unutilised input tax credit",
    "cancel registration": "cancellation of registration section 29",
    "hotel": "accommodation food and beverages",
    "car": "motor vehicle conveyance",
}

SECTION_PATTERN = re.compile(r"\b(?:sec(?:tion)?|s\.)\s*(\d+[A-Z]?)", re.IGNORECASE)
RULE_PATTERN = re.compile(r"\brule\s*(\d+[A-Z]?)", re.IGNORECASE)


def expand_acronyms(query: str) -> str:
    """Append expansions for any domain acronym present. Original text is kept."""
    tokens = re.findall(r"[A-Za-z][A-Za-z-]*", query.lower())
    additions: list[str] = []
    for token in tokens:
        expansion = GST_EXPANSIONS.get(token)
        if expansion and expansion not in query.lower():
            additions.append(expansion)
    return query + (" " + " ".join(additions) if additions else "")


def add_phrase_hints(query: str) -> str:
    lowered = query.lower()
    additions = [
        hint for phrase, hint in PHRASE_HINTS.items() if phrase in lowered
    ]
    return query + (" " + " ".join(additions) if additions else "")


def normalize_citations(query: str) -> str:
    """Rewrite 'sec 16' / 's.16' to the canonical 'section 16' form the corpus uses."""
    query = SECTION_PATTERN.sub(lambda m: f"section {m.group(1)}", query)
    query = RULE_PATTERN.sub(lambda m: f"rule {m.group(1)}", query)
    return query


def rewrite(query: str) -> str:
    """The full deterministic rewrite chain. No model, no latency, no cost."""
    out = normalize_citations(query)
    out = expand_acronyms(out)
    out = add_phrase_hints(out)
    return re.sub(r"\s+", " ", out).strip()


class LLMQueryRewriter:
    """Optional: a local instruct model generates a statutory-style paraphrase.

    Compare it against `rewrite` in the ablation rather than assuming it wins.
    LLM rewriting adds real latency per query and can *hurt* by drifting away
    from the terms that actually appear in the corpus — a failure mode worth
    demonstrating with a concrete example in your write-up.
    """

    PROMPT = (
        "Rewrite the user's GST question using the formal statutory vocabulary "
        "found in Indian GST law, so it can be matched against the text of the "
        "CGST Act and CBIC circulars. Expand abbreviations. Keep it to one "
        "sentence. Output only the rewritten query.\n\nQuestion: {query}\nRewritten:"
    )

    def __init__(self, generator, keep_original: bool = True) -> None:
        self.generator = generator
        self.keep_original = keep_original

    def __call__(self, query: str) -> str:
        generated = self.generator(self.PROMPT.format(query=query)).strip()
        base = rewrite(query)
        return f"{base} {generated}" if self.keep_original else generated
