from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


def normalize_url(url: str, strip_params: set[str] | None = None) -> str:
    strip_params = strip_params or set()
    parsed = urlparse(url.strip())
    query_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in strip_params]
    normalized = parsed._replace(
        scheme=parsed.scheme.lower() or "https",
        netloc=parsed.netloc.lower(),
        fragment="",
        query=urlencode(sorted(query_items)),
    )
    path = normalized.path or "/"
    normalized = normalized._replace(path=path.rstrip("/") or "/")
    return urlunparse(normalized)


def is_allowed_domain(url: str, allowed_domains: set[str]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def absolutize(base_url: str, href: str) -> str:
    return urljoin(base_url, href)
