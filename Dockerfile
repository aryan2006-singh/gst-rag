# Multi-stage build: Node builds the frontend, Python serves it + the API.
#
# This deploys the fixture/demo corpus (HashingEmbedder, no reranker) rather
# than the real CBIC corpus -- the real scrape is blocked on cbic.gov.in's
# robots.txt currently returning 401. See README.md.

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

# Build the demo index from the fixture corpus (fast, offline, no model
# download) at image-build time, not container-start time.
RUN python scripts/build_dev_index.py

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

ENV EMBEDDER=hashing
ENV RERANK=0
ENV INDEX_DIR=data/index_dev

EXPOSE 8000
CMD ["sh", "-c", "uvicorn src.serve.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
