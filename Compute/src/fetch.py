"""
Web content fetcher: RSS feeds + HTML scraping for all configured sources.
"""

import json
import hashlib
import time
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup
import trafilatura

BASE_DIR = Path(__file__).parent.parent
SEEN_URLS_FILE = BASE_DIR / "data" / "seen_urls.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

MAX_ARTICLES_PER_SOURCE = 15  # cap per fetch run to avoid overloading
REQUEST_DELAY = 1.0            # seconds between requests

# ── Source registry ────────────────────────────────────────────────────────────
SOURCES = [
    # RSS feeds
    {
        "name": "MIT Technology Review",
        "type": "rss",
        "url": "https://www.technologyreview.com/feed/",
    },
    {
        "name": "Epoch AI",
        "type": "rss",
        "url": "https://epochai.substack.com/feed",
    },
    {
        "name": "RAND (AI & Technology)",
        "type": "rss",
        "url": "https://www.rand.org/topics/artificial-intelligence.xml",
    },
    {
        "name": "Brookings Institution",
        "type": "rss",
        "url": "https://www.brookings.edu/feed/",
    },
    {
        "name": "CSET Georgetown",
        "type": "rss",
        "url": "https://cset.georgetown.edu/feed/",
    },
    {
        "name": "CNAS",
        "type": "rss",
        "url": "https://www.cnas.org/feed",
    },
    # Scraped sources
    {
        "name": "MLCommons",
        "type": "scrape",
        "listing_url": "https://mlcommons.org/insights/",
        "base_url": "https://mlcommons.org",
        "link_contains": "/insights/",
    },
    {
        "name": "Exxact Corp Blog",
        "type": "scrape",
        "listing_url": "https://www.exxactcorp.com/blog",
        "base_url": "https://www.exxactcorp.com",
        "link_contains": "/blog/",
    },
    {
        "name": "CoreWeave Blog",
        "type": "scrape",
        "listing_url": "https://www.coreweave.com/blog",
        "base_url": "https://www.coreweave.com",
        "link_contains": "/blog/",
    },
    {
        "name": "SemiAnalysis",
        "type": "scrape",
        "listing_url": "https://semianalysis.com/",
        "base_url": "https://semianalysis.com",
        "link_contains": "/p/",
    },
]


# ── Seen-URL tracking ──────────────────────────────────────────────────────────

def _load_seen() -> dict:
    if SEEN_URLS_FILE.exists():
        try:
            return json.loads(SEEN_URLS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_seen(seen: dict):
    SEEN_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_URLS_FILE.write_text(
        json.dumps(seen, indent=2), encoding="utf-8"
    )


def seen_url_count() -> int:
    return len(_load_seen())


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 15) -> requests.Response | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


def _extract_text(url: str, html: str) -> str:
    """Use trafilatura to pull main article text from raw HTML."""
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )
    return (text or "").strip()


# ── RSS fetching ───────────────────────────────────────────────────────────────

def _fetch_rss(source: dict, seen: dict) -> list[dict]:
    feed = feedparser.parse(source["url"])
    articles = []

    for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
        url = entry.get("link", "")
        if not url or url in seen:
            continue

        # Try to get full text by fetching the article page
        time.sleep(REQUEST_DELAY)
        resp = _get(url)
        if resp:
            text = _extract_text(url, resp.text)
        else:
            # Fall back to RSS summary
            text = BeautifulSoup(
                entry.get("summary", ""), "lxml"
            ).get_text(separator=" ")

        if len(text) < 150:
            continue

        date = ""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            date = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")

        articles.append({
            "title": entry.get("title", ""),
            "url": url,
            "text": text,
            "source_name": source["name"],
            "date": date,
        })

    return articles


# ── Scrape fetching ────────────────────────────────────────────────────────────

def _discover_article_urls(source: dict) -> list[str]:
    resp = _get(source["listing_url"])
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    base = source["base_url"]
    pattern = source["link_contains"]
    seen_hrefs: set[str] = set()
    urls = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        # Resolve relative URLs
        if href.startswith("/"):
            href = base + href
        elif not href.startswith("http"):
            continue
        # Must contain the pattern and be on the same domain
        parsed = urlparse(href)
        base_parsed = urlparse(base)
        if pattern in href and parsed.netloc == base_parsed.netloc:
            # Strip query strings and fragments
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if clean not in seen_hrefs:
                seen_hrefs.add(clean)
                urls.append(clean)

    return urls[:MAX_ARTICLES_PER_SOURCE]


def _fetch_scrape(source: dict, seen: dict) -> list[dict]:
    article_urls = _discover_article_urls(source)
    articles = []

    for url in article_urls:
        if url in seen:
            continue

        time.sleep(REQUEST_DELAY)
        resp = _get(url)
        if not resp:
            continue

        text = _extract_text(url, resp.text)
        if len(text) < 150:
            continue

        # Try to extract title from HTML
        soup = BeautifulSoup(resp.text, "lxml")
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url

        articles.append({
            "title": title,
            "url": url,
            "text": text,
            "source_name": source["name"],
            "date": datetime.now().strftime("%Y-%m-%d"),
        })

    return articles


# ── Main entry point ───────────────────────────────────────────────────────────

def fetch_all(progress_callback=None) -> list[dict]:
    """
    Fetch new articles from all sources. Skips already-seen URLs.
    Returns list of new article dicts.
    progress_callback(source_name, status) called for each source.
    """
    seen = _load_seen()
    all_articles = []

    for i, source in enumerate(SOURCES):
        name = source["name"]
        if progress_callback:
            progress_callback(name, "fetching")

        try:
            if source["type"] == "rss":
                articles = _fetch_rss(source, seen)
            else:
                articles = _fetch_scrape(source, seen)
        except Exception as e:
            if progress_callback:
                progress_callback(name, f"error: {e}")
            continue

        for art in articles:
            seen[art["url"]] = art["date"] or datetime.now().strftime("%Y-%m-%d")

        all_articles.extend(articles)

        if progress_callback:
            progress_callback(name, f"done ({len(articles)} new)")

    _save_seen(seen)
    return all_articles
