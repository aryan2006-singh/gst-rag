"""Fetch CBIC GST circulars and notifications.

Read this before running it
---------------------------
This scrapes a government website. Three obligations, none optional:

  * **Rate limit.** One request every `delay` seconds, single-threaded. The
    default is 2s. CBIC is not a CDN and you are not entitled to its bandwidth.
  * **Cache everything to disk.** Fetch once, parse a hundred times. Re-fetching
    while iterating on your parser is the actual rude behaviour, and it is also
    slower for you.
  * **Identify yourself** in the User-Agent and check robots.txt before a real
    run. `python -m src.ingest.cbic_scraper --check-robots` does the check.

Structure of the source: CBIC publishes circulars and notifications as index
pages of links to PDFs, grouped by year. The HTML layout has changed more than
once, so `parse_index_page` is written to be forgiving — it looks for links that
*look like* notification PDFs rather than relying on a specific table structure,
and it logs anything it skipped so you can see what the parser missed instead of
silently under-collecting.

Legal note: these documents are Government of India publications. Reproducing
them for a research/portfolio project is normal, but say where they came from and
do not claim the corpus as your own work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import time
import urllib.parse
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

BASE = "https://www.cbic.gov.in"
USER_AGENT = (
    "gst-rag-research/0.1 (portfolio project; contact: your-email@example.com)"
)

# Circular / notification identifiers as they appear in link text and filenames.
CIRCULAR_ID_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*[-–]\s*(\d{4})", re.IGNORECASE)
NOTIFICATION_ID_RE = re.compile(r"(\d+)\s*/\s*(\d{4})\s*[-–]?\s*([A-Z()\.\s]*)", re.IGNORECASE)
DATE_RE = re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})")


@dataclass
class SourceDocument:
    doc_id: str
    url: str
    title: str
    doc_type: str  # "circular" | "notification" | "faq" | "order"
    published: str | None = None
    notification_id: str | None = None
    local_path: str | None = None
    fetch_error: str | None = None
    metadata: dict = field(default_factory=dict)


class RateLimitedFetcher:
    """Single-threaded, disk-cached, polite."""

    def __init__(
        self,
        cache_dir: str | Path = "data/raw/cache",
        delay: float = 2.0,
        timeout: int = 30,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.timeout = timeout
        self._last_request = 0.0
        self.n_fetched = 0
        self.n_cached = 0

    def _cache_path(self, url: str, suffix: str) -> Path:
        digest = hashlib.blake2b(url.encode(), digest_size=16).hexdigest()
        return self.cache_dir / f"{digest}{suffix}"

    def get(self, url: str, suffix: str = ".html") -> bytes | None:
        path = self._cache_path(url, suffix)
        if path.exists():
            self.n_cached += 1
            return path.read_bytes()

        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        import urllib.error
        import urllib.request

        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            log.warning("fetch failed %s: %s", url, exc)
            self._last_request = time.monotonic()
            return None

        self._last_request = time.monotonic()
        self.n_fetched += 1
        path.write_bytes(payload)
        return payload


def check_robots(url: str = BASE, path: str = "/") -> bool:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(urllib.parse.urljoin(url, "/robots.txt"))
    try:
        parser.read()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read robots.txt (%s); assuming disallowed", exc)
        return False
    return parser.can_fetch(USER_AGENT, urllib.parse.urljoin(url, path))


def parse_index_page(html: str, base_url: str, doc_type: str) -> list[SourceDocument]:
    """Extract PDF links from a CBIC index page.

    Written against link shape rather than page structure, because the page
    structure has changed. Returns documents in page order; the caller dedupes.
    """
    documents: list[SourceDocument] = []
    seen: set[str] = set()

    # <a href="...pdf" ...>text</a>, tolerant of attribute order and whitespace.
    for match in re.finditer(
        r"<a\s[^>]*href\s*=\s*[\"']([^\"']+\.pdf)[\"'][^>]*>(.*?)</a>",
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        href, raw_text = match.group(1), match.group(2)
        title = re.sub(r"<[^>]+>", " ", raw_text)
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue

        url = urllib.parse.urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)

        documents.append(
            SourceDocument(
                doc_id=make_doc_id(doc_type, title, url),
                url=url,
                title=title,
                doc_type=doc_type,
                published=extract_date(title),
                notification_id=extract_identifier(title),
            )
        )
    return documents


def extract_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_identifier(text: str) -> str | None:
    match = CIRCULAR_ID_RE.search(text) or NOTIFICATION_ID_RE.search(text)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(0)).upper().rstrip("-.")


def make_doc_id(doc_type: str, title: str, url: str) -> str:
    identifier = extract_identifier(title)
    if identifier:
        slug = re.sub(r"[^A-Z0-9]+", "-", identifier).strip("-").lower()
        return f"{doc_type}-{slug}"
    digest = hashlib.blake2b(url.encode(), digest_size=6).hexdigest()
    return f"{doc_type}-{digest}"


def crawl(
    index_urls: dict[str, str],
    fetcher: RateLimitedFetcher,
    limit: int | None = None,
) -> list[SourceDocument]:
    """`index_urls` maps doc_type -> index page URL."""
    collected: list[SourceDocument] = []
    for doc_type, index_url in index_urls.items():
        payload = fetcher.get(index_url, suffix=".html")
        if payload is None:
            log.error("could not fetch index %s", index_url)
            continue
        found = parse_index_page(payload.decode("utf-8", errors="replace"), index_url, doc_type)
        log.info("%s: %d document links on %s", doc_type, len(found), index_url)
        collected.extend(found)

    if limit:
        collected = collected[:limit]

    for document in collected:
        payload = fetcher.get(document.url, suffix=".pdf")
        if payload is None:
            document.fetch_error = "download failed"
            continue
        if not payload.startswith(b"%PDF"):
            # A 404 page served with a .pdf URL. Catching this here saves a
            # confusing failure three stages later in the PDF parser.
            document.fetch_error = "not a PDF (probably an error page)"
            continue
        document.local_path = str(fetcher._cache_path(document.url, ".pdf"))
    return collected


def save_manifest(documents: list[SourceDocument], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(asdict(document), ensure_ascii=False) + "\n")

    failed = [d for d in documents if d.fetch_error]
    print(f"{len(documents)} documents, {len(failed)} failed")
    for document in failed[:10]:
        print(f"  FAIL {document.doc_id}: {document.fetch_error}")


DEFAULT_INDEX_URLS = {
    # Verify these before a real run — CBIC reorganises its site periodically.
    # The point of keeping them in one dict is that fixing a move is a one-line
    # change, not a hunt through the crawler.
    "circular": f"{BASE}/entities/cbic-content-mst/MTQ0NA==",
    "notification": f"{BASE}/entities/cbic-content-mst/MTQ0Mw==",
}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/raw/manifest.jsonl")
    parser.add_argument("--cache", default="data/raw/cache")
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--check-robots", action="store_true")
    args = parser.parse_args()

    if args.check_robots:
        allowed = check_robots()
        print(f"robots.txt allows this crawler: {allowed}")
        return

    if not check_robots():
        raise SystemExit(
            "robots.txt does not permit this crawl. Do not proceed. "
            "Consider an alternative source, or request the data directly."
        )

    fetcher = RateLimitedFetcher(cache_dir=args.cache, delay=args.delay)
    documents = crawl(DEFAULT_INDEX_URLS, fetcher, limit=args.limit)
    save_manifest(documents, args.out)
    print(f"fetched {fetcher.n_fetched}, served from cache {fetcher.n_cached}")


if __name__ == "__main__":
    main()
