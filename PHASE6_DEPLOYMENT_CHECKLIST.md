# Phase 6 live deployment / acceptance checklist

Date: 2026-10-23. State: **PACKAGE READY, NOT DEPLOYED**.

## Before publication

- [x] Keep existing 16 leads, property IDs and source links without marking old listings as new
- [x] Preserve T-001 excluded and T-002 held, with no auto-approval via GIS
- [x] Add official regional GIS source registry for PA Chester, Delaware, Montgomery, Bucks, Philadelphia; DE New Castle; NJ statewide
- [x] Require geocoder address match and official GIS query metadata
- [x] Reject ambiguous/truncated or schema-changed results and record warnings
- [x] Add separate append-only GIS observations and review change log
- [x] Allow user-sourced PA/DE/NJ watchlist import without falsely claiming active sale
- [x] Integrate Phase 6 Python invocation in GitHub workflow
- [x] Verify **23 tests pass** on a sandbox local run
- [x] Create 5 additional native Google Sheets tabs; initial histories empty

## Required to declare live

- [ ] GitHub private repo `secured-innovations-cre-scout` exists and GitHub connection has access
- [ ] Phase 6 source files committed to default branch with visible commit SHA
- [ ] Repository Actions enabled and `workflow_dispatch` execution returned a workflow run ID
- [ ] Tests pass in the hosted Actions environment
- [ ] Philadelphia permit feed and at least one real GIS endpoint respond successfully
- [ ] Regional run writes source response status and candidate evidence with real government URLs; GIS results reviewed for false address matches
- [ ] Workflow artifacts contain `weekly_report.md`, `regional_source_registry.csv`, `regional_parcel_candidates.csv`, `regional_gis_change_log.csv`, and `regional_source_health.csv`
- [ ] A second weekly/triggered run preserves the SQLite prior state, and unchanged GIS records produce **zero** fake change events
- [ ] `git push` or approved managed database persistence confirmed; fallback if branch protection blocks
- [ ] Google Sheets sync uses a restricted authenticated service account and appends to dedicated machine tabs, or is expressly marked skipped
- [ ] Due diligence on deeds, exact parcels, franchise/operator criteria, zoning, title, access, AADT and gasoline operations still marked separately **unverified**
- [ ] Source failures visible in the job summary; alerts configured for failed workflow runs

## Controls

No commercial listing feed integration is claimed. No historical marketing lead is automatically promoted to NEWLY LISTED from GIS records. No automated contact, brokerage, owner solicitations, offers, compensation agreements or brand outreach.

## Test commands

```bash
python -m unittest discover -s tests -v
python regional_parcels.py registry
python regional_parcels.py scan --offline --limit 8
python regional_parcels.py report
python sheets_sync.py --dry-run
# Network-enabled only after repo creation:
python regional_parcels.py scan --limit 16
```
