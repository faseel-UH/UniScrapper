from __future__ import annotations

import hashlib


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_source_id(canonical_url: str) -> str:
    return sha256_text(canonical_url)
