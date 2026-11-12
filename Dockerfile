# Multi-stage build: Node builds the frontend, Python serves it + the API.
#
# This deploys the CBIC GST starter corpus (40 rules, circulars, instructions
# and FAQs from cbic-gst.gov.in, pre-extracted and committed under
# data/corpus/) with the HashingEmbedder and no reranker, so the image needs
# no torch and no model download. See README.md.

FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS final
WORKDIR /app

# Hashing embedder + no reranker needs no torch/sentence-transformers at
# runtime -- keep the image light.
RUN pip install --no-cache-dir numpy fastapi "uvicorn[standard]" pydantic

COPY src/ ./src/
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY data/corpus/ ./data/corpus/

# Build the index at image-build time, not container-start time. Hashing
# embeddings over ~700 chunks take well under a second.
RUN python -m src.index.build \
    --docs data/corpus/cbic_gst_starter.documents.jsonl.gz \
    --strategy section --embedder hashing --out data/index_cbic

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

ENV EMBEDDER=hashing
ENV RERANK=0
ENV INDEX_DIR=data/index_cbic
# Render puts one proxy in front of the app; its X-Forwarded-For entry is the
# one to rate-limit on (see src/serve/limits.py:client_key).
ENV TRUSTED_PROXY_HOPS=1
ENV RATE_LIMIT_PER_MINUTE=60
ENV QUERY_CACHE_SIZE=256

EXPOSE 8000
CMD ["sh", "-c", "uvicorn src.serve.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
