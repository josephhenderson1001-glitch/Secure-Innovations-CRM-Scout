# Secured Innovations Inc. — Phase 6 Regional CRE Intelligence Engine

**Release date:** October 23, 2026  
**Deployment:** Code packaged and **23 offline automated tests passed**. **Not independently cloud deployed.** A connected GitHub account exists, but no accessible repository has been found as of this release; a live public-source query and GitHub→Sheets authentication remain incomplete.

**Target priority order:** **1. Taco Bell → 2. Sheetz → 3. Bank of America**. Primary research counties: **Chester, Delaware, Montgomery, Bucks and Philadelphia**, Pennsylvania. Secondary coverage: **New Castle County, DE**, and New Jersey's **current state parcel composite**. This is **property research**, not brokerage, sale availability, company approval, or title evidence.

## What Phase 6 builds upon Phase 5

1. **Multi-region government GIS candidate matching**: `regional_parcels.py` connects candidate addresses to public ArcGIS parcel/assessment records in seven jurisdictional scopes (five PA, one DE, NJ statewide). It uses a Census address geocoder and point-in-polygon/near-point GIS lookups. Matches are **GIS candidates for human review**, never legal-survey matches.
2. **Persistent source change history**: Each considered property gets a dated GIS lookup snapshot; the first valid GIS snapshot and a change in the candidate attributes generate distinct review events. Duplicate identical candidate snapshots do not generate new events.
3. **Address and schema safeguards**: Geocoder address-number, state and ZIP mismatches are rejected; unrecognized GIS schemas, truncated response sets, network failures and ambiguous geocodes are explicitly surfaced. No GIS record automatically sets `recorded_owner_verified`, `parcel_id`, `officially_verified_aadt`, a zoning clearance or the sale status.
4. **NJ privacy boundaries**: The current NJGIS source redacts `OWNER_NAME` per Daniel's Law; the Phase 6 adapter does not request any owner/mailing fields from **any** source. Public recorded-deed ownership requires separate responsible legal diligence, not this GIS pass.
5. **Analyst watchlist import**: `watchlist_import.py` accepts documented candidate sites in the configured PA/DE/NJ counties, prevents repeated brand/address pairs, assigns stable watchlist IDs, and **never assumes that a property is listed or that a brand is expanding there**. Existing source material must be independently reviewed.
6. **GitHub Actions workflow**: Adds regional enrichment after the municipal permit scan and before optional Google Sheets synchronization. Errors remain visible in Actions, with reports uploaded even after failures. Data persistence still depends on `git push` or a managed database.
7. **Append-only Google Sheets machine data**: Adds machine-owned tabs `Phase6 GIS Observations`, `Phase6 GIS Changes`, `Phase6 Source Health` to `sheets_sync.py`. They are separate from analyst-controlled Property Register, Diligence Queue and Scorecard. The existing Google Sheet also has `Phase6 Deployment` and `Phase6 Source Registry` tabs.

## Files

| File | Function |
| --- | --- |
| `scout.py` | Phase 5 permits, baseline and human-reviewed lead changes |
| `regional_parcels.py` | Phase 6 regional ArcGIS candidate lookup, change log and review CSV exports |
| `watchlist_import.py` | Safe intake for sourced PA/DE/NJ watchlist sites |
| `sheets_sync.py` | Optional, credentialed append-only Google Sheets machine-tab sync |
| `.github/workflows/scout-weekly.yml` | Monday 8:00 AM ET scheduled and manually triggered workflow |
| `data/scout.sqlite` | Baseline SQLite state: 16 sites, zero live source observations |
| `data/seed_phase3.csv` | Provenance-preserving original research baseline |
| `data/phase6_watchlist_template.csv` | CSV schema for separately researched new potential locations |
| `output/regional_source_registry.csv` | Source provenance and unverified-title warnings |
| `output/regional_parcel_candidates.csv` | Latest per-lead GIS matching outcomes (initially empty) |
| `output/regional_gis_change_log.csv` | First observed/changed GIS reviews (initially empty) |
| `tests/test_phase6.py` | Eight regional and three watchlist/Sheets safety tests |
| `PHASE6_DEPLOYMENT_CHECKLIST.md` | Live go/no-go gates |
| `PHASE6_CODEX_HANDOFF.md` | Next Codex/repository instructions |

## Local verification

Python 3.11+:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scout.py report
python regional_parcels.py registry
python regional_parcels.py scan --offline --limit 8  # NO network, NO invented source records
python regional_parcels.py report
python sheets_sync.py --dry-run
```

To review newly sourced off-market candidates before ingestion:

```bash
python watchlist_import.py data/phase6_watchlist_template.csv --dry-run
# After filling with real addresses and public evidence URLs:
python watchlist_import.py data/phase6_watchlist_template.csv
```

To run the **first actual regional source call** from a network-enabled machine or private GitHub runner:

```bash
python scout.py scan --verify-limit 8
python regional_parcels.py scan --limit 16
python regional_parcels.py report
python sheets_sync.py --dry-run
```

Do not run the `scout.py scan --offline` simulated Philadelphia fixtures on the production SQLite file. The fixture contains invented permits for test use only. In contrast, `regional_parcels.py scan --offline` makes **zero source calls and writes zero GIS observations**.

## Independent deployment requirements

1. Create (or grant this connected GitHub account access to) a **private** repository, e.g. `secured-innovations-cre-scout`, then add the **contents** of this package to repository root. Import to Codex if preferred. Do not commit secrets.
2. Ensure GitHub Actions has been enabled for the repository, the default branch is correct, and `contents: write` permission allows SQLite history persistence. If branch protections block the persistence push, design and approve another durable store before declaring automation operational.
3. Trigger **Actions → Secured Innovations CRE — Weekly Live Scout → Run workflow**. Require unit tests, Philly permit source/fallback, GIS matching, durable SQLite write, and nonzero real run history to be visible. If one government source fails, the Action should show a warning/failure rather than claiming a complete scan.
4. For Google Sheets synchronization, use a secured Google service-account secret `GOOGLE_SERVICE_ACCOUNT_JSON`, share only the designated spreadsheet with that principal, and validate a real append to machine data tabs. **Never paste, commit or send service-account JSON through chat.** The existing ChatGPT Google Drive connection does not authorize a GitHub job.
5. Inspect all candidate IDs against the county recorders, municipal zoning/drive-through or gasoline-use rules, roadway access and official AADT station/year before any investment package or licensed property outreach.

Target spreadsheet (existing, owned by the project):  
<https://docs.google.com/spreadsheets/d/1g7KdL1N12iGVnLqhpDcAeir4x3PrmhcmFAHtpeICvJ0/edit>

## Specific known hard gates

- `T-001` **2023 MacDade Boulevard, Holmes, PA** is **EXCLUDED** from vacant Taco Bell search because it currently operates as Popeyes; never recycle it as a new vacant property.
- `T-002` **363 Wilmington Pike, Glen Mills, PA** remains **HOLD—PARCEL IDENTITY**; the marketed 1.2-acre claim is not reconciled to the separate 0.32-acre address/parcel indication. GIS candidate mapping **cannot** clear that discrepancy without recorded plats/deeds and survey/assemblage confirmation.
- Sheetz's preliminary physical preference is typically 1–3 acres with 18,000+ AADT, parking for 35–50 vehicles, compatible 24-hour gasoline zoning and utilities, **all independently verified per site** before presenting as suitable.

## Sources and integrity note

The seven ArcGIS layer URLs are enumerated in `regional_parcels.py` and `output/regional_source_registry.csv`; as-of October 23, 2026 their public documentation was checked. **Live GET/Query execution in GitHub has not yet been verified.** NJGIS explicitly notes that its composite boundaries are not legal title boundaries and certain owner data are redacted by law; do not try to reconstruct redacted NJ records.

The existing Monday ChatGPT research task is separate and remains scheduled. Phase 6 does not claim that GitHub itself is now running automatically.
