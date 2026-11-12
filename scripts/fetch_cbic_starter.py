"""Download the curated CBIC GST starter corpus into a local PDF folder.

    python scripts/fetch_cbic_starter.py            # -> data/raw/pdfs/
    python -m src.ingest.local_pdfs                 # -> data/raw/manifest.jsonl
    make extract build

The list lives in `data/sources/cbic_gst_starter.jsonl`: CGST rules, recent
circulars and instructions, FAQs and amendment acts, all English, all from
cbic-gst.gov.in. It is a starter set for a real index, not the whole of GST law.

Same manners as the scraper: robots.txt is checked first, one request every
`--delay` seconds, and files already on disk are not fetched again. A
`sources.jsonl` sidecar is written next to the PDFs so `local_pdfs` picks up the
proper titles, URLs and document types.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingest.cbic_scraper import USER_AGENT, check_robots  # noqa: E402

DEFAULT_LIST = "data/sources/cbic_gst_starter.jsonl"


def local_name(url: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    # Keep sub-folders out of the name but keep it recognisable.
    return path.removeprefix("/pdf/").replace("/", "__").replace(" ", "_")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", default=DEFAULT_LIST)
    parser.add_argument("--out-dir", default="data/raw/pdfs")
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    sources = [
        json.loads(line)
        for line in Path(args.list).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hosts = {urllib.parse.urlparse(s["url"]).scheme + "://" + urllib.parse.urlparse(s["url"]).netloc for s in sources}
    for host in sorted(hosts):
        if not check_robots(host, "/pdf/"):
            raise SystemExit(f"robots.txt on {host} disallows /pdf/ (or could not be read); stopping")

    sidecar: list[dict] = []
    fetched = cached = failed = 0
    last = 0.0
    for source in sources:
        name = local_name(source["url"])
        target = out_dir / name
        if target.exists() and target.stat().st_size > 0:
            cached += 1
        else:
            wait = args.delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            request = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=args.timeout) as response:
                    payload = response.read()
            except (urllib.error.URLError, TimeoutError) as exc:
                print(f"FAILED {source['url']}: {exc}")
                failed += 1
                last = time.monotonic()
                continue
            last = time.monotonic()
            if not payload.startswith(b"%PDF"):
                print(f"FAILED {source['url']}: response is not a PDF")
                failed += 1
                continue
            target.write_bytes(payload)
            fetched += 1
            print(f"fetched {name} ({len(payload) // 1024} KB)")
        sidecar.append({"file": name, **source})

    with open(out_dir / "sources.jsonl", "w", encoding="utf-8") as handle:
        for entry in sidecar:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n{fetched} fetched, {cached} already on disk, {failed} failed -> {out_dir}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
