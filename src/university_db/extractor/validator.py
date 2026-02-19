from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from university_db.common.models import UniversityCatalog, ValidationReport

REQ_TOP = ["source_id", "university_key", "name", "source_urls", "departments", "last_scraped_at", "data_quality_flags", "crawl_stats"]


def _to_payload(catalog) -> dict[str, Any]:
    if isinstance(catalog, UniversityCatalog):
        return catalog.to_dict()
    if isinstance(catalog, dict):
        return catalog
    return json.loads(Path(catalog).read_text(encoding="utf-8"))


def validate(catalog) -> ValidationReport:
    payload = _to_payload(catalog)
    errors = [f"missing field: {f}" for f in REQ_TOP if f not in payload]

    programs = []
    depts = payload.get("departments", [])
    for d in depts:
        programs.extend(d.get("programs", []))

    programs_total = len(programs)
    counts = {
        "departments": len(depts),
        "programs_total": programs_total,
        "programs_with_requirements_text": sum(bool(p.get("requirements_text")) for p in programs),
        "programs_with_tuition": sum(bool(p.get("tuition")) for p in programs),
        "programs_with_deadlines": sum(bool(p.get("application_deadlines")) for p in programs),
        "programs_with_duration": sum(bool(p.get("duration_text")) for p in programs),
        "programs_with_modules": sum(bool(p.get("modules")) for p in programs),
    }
    percentages = {k: round((v / programs_total) * 100, 2) if programs_total else 0.0 for k, v in counts.items() if k.startswith("programs_with_")}

    miss_counter = Counter()
    worst = []
    seen = {}
    merged = 0
    for p in programs:
        sid = p.get("source_id", "")
        if sid in seen:
            merged += 1
        seen[sid] = p
        missing = 0
        for f in ["requirements_text", "tuition", "application_deadlines", "duration_text", "modules"]:
            if not p.get(f):
                miss_counter[f] += 1
                missing += 1
        worst.append({"canonical_url": p.get("canonical_url", ""), "flags": p.get("data_quality_flags", []), "missing_count": missing})

    worst = sorted(worst, key=lambda x: x["missing_count"], reverse=True)[:50]

    leakage = 0
    allowed_roots = set(payload.get("source_urls", []))
    for p in programs:
        for u in p.get("source_urls", []):
            if allowed_roots and not any(root.split("//", 1)[-1].split("/", 1)[0] in u for root in allowed_roots):
                leakage += 1

    report = ValidationReport(
        university_key=payload.get("university_key", "unknown"),
        valid_schema=len(errors) == 0,
        errors=errors,
        counts=counts,
        percentages=percentages,
        top_missing_fields_frequency=dict(miss_counter.most_common()),
        worst_programs=worst,
        crawl_stats=payload.get("crawl_stats", {}),
        domain_leakage_check=leakage,
        dedupe_stats={"duplicates_merged": merged},
    )
    return report
