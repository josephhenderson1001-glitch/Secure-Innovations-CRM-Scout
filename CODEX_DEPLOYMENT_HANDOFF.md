# Codex handoff — deploy Secured Innovations Phase 5

Use this complete project folder as the starting working tree. The user wants a production-bound, PRIVATE GitHub Actions CRE research runner for Taco Bell, Sheetz and Bank of America, in that order. Existing `data/scout.sqlite` has 16 baseline leads; it does NOT have any live newly discovered events. Preserve historical gates and avoid creating fictional property data.

## Guardrails

- **Do not** create or expose a public repository. Do not publish property-owner research publicly.
- No credentials are included. Never commit a Google service-account JSON key.
- **Do not** call a public-data API response official ownership/title verification, site-specific AADT or zoning approval without additional source-specific review.
- The Google Sheets ID targets an existing user's spreadsheet; do not create a second copy unless instructed.
- The score may never override a `HOLD` or `EXCLUDED` gate. T-001 is an occupied Popeyes; T-002 has unresolved advertised-footprint discrepancy.
- Do not contact property owners, brokers, tenants, or brands or perform negotiation or licensed brokerage acts.

## Deployment tasks once an accessible private repo exists

1. Read `README.md` and `DEPLOYMENT_CHECKLIST.md`. Run `python -m unittest discover -s tests -v` and verify 12/12 passing.
2. Commit the entire folder contents into a new/existing **private** repository. Preserve `.github/workflows/scout-weekly.yml` on the repository default branch.
3. Configure GitHub Actions appropriate write access or an external durable state destination. Trigger the live workflow via manual `workflow_dispatch`.
4. Inspect actual Carto/ArcGIS, PASDA and PennDOT responses. Repair current API field mappings and date conversions as necessary. Any data-source error must remain a visible partial run, not an invented success.
5. Verify `data/scout.sqlite` actually persists after the run and a subsequent run adds no duplicate permits.
6. Optional: enable Sheets sync through service-account secret `GOOGLE_SERVICE_ACCOUNT_JSON`; share only the target spreadsheet with the service account. Audit its remote writes (dedicated Phase 5 machine tabs ONLY). The existing ChatGPT Google Drive connector is not a secret for GitHub.
7. Leave human-verified title/zoning/traffic/availability gates unmodified absent primary-source record evidence.
8. Produce a deployment status summary that separates completed tasks, actual first live API findings, remaining blockers, and the repository/workflow URLs returned by GitHub. Never claim production is active without a successful real workflow run.

## Acceptance definition

Phase 5 is **LIVE** only after: repository exists and is private; workflow source scan runs to completion or explicitly reports degraded sources; durable SQLite state (or replacement state store) demonstrably survives across runs; optional Sheets integration clearly marked enabled or disabled; and evidence has no fictitious data in production.
