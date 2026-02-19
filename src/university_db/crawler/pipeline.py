from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
import json
import re

from university_db.common.logging_utils import get_logger
from university_db.common.models import RawPage
from university_db.common.storage import write_snapshot
from university_db.common.url_utils import absolutize, is_allowed_domain, normalize_url

logger = get_logger(__name__)

PROGRAM_HINTS = ["program", "course", "degree", "msc", "mba", "phd", "bsc", "master", "undergraduate", "postgraduate"]
RENDER_HINTS = ["enable javascript", "loading", "data-reactroot"]


class LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._in_a = False
        self._href = ""
        self._text = ""

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._in_a = True
            self._href = dict(attrs).get("href", "")
            self._text = ""

    def handle_data(self, data):
        if self._in_a:
            self._text += data

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._in_a:
            if self._href:
                self.links.append((absolutize(self.base_url, self._href), self._text.strip()))
            self._in_a = False


def classify_page(url: str, html: str) -> tuple[str, float]:
    lowered = html.lower()
    score = 0.0
    if re.search(r"<h1[^>]*>.*?</h1>", html, flags=re.I | re.S):
        score += 0.25
    if any(k in lowered for k in ["entry requirements", "fees", "duration", "how to apply"]):
        score += 0.35
    if any(k in url.lower() for k in ["/course", "/program", "/degree"]):
        score += 0.2
    if "breadcrumb" in lowered:
        score += 0.1
    if "application/ld+json" in lowered:
        score += 0.1

    page_type = "irrelevant"
    if score >= 0.6:
        page_type = "program_page"
    elif "course" in lowered or "program" in lowered:
        page_type = "listing_page"
        score = max(score, 0.4)
    return page_type, min(score, 1.0)


def _fetch(url: str) -> tuple[bytes, int, str] | None:
    try:
        req = Request(url, headers={"User-Agent": "PathwaysProBot/2.0"})
        with urlopen(req, timeout=20) as resp:
            return resp.read(), getattr(resp, "status", 200), resp.headers.get_content_type()
    except URLError as exc:
        logger.warning("Failed fetch %s: %s", url, exc)
        return None


def crawl_university(config) -> list[RawPage]:
    allowed_domains = set(config["allowed_domains"])
    strip_params = set(config.get("strip_query_params", []))
    exclude_patterns = config.get("exclude_patterns", [])
    depth_limit = int(config.get("depth_limit", 3))
    max_pages = int(config.get("max_pages", 120))
    strategy = config.get("strategy", "auto")
    render_triggers = [s.lower() for s in config.get("render_triggers", RENDER_HINTS)]
    output_dir = Path(config.get("snapshot_dir", "snapshots")) / config["university_key"] / config.get("run_id", "latest")

    queue = deque((u, 0) for u in config["start_urls"])
    visited, pages = set(), []

    while queue and len(pages) < max_pages:
        url, depth = queue.popleft()
        if depth > depth_limit:
            continue
        normalized = normalize_url(url, strip_params)
        if normalized in visited:
            continue
        visited.add(normalized)
        if not is_allowed_domain(normalized, allowed_domains):
            pages.append(RawPage(url, normalized, normalized, "irrelevant", 0.0, [], [], datetime.now(timezone.utc), 0, "blocked", "", None, "", False, "domain_blocked", [normalized]))
            continue
        if any(p in normalized for p in exclude_patterns):
            continue

        fetched = _fetch(normalized)
        if not fetched:
            continue
        content, code, content_type = fetched
        fetched_at = datetime.now(timezone.utc)
        canonical = normalized
        breadcrumbs: list[str] = []
        discovered: list[str] = []
        needs_js = False
        page_type = "irrelevant"
        confidence = 0.0
        pdf_path = None

        if content_type == "application/pdf" or normalized.endswith(".pdf"):
            snapshot_path, digest = write_snapshot(content, output_dir, "pdf")
            pdf_path = snapshot_path
            page_type, confidence = "program_page", 0.65
        else:
            html = content.decode("utf-8", errors="ignore")
            m = re.search(r"<link[^>]*rel=['\"]canonical['\"][^>]*href=['\"]([^'\"]+)['\"]", html, re.I)
            if m:
                canonical = normalize_url(m.group(1), strip_params)
            parser = LinkParser(normalized)
            parser.feed(html)
            discovered = [normalize_url(h, strip_params) for h, _ in parser.links]
            needs_js = any(t in html.lower() for t in render_triggers)
            page_type, confidence = classify_page(normalized, html)
            snapshot_path, digest = write_snapshot(content, output_dir, "html")

            for link, text in parser.links:
                n = normalize_url(link, strip_params)
                if n not in visited and is_allowed_domain(n, allowed_domains):
                    if any(h in (text + " " + n).lower() for h in PROGRAM_HINTS) or depth < 1:
                        queue.append((n, depth + 1))

            if strategy in {"playwright_render", "api_harvest", "auto"} and needs_js and page_type == "listing_page" and not discovered:
                logger.info("JS-heavy listing detected for %s; fallback strategy=%s", normalized, strategy)

        pages.append(RawPage(url, normalized, canonical, page_type, confidence, breadcrumbs, discovered, fetched_at, code, content_type, snapshot_path, pdf_path, digest, needs_js, None, [canonical]))

    return pages
