STRATEGY ?= section
EMBEDDER  ?= sentence-transformers
INDEX     ?= data/index
GOLD      ?= data/gold/gold_set.jsonl

.PHONY: install test demo scrape extract build eval eval-dev validate-judge serve clean

install:
	pip install -r requirements.txt

## Full suite. Runs offline in a few seconds — no downloads, no keys.
test:
	pytest tests/ -v

## See the machinery work on the fixture corpus before scraping anything.
demo:
	python scripts/demo_ablation.py

# ---------------------------------------------------------------- ingestion
## Check robots.txt first. Always.
check-robots:
	python -m src.ingest.cbic_scraper --check-robots

scrape:
	python -m src.ingest.cbic_scraper --out data/raw/manifest.jsonl --delay 2.0

extract:
	python -m src.ingest.run_extract --manifest data/raw/manifest.jsonl \
		--out data/processed/documents.jsonl --report results/extraction_report.md

build:
	python -m src.index.build --docs data/processed/documents.jsonl \
		--strategy $(STRATEGY) --embedder $(EMBEDDER) --out $(INDEX)

# ------------------------------------------------------------------- eval
## The one that produces your results table. Uses the held-out test split.
eval:
	python -m src.eval.run_eval --index $(INDEX) --gold $(GOLD) --split test \
		--out-json results/ablation.json --out-md RESULTS.md

## Tune on dev. Never report dev numbers.
eval-dev:
	python -m src.eval.run_eval --index $(INDEX) --gold $(GOLD) --split dev \
		--out-json results/ablation_dev.json --out-md results/RESULTS_dev.md

## Sweep chunking strategies. Each needs its own index, so this is slow.
sweep-chunking:
	for s in fixed_150_0 fixed_300_50 fixed_600_100 section sentence_window; do \
		$(MAKE) build STRATEGY=$$s INDEX=data/index_$$s ; \
		python -m src.eval.run_eval --index data/index_$$s --gold $(GOLD) \
			--split dev --out-json results/chunking_$$s.json \
			--out-md results/chunking_$$s.md ; \
	done

validate-judge:
	python scripts/validate_judge.py score --labels data/gold/human_labels.jsonl

serve:
	INDEX_DIR=$(INDEX) uvicorn src.serve.app:app --host 0.0.0.0 --port 8000

clean:
	rm -rf results/*.json results/*.md .pytest_cache
	find . -name "__pycache__" -type d -exec rm -rf {} +
