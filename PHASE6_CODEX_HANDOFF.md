# Codex implementation / deployment handoff — Phase 6

**Target repository:** private `secured-innovations-cre-scout` under an authorized Secured Innovations GitHub account. **Do not create a public repository.** GitHub is connected, but no accessible repo was discovered when Phase 6 was packaged; repository creation was not available through the connected actions.

**Goal:** publish and run the provided Phase 6 regional GIS acquisition intelligence prototype; validate public source endpoints under live network conditions; configure persistent state and machine-only Sheets synchronization; report actual acceptance evidence.

## Codex instructions

1. Check target repo permissions and existing files before merging; do not overwrite user work. Import the *contents* of the ZIP into the correct directory, preserving `data/seed_phase3.csv`, `data/scout.sqlite`, and the historical `scout.py` gates. Use a feature branch/PR where repo policy requires.
2. Run `python -m unittest discover -s tests -v`. As initially supplied there are **23 offline tests**; all must pass without network.
3. Inspect `.github/workflows/scout-weekly.yml` for account policy, timezone and secret handling. Ensure the regional step triggers after the primary Philly scan and precedes Sheets sync. Do not grant more GitHub token permissions than persistence requires.
4. Test source connectivity with `python regional_parcels.py scan --limit 3` using a disposable SQLite DB first; check the Census geocoder matched street number, ZIP and state, and inspect live JSON metadata against the fields in `regional_parcels.py`. If the government API changed, repair the source mapping using the provider's *official* new endpoint and record the source migration.
5. Confirm the newest NJ parcel layer is `Parcels_Composite_NJ_WM/FeatureServer/0`; the old NJ service was retired March 11, 2026. Respect NJ Daniel's Law redactions. Never scrape around protected owner fields.
6. Run official GIS results as **evidence-only** and never automatically set recorded ownership verification, site-specific AADT, zoning, company expansion intent, availability, sale price or franchise approval. Preserve T-001 exclusion and T-002 acreage hold.
7. Confirm `output/regional_*.csv` presents unverified GIS candidate evidence and that identical twice-run source content generates no extra `phase6_events`. Test real network error handling and source-limit truncation.
8. Arrange durable history under an approved model: current GitHub workflow pushes `data/scout.sqlite` to default branch; if branch rules or write races prevent that, use a managed SQLite-compatible DB or another transactional store with documented recovery. Never declare unattended change tracking stable without a successful persistence/readback cycle.
9. Configure the existing project's spreadsheet with machine tabs `Phase6 GIS Observations`, `Phase6 GIS Changes`, and `Phase6 Source Health`, *already created* in the existing sheet. For independent GitHub writes, set encrypted `GOOGLE_SERVICE_ACCOUNT_JSON` and grant only the authorized project Sheet. Do not paste credential JSON into code, logs or this chat. Verify a first real append, then a second idempotent run.
10. Publish a deployment acceptance report with repo URL, commit SHA, GitHub Actions run URL, number of live source responses, source failures, genuine candidate observations, duplicate count, changes detected, SQLite persistence SHA/state, and confirmation of Sheets sync or explicit skipped status. Do not invent sample properties to satisfy counts.
11. Keep future brand order: Taco Bell, Sheetz, Bank of America. Extend automated **discovery** beyond Philadelphia permit feeds only after legally accessible government/authorized real estate sources have been selected, integration tested and independently scored.

## Source registry

See `output/regional_source_registry.csv` (government URLs; 7 jurisdictions). The public metadata was consulted in October 2026 but actual API execution could not be verified from the sandbox. Geocoded parcel candidates are *not* legal title or survey proofs.
