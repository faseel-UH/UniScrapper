from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TraceBlock:
    url: str
    heading: str
    text: str


@dataclass
class RawPage:
    url: str
    normalized_url: str
    canonical_url: str | None
    page_type: str
    confidence: float
    breadcrumbs: list[str]
    discovered_links: list[str]
    fetched_at: datetime
    status_code: int
    content_type: str
    snapshot_path: str
    pdf_path: str | None
    snapshot_hash: str
    needs_js_render: bool = False
    blocked_reason: str | None = None
    source_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fetched_at"] = self.fetched_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RawPage":
        payload = dict(data)
        payload["fetched_at"] = datetime.fromisoformat(payload["fetched_at"])
        return cls(**payload)


@dataclass
class Program:
    source_id: str
    canonical_url: str
    name: str
    source_urls: list[str]
    last_scraped_at: datetime
    requirements_text: str = ""
    requirements_normalized: dict[str, Any] = field(default_factory=lambda: {"raw_bullets": []})
    program_summary: str | None = None
    degree_level: str | None = None
    degree_type: str | None = None
    study_mode: str | None = None
    duration_text: str | None = None
    duration_months: int | None = None
    duration_years: float | None = None
    delivery_location: str | None = None
    intake_terms: list[str] = field(default_factory=list)
    application_deadlines: list[str] = field(default_factory=list)
    tuition: dict[str, Any] = field(default_factory=dict)
    modules: dict[str, list[str]] = field(default_factory=dict)
    fit_signals: dict[str, list[str]] = field(default_factory=lambda: {"discipline_tags": [], "career_outcomes": []})
    trace: dict[str, list[TraceBlock]] = field(default_factory=lambda: {"requirements": [], "tuition": [], "modules": [], "deadlines": []})
    data_quality_flags: list[str] = field(default_factory=list)


@dataclass
class Department:
    source_id: str
    name: str
    source_urls: list[str]
    programs: list[Program] = field(default_factory=list)
    data_quality_flags: list[str] = field(default_factory=list)


@dataclass
class CrawlStats:
    pages_fetched: int = 0
    blocked_count: int = 0
    js_render_count: int = 0
    api_harvest_used: int = 0
    pdf_downloaded_count: int = 0
    domain_leakage_count: int = 0


@dataclass
class UniversityCatalog:
    source_id: str
    university_key: str
    name: str
    source_urls: list[str]
    departments: list[Department]
    last_scraped_at: datetime
    data_quality_flags: list[str] = field(default_factory=list)
    crawl_stats: CrawlStats = field(default_factory=CrawlStats)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["last_scraped_at"] = self.last_scraped_at.isoformat()
        for dept in data["departments"]:
            for program in dept["programs"]:
                program["last_scraped_at"] = program["last_scraped_at"].isoformat()
        return data


@dataclass
class ValidationReport:
    university_key: str
    valid_schema: bool
    errors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    percentages: dict[str, float] = field(default_factory=dict)
    top_missing_fields_frequency: dict[str, int] = field(default_factory=dict)
    worst_programs: list[dict[str, Any]] = field(default_factory=list)
    crawl_stats: dict[str, Any] = field(default_factory=dict)
    domain_leakage_check: int = 0
    dedupe_stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
