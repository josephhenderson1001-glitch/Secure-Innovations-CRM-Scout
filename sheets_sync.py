#!/usr/bin/env python3
"""Optional *append-only* Google Sheets adapter for Phase 5 CRE signal data.

Writes ONLY three dedicated machine-owned event tabs. Does not edit analyst
Property Register, Scorecard or Diligence Queue, does not imply verified deals.

Auth: GOOGLE_SERVICE_ACCOUNT_JSON as a GitHub Actions secret, GOOGLE_SHEET_ID.
Never store the service-account secret in the repository or outputs.
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from scout import DB, connect

SHEETS_API = 'https://sheets.googleapis.com/v4/spreadsheets'
HEADERS = {
    'Phase5 Permit Event History': [
        'Event Key', 'Permit ID', 'Change Type', 'Detected UTC', 'Government Event Date',
        'Address', 'Permit Status', 'Brand Hint (Not Approved)', 'Activity Summary',
        'Source URL', 'Evidence Level'],
    'Phase5 Collection Runs': [
        'Run Key', 'Started UTC', 'Finished UTC', 'Mode', 'Collection Status',
        'New Permit Signals', 'Changed Leads', 'Source Warnings', 'Evidence Level'],
    'Phase5 Official Evidence': [
        'Evidence Key', 'Lead ID', 'Checked UTC', 'Public Source', 'Record Type',
        'Evidence Status', 'Source URL', 'Evidence Level'],
    'Phase6 GIS Observations': [
        'Observation Key','Lead ID','Jurisdiction','Checked UTC','Result','Candidate Count',
        'Candidates JSON (IDs/acreage/address only)','Geocode Status','Source URL','Warning','Review Requirement'],
    'Phase6 GIS Changes': [
        'Change Key','Lead ID','First Seen UTC','Change Type','Status','Source URL'],
    'Phase6 Source Health': [
        'Health Key','Run UTC','Jurisdiction','Source','Status','Checked Leads',
        'Matched Leads','Warnings','Source URL'],
}


def is_fixture(url):
    return (url or '').lower().startswith('fixture:')


def outbox(db):
    """Stable, idempotent row keys; public-source results remain UNVERIFIED."""
    events=[]
    for r in db.execute('SELECT * FROM signal_observations ORDER BY id'):
        if is_fixture(r['evidence_url']):
            continue
        events.append([
            f"{r['signal_id']}:{r['fingerprint'][:24]}", r['signal_id'],
            r['change_type'], r['detected_utc'], r['event_date'] or '',
            r['address'] or '', r['status'] or '', r['hint'] or '',
            (r['activity'] or '')[:2500], r['evidence_url'] or '',
            'MUNICIPAL ACTIVITY SIGNAL—NOT PROPERTY AVAILABILITY'])
    runs=[]
    for r in db.execute('SELECT * FROM runs ORDER BY run_id'):
        if r['mode'] != 'LIVE':
            continue
        warnings=json.loads(r['warnings_json'] or '[]')
        runs.append([f"{r['started_utc']}:{r['run_id']}",
            r['started_utc'],r['finished_utc'] or '',r['mode'],r['status'] or '',
            r['total_new_signals'] or 0,r['total_changed_leads'] or 0,
            '; '.join(str(x) for x in warnings)[:3000],
            'COLLECTION RUN; SOURCE COMPLETENESS NOT GUARANTEED'])
    evidence=[]
    for r in db.execute('SELECT * FROM research_evidence ORDER BY evidence_id'):
        if is_fixture(r['source_url']):
            continue
        evidence.append([f"{r['evidence_id']}:{r['lead_id']}:{r['checked_utc']}",
             r['lead_id'],r['checked_utc'],r['source'],r['record_type'],
             r['status'],r['source_url'] or '',
             'UNREVIEWED PUBLIC-DATA CANDIDATE; NOT DEED/TITLE/ZONING/AADT CLEARANCE'])
    # Phase 6 machine data remains distinct from the analyst-maintained master register.
    # Never represent GIS candidates as legal parcels, proof of a current deed, or active listings.
    tables={'Phase5 Permit Event History':events,
            'Phase5 Collection Runs':runs,'Phase5 Official Evidence':evidence,
            'Phase6 GIS Observations':[], 'Phase6 GIS Changes':[], 'Phase6 Source Health':[]}
    tables_exist={str(r[0]) for r in db.execute('SELECT name FROM sqlite_master WHERE type="table"')}
    if 'phase6_snapshots' in tables_exist:
        for r in db.execute('SELECT * FROM phase6_snapshots ORDER BY id'):
            if is_fixture(r['source_url']):continue
            candidates=json.loads(r['candidates_json'] or '[]')
            tables['Phase6 GIS Observations'].append([
                f"P6:SNAP:{r['lead_id']}:{r['id']}",r['lead_id'],r['jurisdiction'],r['checked_utc'],
                r['result'],len(candidates),json.dumps(candidates,sort_keys=True)[:2900],
                r['geocode_status'] or '',r['source_url'] or '',r['warning'] or '',
                'GIS CANDIDATE ONLY—NO RECORDED DEED, BOUNDARY, ZONING OR AVAILABILITY VERIFICATION'])
    if 'phase6_events' in tables_exist:
        for r in db.execute('SELECT * FROM phase6_events ORDER BY first_seen_utc'):
            if is_fixture(r['source_url']):continue
            tables['Phase6 GIS Changes'].append([
                'P6:CHANGE:'+r['event_key'],r['lead_id'],r['first_seen_utc'],r['kind'],r['status'],r['source_url'] or ''])
    if 'phase6_source_health' in tables_exist:
        for r in db.execute('SELECT * FROM phase6_source_health ORDER BY id'):
            if is_fixture(r['source_url']):continue
            tables['Phase6 Source Health'].append([
                f"P6:HEALTH:{r['id']}",r['run_utc'],r['jurisdiction'],r['source_name'],r['status'],
                r['checked_leads'],r['matched_leads'],r['warnings_json'] or '',r['source_url'] or ''])
    return tables


def missing_rows(rows, remote_keys):
    """Avoid duplicate rows across retried runs or lost append responses."""
    seen=set(str(k) for k in remote_keys)
    pending=[]
    for row in rows:
        key=str(row[0])
        if key in seen:
            continue
        pending.append(row)
        seen.add(key)
    return pending


def token_from_secret(secret_text):
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleAuthRequest
    except ImportError as e:
        raise RuntimeError('Missing google-auth/requests; install requirements.txt') from e
    try:
        info=json.loads(secret_text)
        creds=service_account.Credentials.from_service_account_info(
            info,scopes=['https://www.googleapis.com/auth/spreadsheets'])
        creds.refresh(GoogleAuthRequest())
        return creds.token
    except Exception as e:
        raise RuntimeError('Google Sheets authentication failed; check service account secret') from e


def sheets_request(method, sheet_id, tab_and_range, token, payload=None):
    range_path=quote(tab_and_range,safe='')
    url=f'{SHEETS_API}/{quote(sheet_id,safe="")}/values/{range_path}'
    if method=='POST':
        url+=':'+ 'append' +'?'+urlencode({'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'})
    request=Request(url,method=method,
        headers={'Authorization':f'Bearer {token}','Accept':'application/json',
                 'Content-Type':'application/json'},
        data=None if payload is None else json.dumps(payload).encode('utf-8'))
    with urlopen(request,timeout=40) as response:
        data=response.read(2_000_001)
        if len(data)>2_000_000:
            raise RuntimeError('Google Sheets returned an unexpectedly large response')
    return json.loads(data.decode('utf-8'))


def existing_keys(sheet_id,tab,token):
    result=sheets_request('GET',sheet_id,f"'{tab}'!A2:A2000",token)
    return {str(r[0]) for r in result.get('values',[]) if r and r[0] is not None}


def sync(db, sheet_id, token):
    tables=outbox(db)
    result={}
    for tab,all_rows in tables.items():
        prior=existing_keys(sheet_id,tab,token)
        add=missing_rows(all_rows,prior)
        for start in range(0,len(add),100):
            batch=add[start:start+100]
            last_col=chr(ord('A')+len(HEADERS[tab])-1)
            response=sheets_request('POST',sheet_id,f"'{tab}'!A:{last_col}",token,
                          payload={'majorDimension':'ROWS','values':batch})
            recorded=int(response.get('updates',{}).get('updatedRows',-1))
            if recorded!=len(batch):
                raise RuntimeError(f'Sheets append acknowledgement mismatch in {tab}')
        result[tab]={'existing':len(prior),'appended':len(add)}
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description='Append Phase 5 machine evidence to dedicated Google Sheet tabs')
    p.add_argument('--dry-run',action='store_true',help='Inspect local outgoing records without network calls or credentials')
    p.add_argument('--db',type=Path,default=DB)
    p.add_argument('--sheet-id',default=os.environ.get('GOOGLE_SHEET_ID',''))
    args=p.parse_args(argv)
    db=connect(args.db)
    content=outbox(db)
    if args.dry_run:
        print(json.dumps({'mode':'DRY_RUN_NO_REMOTE_SYNC',
          'rows_available':{k:len(v) for k,v in content.items()},
          'caution':'These are source signals/evidence, not verified sale opportunities.'},indent=2))
        return 0
    secret=os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON','')
    if not args.sheet_id or not secret:
        print('Google Sheet sync SKIPPED: missing GOOGLE_SHEET_ID or GOOGLE_SERVICE_ACCOUNT_JSON.',file=sys.stderr)
        return 3
    token=token_from_secret(secret)
    result=sync(db,args.sheet_id,token)
    print(json.dumps({'status':'REMOTE_SYNC_COMPLETED','tabs':result},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
