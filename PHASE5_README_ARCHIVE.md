# Secured Innovations Inc. — Phase 5: Cloud Deployment & Persistent CRE Intelligence

**Release:** October 23, 2026 · **Status:** packaged and offline-tested, **not deployed** to an independently running cloud service.

Research priority: **1. Taco Bell → 2. Sheetz → 3. Bank of America**. This tool is commercial real-estate *signal intelligence*, not permission to act as a broker or evidence of brand approval. Geographic discovery in the standalone Python runner remains primarily **Philadelphia permits**; parcel and road-traffic enrichment applies to selected **Chester County** baseline sites. Independent multi-state listing discovery is **not implemented**.

## What Phase 5 adds

- GitHub Actions schedule at **8:00 AM America/New_York each Monday**, using GitHub's 2026 timezone-aware cron syntax. The run may be delayed by GitHub; it is not an exact-time SLA.
- A local **SQLite change-history database** that distinguishes first-observed public permit events from permit status/description changes and preserves historical property observations.
- **Two official Philadelphia public-source interfaces**: Carto SQL as primary and City ArcGIS permit layer as fallback. The backup field names were cross-checked against the City's published service metadata; **live API queries have not yet been tested** in this no-network runtime.
- Optional Google Sheets service-account synchronization to three dedicated *append-only machine tabs*: `Phase5 Permit Event History`, `Phase5 Collection Runs`, and `Phase5 Official Evidence`. No direct edit to the human-reviewed Property Register, Diligence Queue or Phase4 Scorecard.
- Remote synchronization is **idempotent by stable event key**. When an append completes but its response fails, a later run checks the remote keys before attempting the append again.
- Safe fixture isolation: synthetic local permit fixtures are excluded from the Google Sheets sync and live-run outbox.
- Degraded source-run reporting and downloadable GitHub Actions artifacts even when the live scan fails. Google Sheets sync/push failures are visible in the final workflow status.
- **12 offline tests passed** on October 23, 2026, covering baseline, hard holds, duplicates, changed permit statuses, ArcGIS timestamps, synthetic-fixture exclusion, and outgoing row-key deduplication.

## Handoff and deployment steps

### 1. Create private repository (not yet done)

In your connected GitHub account, create a **private** repository named `secured-innovations-cre-scout` (or another suitable name). As of the build, GitHub was connected but **no accessible repository existed**, and the connected repository tools did not expose repository creation.

If you use a local terminal with Git installed, open the extracted folder and push its **contents** (not the containing parent folder):

```bash
git init
git add .
git commit -m "feat: Phase 5 CRE property research bot"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_LOGIN>/secured-innovations-cre-scout.git
git push -u origin main
```

**The GitHub URL above is a placeholder, not a real created repository link.** Alternatively, once the private repository exists, use Codex or the connected GitHub app to import the Phase 5 package into that repository.

### 2. Enable GitHub Actions and run an initial live scan

- In repository **Settings → Actions**, enable Actions and allow the workflow's `contents: write` permission, or configure an approved alternative for database persistence if your branch is protected.
- In **Actions → Secured Innovations CRE — Weekly Live Scout → Run workflow**, start a manual test. The workflow will install dependencies, run 12 tests, query the public sources, and upload `output/` as an Actions artifact whether the source call succeeds or fails.
- Review the latest job run. `COMPLETED` means all implemented collectors returned without raised errors. `PARTIAL—SOURCE WARNINGS` means some records may be missing. **Neither status means deeds, zoning, access or brand approvals were verified.**
- Check `output/weekly_report.md`, `output/run_history.csv`, `output/permit_signal_changes.csv`, `output/official_evidence_review.csv`, and the Actions artifact before any property presentation.
- The workflow attempts to commit its updated `data/scout.sqlite` and `output/` to the repository. If branch protection or permissions reject the push, no reliable cloud history has been established; configure an approved durable database or review/adjust repository permissions.

### 3. Optional Google Sheets synchronization (not yet authenticated)

An existing live spreadsheet has the required three Phase 5 machine tabs:

<https://docs.google.com/spreadsheets/d/1g7KdL1N12iGVnLqhpDcAeir4x3PrmhcmFAHtpeICvJ0/edit>

To enable **independent GitHub-to-Google-Sheets** writes:

1. In your own Google Cloud project, enable Google Sheets API and create a restricted service account. For this prototype the adapter uses service-account JSON credentials; a workload identity/OIDC configuration is preferable for mature deployment.
2. Share **only this one spreadsheet** with the service account's `client_email`, granting Editor permission. Google Sheets permissions are at file level; the adapter's code only targets the machine tabs, but the account technically has full editor permissions. Restrict and monitor this credential.
3. Store the entire downloaded service-account JSON **only** as the GitHub Actions encrypted repository secret named `GOOGLE_SERVICE_ACCOUNT_JSON`. Do **not** commit, email or paste credential JSON into chat or logs.
4. Re-run the Action. The workflow already targets the existing spreadsheet ID. Verify the machine-tab rows in the live sheet; the `Phase5 Collection Runs` tab should show a `LIVE` run with the actual collection status.
5. If the secret is absent, the workflow intentionally **skips sync** and leaves the report in GitHub artifacts; it will not claim that Google Sheets was updated.

The service-account method is distinct from ChatGPT's existing Google Drive connection. A connected ChatGPT Drive account does **not** automatically authorize GitHub Actions.

### 4. Validate the first genuine weekly report

For a property to advance from discovery signal to investor dossier, verify **official parcel/folio + legal boundaries, recorded ownership/deed, current marketing/availability, municipal permitted use, access/traffic station and year, utility constraints and brand site criteria**. Have appropriately licensed real estate professionals coordinate outreach or transactions.

**Hard stops maintained:** `T-001` 2023 MacDade Blvd, Holmes remains **EXCLUDED—OCCUPIED**. `T-002` 363 Wilmington Pike, Glen Mills remains **HOLD—PARCEL IDENTITY** until marketed 1.2 acres are reconciled with conflicting records. `HOLD` caps preliminary screen score; no score authorizes outreach.

## Offline local test / demonstration

Python **3.11+**; the core scout is standard-library-only. Dependencies in `requirements.txt` are only for Google service-account token acquisition.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scout.py report
python sheets_sync.py --dry-run
```

To simulate deduplication without network, run `python scout.py scan --offline` **only on a disposable copy of the database**. Offline fixtures intentionally contain fabricated example permits. Do not use a demo-run DB for production, and do not represent demo signals as real findings.

You can also perform a local live scan from a network-enabled machine:

```bash
python scout.py scan --verify-limit 8
# After configuring GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID locally:
python sheets_sync.py
```

The GitHub runner uses `America/New_York` time-zone-aware scheduling, and its stored SQLite file is its persistent history only when git push completes. For larger use, migrate state to a managed database before increasing request volume.

## Component inventory

| Component | Purpose |
| --- | --- |
| `scout.py` | Baseline importer, permit data collectors, GIS/traffic candidate enrichment, SQLite observation history, CSV/Markdown output |
| `sheets_sync.py` | Optional authenticated Google Sheets append-only machine-data sync |
| `.github/workflows/scout-weekly.yml` | Tests, timezone-aware schedule, source collection, artifacts, database persistence, optional Sheets sync |
| `data/seed_phase3.csv` | 16 original, not-yet-deed-verified research leads |
| `data/scout.sqlite` | Initial persistent baseline with zero live permit signals; **not production cloud state yet** |
| `fixtures/philadelphia_permits_fixture.json` | Deliberately fictitious test-only data |
| `tests/` | 12 unit tests for deduplication, gates, history, sync filtering |
| `output/` | Human-review report and machine-export CSVs (at initial baseline, zero live source events) |
| `DEPLOYMENT_CHECKLIST.md` | Release controls, permissions and acceptance criteria |

## Verified reference URLs (documentation; not proof live connectivity)

- GitHub Actions schedule timezone: <https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule>
- GitHub 2026 timezone feature: <https://github.blog/changelog/2026-03-19-github-actions-late-march-2026-updates/>
- Google Sheets append API: <https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append>
- Philadelphia building/zoning permit dataset: <https://opendataphilly.org/datasets/licenses-and-inspections-building-and-zoning-permits/>
- Philadelphia ArcGIS permit layer: <https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/PERMITS/FeatureServer/0>
- Chester parcel GIS: <https://mapservices.pasda.psu.edu/server/rest/services/pasda/ChesterCounty/MapServer/11>
- PennDOT TIRe: <https://gis.penndot.pa.gov/gis/rest/services/tds/tire/MapServer/3>

## Scope and compliance

This project provides market intelligence and **requires verification**, not brokerage or automated owner solicitation. Recorded owners must be validated against official land records; a GIS assessed owner is not a title opinion. A nearby PennDOT road segment `CUR_AADT` value is not a validated entrance traffic count. A planning/permit signal does not prove a site is vacant, on the market or likely to be approved for Taco Bell, Sheetz or Bank of America. Expansion into New Jersey and Delaware at autonomous feed level, external commercial listing subscriptions, and licensed-deal handoffs remain follow-on integrations.
