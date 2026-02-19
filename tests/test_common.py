from datetime import datetime, timezone

from university_db.common.hashing import stable_source_id
from university_db.common.models import UniversityCatalog
from university_db.common.url_utils import normalize_url
from university_db.extractor.pipeline import discover_enrichment_links
from university_db.extractor.validator import validate


def test_canonical_url_normalization():
    assert normalize_url("HTTPS://Example.edu/programs/?utm_source=x&id=1#section", {"utm_source"}) == "https://example.edu/programs?id=1"


def test_source_id_determinism():
    u = "https://example.edu/program/msc-ai"
    assert stable_source_id(u) == stable_source_id(u)


def test_link_keyword_matching_for_enrichment_discovery():
    html = '<a href="/admissions">Entry requirements</a><a href="/about">About</a>'
    links = discover_enrichment_links(html, "https://example.edu/program", {"example.edu"}, max_related_pages=5)
    assert "https://example.edu/admissions" in links
    assert all("about" not in l for l in links)


def test_validation_report_has_required_keys():
    catalog = UniversityCatalog(
        source_id="sid",
        university_key="u",
        name="Uni",
        source_urls=["https://example.edu"],
        departments=[],
        last_scraped_at=datetime.now(timezone.utc),
        data_quality_flags=[],
    )
    catalog.crawl_stats.pages_fetched = 0
    report = validate(catalog).to_dict()
    for key in ["counts", "percentages", "top_missing_fields_frequency", "worst_programs", "crawl_stats", "domain_leakage_check", "dedupe_stats"]:
        assert key in report
