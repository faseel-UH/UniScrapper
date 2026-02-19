from university_db.crawler import crawl_university
from university_db.extractor import extract_programs, normalize_requirements, validate

__all__ = ["crawl_university", "extract_programs", "normalize_requirements", "validate"]
