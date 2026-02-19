# University DB v1 (Pathways Pro)

## Architecture

- Stage A crawler snapshots HTML/PDF pages and writes per-page metadata.
- Stage B extractor builds `University -> Departments -> Programs` and enriches each program from related admissions/fees/modules/deadlines pages.
- Validation creates actionable per-university coverage reports.

## Discovery strategies

- `html_crawl`: direct HTML crawling.
- `playwright_render`: fallback flag path for JS-heavy pages.
- `api_harvest`: hook point for capturing listing APIs (auto mode can switch).

Configured per adapter in `configs/adapters.yaml` via `discovery.strategy`.

## Outputs

- `outputs/<university_key>/catalog.json`
- `outputs/<university_key>/validation_report.json`
- `snapshots/<university_key>/<run_id>/*`
- `logs/<university_key>/<run_id>.log`

## Commands

```bash
PYTHONPATH=src python -m university_db.cli crawl --university_key mit --config configs/adapters.yaml --max-pages 60
PYTHONPATH=src python -m university_db.cli extract --university_key mit
PYTHONPATH=src python -m university_db.cli validate --input outputs/mit/catalog.json
PYTHONPATH=src python -m university_db.cli enrich --university_key mit --config configs/adapters.yaml --max-pages 60 --max-programs 25
```

## Assumptions

- Public pages only; login-gated content should be flagged (`auth_required`) when encountered.
- PDF extraction is placeholder text, still preserved in program trace/source URLs.
- Missing public fields are explicitly flagged in `data_quality_flags` and surfaced by validation report.
