# Phase 5 go-live checklist — Secured Innovations Inc.

Snapshot: **October 23, 2026**. Checked items are supported by local tests or live connected-account metadata; they do **not** signify production deployment.

| Step | Outcome | Exit criterion |
| --- | --- | --- |
| Local baseline restored | PASS | Original 16 leads retained with historical gates |
| Source-event change history | PASS | Permit-status change recorded once without creating a new permit ID |
| Simulated data isolation | PASS | Offline fixtures do not appear in Google Sheets outbox |
| Safe brand priority | PASS | Taco Bell first, Sheetz second, Bank of America third |
| Hard exclusion / holds | PASS | EXCLUDED score 0; HOLD capped and never outreach-cleared |
| Unit tests | PASS | 12 of 12 offline tests |
| Google Sheet schema | PASS | New append-only machine tabs exist (no live events yet) |
| GitHub account connection | PASS | Account connection verified, no accessible repositories |
| Private GitHub repository | BLOCKED | User creates/grants repository, deployment files committed |
| First GitHub Actions live run | PENDING | Runner reaches Carto or ArcGIS and yields auditable source results |
| Public data endpoints | NOT NETWORK TESTED | Validate schema, request throttling and source warnings in actual runner |
| GitHub repo state persistence | PENDING | Successful `data/scout.sqlite` commit/push between two runs |
| Sheets service-account secret | OPTIONAL / PENDING | `GOOGLE_SERVICE_ACCOUNT_JSON` configured in GitHub Secrets; spreadsheet shared only with scoped service account |
| Remote Google Sheets idempotency | PENDING | Re-run same report twice and confirm zero duplicate keys |
| Investor-facing clearance | NOT MET | Deed, parcel boundaries, zoning, AADT and availability independently reviewed |

**Recommended go-live acceptance test**

1. Create **private** GitHub repository and push this package.
2. Trigger Actions manually (first run). Review job status, source count, `output/run_history.csv` and `weekly_report.md`.
3. If source errors occur, repair adapters based on response schema; do not classify partial results as an exhaustive market search.
4. Add Sheets service-account secret if desired. Confirm machine-run row and any true permit changes appear, with source URL and status, in the remote Sheet.
5. Trigger Actions again to verify no repeat permit events and persisted SQLite history.
6. Verify Monday 8:00 AM America/New_York schedule, allowing for GitHub Actions timing delays; monitor failures.

**Blocker at handoff:** there was no accessible GitHub repository, and no GitHub repository-creation action in the connected tool. This package is ready for repository creation/import, not yet hosted.
