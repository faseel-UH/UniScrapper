from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from university_db.common.models import CrawlStats, RawPage
from university_db.crawler import crawl_university
from university_db.extractor import extract_programs, validate


def _load(path: str) -> dict:
    txt = Path(path).read_text(encoding="utf-8")
    return json.loads(txt)


def _adapter_cfg(university_key: str, config: str) -> dict:
    adapters = _load(config)
    defaults = adapters.get("defaults", {})
    uni = adapters["universities"][university_key]
    merged = {**defaults, **uni}
    merged["discovery"] = {**defaults.get("discovery", {}), **uni.get("discovery", {})}
    return merged


def _run_paths(university_key: str) -> tuple[str, Path, Path, Path]:
    run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    output_dir = Path("outputs") / university_key
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots = Path("snapshots") / university_key / run_id
    snapshots.mkdir(parents=True, exist_ok=True)
    log_path = Path("logs") / university_key
    log_path.mkdir(parents=True, exist_ok=True)
    return run_id, output_dir, snapshots, log_path / f"{run_id}.log"


def run_crawl(args):
    cfg = _adapter_cfg(args.university_key, args.config)
    run_id, output_dir, snapshot_dir, log_file = _run_paths(args.university_key)
    crawl_cfg = {
        "university_key": args.university_key,
        "start_urls": cfg["start_urls"],
        "allowed_domains": cfg["allowed_domains"],
        "exclude_patterns": cfg.get("exclude_patterns", []),
        "strip_query_params": cfg.get("strip_query_params", []),
        "strategy": cfg.get("discovery", {}).get("strategy", "auto"),
        "render_triggers": cfg.get("render_triggers", []),
        "depth_limit": args.depth,
        "max_pages": args.max_pages,
        "snapshot_dir": str(snapshot_dir.parent.parent),
        "run_id": run_id,
    }
    pages = crawl_university(crawl_cfg)
    Path(log_file).write_text(f"run_id={run_id}\npages={len(pages)}\n", encoding="utf-8")
    raw_path = output_dir / "raw_pages.json"
    raw_path.write_text(json.dumps([p.to_dict() for p in pages], indent=2), encoding="utf-8")
    print(str(raw_path))


def run_extract(args):
    output_dir = Path("outputs") / args.university_key
    raw_path = Path(args.input or output_dir / "raw_pages.json")
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    pages = [RawPage.from_dict(item) for item in payload]
    if pages:
        catalog = extract_programs(pages)
    else:
        from university_db.common.hashing import stable_source_id
        from university_db.common.models import UniversityCatalog
        catalog = UniversityCatalog(
            source_id=stable_source_id(f"https://{args.university_key}.invalid"),
            university_key=args.university_key,
            name=args.university_key.upper(),
            source_urls=[f"https://{args.university_key}.invalid"],
            departments=[],
            last_scraped_at=datetime.utcnow(),
            data_quality_flags=["crawl_empty"],
        )
    stats = CrawlStats(
        pages_fetched=len(pages),
        blocked_count=sum(1 for p in pages if p.blocked_reason),
        js_render_count=sum(1 for p in pages if p.needs_js_render),
        api_harvest_used=0,
        pdf_downloaded_count=sum(1 for p in pages if p.pdf_path),
        domain_leakage_count=sum(1 for p in pages if p.blocked_reason == "domain_blocked"),
    )
    catalog.crawl_stats = stats
    out = Path(args.output or output_dir / "catalog.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(catalog.to_dict(), indent=2), encoding="utf-8")
    print(str(out))


def run_validate(args):
    report = validate(args.input)
    out = Path(args.output or Path(args.input).with_name("validation_report.json"))
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(str(out))


def run_enrich(args):
    run_crawl(args)
    args.input = str(Path("outputs") / args.university_key / "raw_pages.json")
    args.output = str(Path("outputs") / args.university_key / "catalog.json")
    run_extract(args)
    args.input = args.output
    args.output = str(Path("outputs") / args.university_key / "validation_report.json")
    run_validate(args)


def main() -> None:
    parser = argparse.ArgumentParser(prog="university-db")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn in [("crawl", run_crawl), ("enrich", run_enrich)]:
        c = sub.add_parser(name)
        c.add_argument("--university_key", required=True)
        c.add_argument("--config", default="configs/adapters.yaml")
        c.add_argument("--depth", type=int, default=3)
        c.add_argument("--max-pages", type=int, default=120)
        c.add_argument("--max-programs", type=int, default=0)
        c.set_defaults(func=fn)

    e = sub.add_parser("extract")
    e.add_argument("--university_key", required=True)
    e.add_argument("--input", default=None)
    e.add_argument("--output", default=None)
    e.set_defaults(func=run_extract)

    v = sub.add_parser("validate")
    v.add_argument("--input", required=True)
    v.add_argument("--output", default=None)
    v.set_defaults(func=run_validate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
