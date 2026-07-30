"""Build a tiny hashing-embedder index from the test fixtures, for local
frontend development only. The numbers and even the retrieval quality are
meaningless here -- see scripts/demo_ablation.py for why. This exists purely
so `uvicorn src.serve.app:app` has something to load while the frontend is
being built, before the real corpus (see Makefile: scrape/extract/build) is
ready.

    python scripts/build_dev_index.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.index.build import build_index
from src.index.embedders import HashingEmbedder
from tests.fixtures import DOCUMENTS

if __name__ == "__main__":
    build_index(DOCUMENTS, "section", HashingEmbedder(), "data/index_dev")
