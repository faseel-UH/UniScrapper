from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urljoin
import json
import re

from university_db.common.hashing import stable_source_id
from university_db.common.models import Department, Program, RawPage, TraceBlock, UniversityCatalog
from university_db.common.url_utils import is_allowed_domain, normalize_url

ENRICH_LINK_KEYWORDS = [
    "entry requirements", "admissions", "how to apply", "fees", "tuition", "funding", "scholarships",
    "course structure", "modules", "curriculum", "syllabus", "deadlines", "key dates", "intakes", "start date"
]
ENRICH_URL_KEYWORDS = ["admissions", "apply", "requirements", "fees", "tuition", "funding", "modules", "course-structure", "curriculum", "syllabus", "deadlines", "dates", "intakes"]


def discover_enrichment_links(html: str, base_url: str, allowed_domains: set[str], max_related_pages: int = 5) -> list[str]:
    links = re.findall(r"<a[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", html, flags=re.I | re.S)
    found: list[str] = []
    for href, text in links:
        t = re.sub(r"<[^>]+>", "", text).strip().lower()
        url = normalize_url(href if href.startswith("http") else urljoin(base_url, href))
        if not is_allowed_domain(url, allowed_domains):
            continue
        if any(k in t for k in ENRICH_LINK_KEYWORDS) or any(k in url.lower() for k in ENRICH_URL_KEYWORDS):
            found.append(url)
        if len(found) >= max_related_pages:
            break
    return list(dict.fromkeys(found))


def _extract_json_ld(html: str) -> dict:
    out = {}
    for chunk in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, flags=re.I | re.S):
        try:
            payload = json.loads(chunk.strip())
        except Exception:
            continue
        if isinstance(payload, dict):
            out.update(payload)
    return out


def _extract_label(html: str, label: str) -> str | None:
    pat = rf"{label}\s*</[^>]+>\s*<[^>]+>(.*?)</"
    m = re.search(pat, html, flags=re.I | re.S)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    m2 = re.search(rf"{label}[:\s]+([^<\n]+)", re.sub(r"<[^>]+>", "\n", html), flags=re.I)
    return m2.group(1).strip() if m2 else None


def normalize_requirements(program) -> Program:
    text = program.requirements_text or ""
    bullets = [line.strip("•- ") for line in text.splitlines() if line.strip()]
    normalized = {"raw_bullets": bullets, "english_tests": []}
    gpa_match = re.search(r"gpa\s*(?:of)?\s*([0-4](?:\.\d+)?)", text, re.IGNORECASE)
    normalized["min_gpa"] = float(gpa_match.group(1)) if gpa_match else None
    for exam in ["IELTS", "TOEFL", "PTE"]:
        match = re.search(rf"{exam}[^\d]*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if match:
            normalized["english_tests"].append({"name": exam, "min_score": match.group(1)})
    program.requirements_normalized = normalized
    if text and not bullets:
        program.data_quality_flags.append("requirements_unparsed")
    return program


def _fetch_text(url: str) -> tuple[str, bool]:
    try:
        req = Request(url, headers={"User-Agent": "PathwaysProBot/2.0"})
        with urlopen(req, timeout=20) as r:
            body = r.read()
            ctype = r.headers.get_content_type()
            if ctype == "application/pdf" or url.lower().endswith(".pdf"):
                return f"PDF placeholder text from {url}", True
            return body.decode("utf-8", errors="ignore"), False
    except URLError:
        return "", False


def _merge_priority(program: Program, field: str, value, priority: int, priorities: dict[str, int]):
    if value is None or value == "" or value == []:
        return
    if priorities.get(field, 999) >= priority:
        setattr(program, field, value)
        priorities[field] = priority


def extract_programs(raw_pages) -> UniversityCatalog:
    if not raw_pages:
        raise ValueError("raw_pages cannot be empty")
    first = raw_pages[0]
    university_key = first.normalized_url.split("//", 1)[-1].split(".")[-2]
    allowed_domains = {first.normalized_url.split('/')[2]}
    uni_url = first.canonical_url or first.normalized_url
    depts: dict[str, Department] = {}

    for raw in raw_pages:
        if raw.page_type not in {"program_page", "listing_page"}:
            continue
        canonical = normalize_url(raw.canonical_url or raw.normalized_url)
        dept_name = raw.breadcrumbs[0] if raw.breadcrumbs else "General"
        dept = depts.setdefault(dept_name, Department(stable_source_id(f"{uni_url}#{dept_name.lower()}"), dept_name, [uni_url]))
        if raw.page_type == "listing_page":
            continue

        html = Path(raw.snapshot_path).read_text(encoding="utf-8", errors="ignore") if raw.content_type != "application/pdf" else ""
        json_ld = _extract_json_ld(html)
        name = re.sub(r"<[^>]+>", "", re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.I | re.S).group(1)).strip() if re.search(r"<h1[^>]*>.*?</h1>", html, flags=re.I | re.S) else canonical
        p = Program(source_id=stable_source_id(canonical), canonical_url=canonical, name=name, source_urls=[canonical], last_scraped_at=raw.fetched_at)
        priorities: dict[str, int] = {}

        p.program_summary = _extract_label(html, "summary") or _extract_label(html, "overview")
        p.degree_level = _extract_label(html, "degree level") or json_ld.get("educationalLevel")
        p.degree_type = _extract_label(html, "award") or _extract_label(html, "degree")
        p.study_mode = _extract_label(html, "study mode")
        p.duration_text = _extract_label(html, "duration")
        if p.duration_text:
            m = re.search(r"(\d+(?:\.\d+)?)\s*year", p.duration_text, re.I)
            if m:
                p.duration_years = float(m.group(1)); p.duration_months = int(float(m.group(1))*12)
            m2 = re.search(r"(\d+)\s*month", p.duration_text, re.I)
            if m2:
                p.duration_months = int(m2.group(1)); p.duration_years = round(int(m2.group(1))/12, 2)
        p.delivery_location = _extract_label(html, "location") or _extract_label(html, "campus")

        req_text = _extract_label(html, "entry requirements") or _extract_label(html, "requirements") or ""
        p.requirements_text = req_text
        if req_text:
            p.trace["requirements"].append(TraceBlock(canonical, "Entry requirements", req_text))

        fee_text = _extract_label(html, "tuition") or _extract_label(html, "fees")
        if fee_text:
            p.tuition = {"raw": fee_text}
            p.trace["tuition"].append(TraceBlock(canonical, "Fees", fee_text))

        deadline = _extract_label(html, "deadline") or _extract_label(html, "key dates")
        if deadline:
            p.application_deadlines = [deadline]
            p.trace["deadlines"].append(TraceBlock(canonical, "Deadlines", deadline))

        modules_text = _extract_label(html, "modules") or _extract_label(html, "course structure")
        if modules_text:
            p.modules = {"general": [modules_text]}
            p.trace["modules"].append(TraceBlock(canonical, "Modules", modules_text))

        related = discover_enrichment_links(html, canonical, allowed_domains)
        for rurl in related:
            txt, is_pdf = _fetch_text(rurl)
            if not txt:
                continue
            p.source_urls.append(rurl)
            priority_map = {"requirements": 1, "tuition": 0, "modules": 0}
            if is_pdf:
                p.data_quality_flags.append("pdf_only")
            req = _extract_label(txt, "entry requirements") or (_extract_label(txt, "requirements") if not is_pdf else txt[:1000])
            fees = _extract_label(txt, "tuition") or _extract_label(txt, "fees")
            mods = _extract_label(txt, "modules") or _extract_label(txt, "curriculum")
            if req:
                _merge_priority(p, "requirements_text", req, 1 if "admission" in rurl else 2, priorities)
                p.trace["requirements"].append(TraceBlock(rurl, "Requirements", req[:1000]))
            if fees:
                _merge_priority(p, "tuition", {"raw": fees}, 0 if "fee" in rurl or "tuition" in rurl else 1, priorities)
                p.trace["tuition"].append(TraceBlock(rurl, "Fees", fees[:1000]))
            if mods:
                _merge_priority(p, "modules", {"general": [mods]}, 0 if "module" in rurl or "structure" in rurl else 1, priorities)
                p.trace["modules"].append(TraceBlock(rurl, "Modules", mods[:1000]))

        normalize_requirements(p)
        if raw.needs_js_render:
            p.data_quality_flags.append("needs_js_render")
        if raw.confidence < 0.6:
            p.data_quality_flags += ["low_confidence_page", "requirements_unparsed"]
        if not p.requirements_text:
            p.data_quality_flags.append("requirements_unparsed")
        if not p.application_deadlines:
            p.data_quality_flags.append("missing_deadline")
        if not p.tuition:
            p.data_quality_flags.append("missing_tuition")
        if not p.duration_text:
            p.data_quality_flags.append("missing_duration")
        p.source_urls = list(dict.fromkeys(p.source_urls))
        dept.programs.append(p)

    catalog = UniversityCatalog(
        source_id=stable_source_id(uni_url),
        university_key=university_key,
        name=university_key.upper(),
        source_urls=[uni_url],
        departments=list(depts.values()),
        last_scraped_at=datetime.now(timezone.utc),
    )
    return catalog
