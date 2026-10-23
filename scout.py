#!/usr/bin/env python3
"""Secured Innovations Phase 5 CRE signal scout, Python 3.11+, stdlib only.

This is a due-diligence SIGNAL tracker, not an automated broker, deed search
substitute, land-use entitlement verification, or assertion of availability.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DB = DATA / 'scout.sqlite'
OUT = ROOT / 'output'
BRAND_ORDER = {'Taco Bell': 1, 'Sheetz': 2, 'Bank of America': 3}
PHILLY_SQL_ENDPOINT = 'https://phl.carto.com/api/v2/sql'
PHILLY_ARCGIS_ENDPOINT = 'https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/PERMITS/FeatureServer/0/query'
CHESTER_LAYER = 'https://mapservices.pasda.psu.edu/server/rest/services/pasda/ChesterCounty/MapServer/11/query'
PENNDOT_LAYER = 'https://gis.penndot.pa.gov/gis/rest/services/tds/tire/MapServer/3/query'
CENSUS_ENDPOINT = 'https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress'
USER_AGENT = 'SecuredInnovationsCREResearch/0.4 (public-data research; respectful request rate)'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS leads(
      lead_id TEXT PRIMARY KEY, brand TEXT NOT NULL, address TEXT NOT NULL,
      municipality TEXT, county TEXT, state TEXT, offer TEXT, ask_usd REAL,
      acres REAL, gate TEXT, source_url TEXT, critical_caveat TEXT,
      first_observed TEXT, updated_utc TEXT, parcel_id TEXT,
      recorded_owner_verified INTEGER NOT NULL DEFAULT 0,
      officially_verified_aadt INTEGER NOT NULL DEFAULT 0,
      score INTEGER, score_quality TEXT,
      source_kind TEXT NOT NULL DEFAULT 'Phase3 marketing baseline');
    CREATE TABLE IF NOT EXISTS lead_observations(
      observation_id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT NOT NULL,
      observed_utc TEXT NOT NULL, fingerprint TEXT NOT NULL,
      offer TEXT, ask_usd REAL, acres REAL, gate TEXT, source_url TEXT,
      change_type TEXT NOT NULL, note TEXT,
      UNIQUE(lead_id, fingerprint),
      FOREIGN KEY(lead_id) REFERENCES leads(lead_id));
    CREATE TABLE IF NOT EXISTS signals(
      signal_id TEXT PRIMARY KEY, source TEXT NOT NULL, first_seen_utc TEXT,
      last_seen_utc TEXT, event_date TEXT, address TEXT,
      title TEXT, description TEXT, status TEXT, evidence_url TEXT,
      target_hint TEXT, classification TEXT NOT NULL DEFAULT 'REDEVELOPMENT SIGNAL',
      event_json TEXT);
    CREATE TABLE IF NOT EXISTS signal_observations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      signal_id TEXT NOT NULL,
      fingerprint TEXT NOT NULL,
      detected_utc TEXT NOT NULL,
      event_date TEXT,
      status TEXT,
      address TEXT,
      activity TEXT,
      hint TEXT,
      evidence_url TEXT,
      change_type TEXT NOT NULL,
      UNIQUE(signal_id,fingerprint),
      FOREIGN KEY(signal_id) REFERENCES signals(signal_id));
    CREATE TABLE IF NOT EXISTS research_evidence(
      evidence_id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT NOT NULL,
      checked_utc TEXT NOT NULL, source TEXT NOT NULL,
      record_type TEXT NOT NULL, status TEXT NOT NULL, source_url TEXT,
      details_json TEXT, FOREIGN KEY(lead_id) REFERENCES leads(lead_id));
    CREATE TABLE IF NOT EXISTS runs(
      run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_utc TEXT,
      finished_utc TEXT, mode TEXT, status TEXT, total_new_signals INTEGER,
      total_changed_leads INTEGER, warnings_json TEXT);
    ''')
    db.commit()
    return db


def price(s):
    if s is None or str(s).strip() == '': return None
    try: return float(str(s).replace(',',''))
    except (ValueError, TypeError): return None


def fp(*items):
    return hashlib.sha256(json.dumps(items,sort_keys=True,default=str).encode()).hexdigest()


def normalized(s):
    return re.sub(r'[^a-z0-9]+',' ',(s or '').lower()).strip()


def gate_code(gate):
    s = (gate or '').upper()
    if 'EXCLUDED' in s: return 'EXCLUDED'
    if 'HOLD' in s: return 'HOLD'
    if 'WATCH' in s: return 'WATCH'
    if 'REVIEW' in s: return 'REVIEW'
    return 'UNVERIFIED'


def score_lead(lead):
    """Transparent preliminary scores. Unknown facts do not earn affirmative points."""
    brand=lead['brand']; acreage=price(lead['acres']); g=gate_code(lead['gate'])
    if g=='EXCLUDED': return 0,'INELIGIBLE'
    # Transparent base is candidate presence only; not probability of sale or brand interest.
    pts=20 if brand=='Taco Bell' else (15 if brand=='Sheetz' else 18)
    if lead['source_url']: pts+=8
    offer=(lead['offer'] or '').lower()
    if 'for sale' in offer: pts+=12
    elif 'for lease' in offer: pts+=8
    if acreage is not None:
        if brand=='Sheetz': pts+=20 if 1<=acreage<=3 else 0
        elif brand=='Taco Bell': pts+=15 if .5<=acreage<=2.5 else 5
        elif brand=='Bank of America': pts+=8
    if lead['ask_usd'] is not None: pts+=5
    if lead['parcel_id']: pts+=10
    if lead['recorded_owner_verified']: pts+=10
    if lead['officially_verified_aadt']: pts+=10
    pts=min(pts,100)
    if g=='HOLD': pts=min(pts,49)
    if g=='WATCH': pts=min(pts,60)
    return pts, 'PRELIMINARY—GATED' if g in ('HOLD','WATCH') else 'PRELIMINARY—INCOMPLETE'


def add_observation(db, lead_id, offer, asking, acreage, gate, source_url, observed_at, note=''):
    f=fp(offer,asking,acreage,gate,source_url)
    prev=db.execute('SELECT * FROM lead_observations WHERE lead_id=? ORDER BY observation_id DESC LIMIT 1',(lead_id,)).fetchone()
    if prev and prev['fingerprint']==f:return False
    ct='BASELINE' if not prev else 'DOCUMENTED SOURCE CHANGE (REQUIRES REVIEW)'
    db.execute('''INSERT OR IGNORE INTO lead_observations
      (lead_id,observed_utc,fingerprint,offer,ask_usd,acres,gate,source_url,change_type,note)
      VALUES(?,?,?,?,?,?,?,?,?,?)''',
      (lead_id,observed_at,f,offer,asking,acreage,gate,source_url,ct,note))
    return bool(prev)


def seed(db, path):
    new=0
    with open(path,newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if not r['lead_id'] or r['lead_id'] in [None,'']:continue
            if db.execute('SELECT 1 FROM leads WHERE lead_id=?',(r['lead_id'],)).fetchone():continue
            arr={
              'lead_id':r['lead_id'],'brand':r['brand'],'address':r['address'],
              'municipality':r.get('municipality'),'county':r.get('county'),'state':r.get('state') or 'PA',
              'offer':r.get('offer'),'ask_usd':price(r.get('ask_usd')),'acres':price(r.get('acres')),
              'gate':r.get('gate'),'source_url':r.get('source_url'),
              'critical_caveat':r.get('critical_caveat'),
              'first_observed':r.get('observed_date') or '2026-10-23','updated_utc':now(),
              'parcel_id':None,'recorded_owner_verified':0,'officially_verified_aadt':0
            }
            score,qual=score_lead(arr)
            db.execute('''INSERT INTO leads
              (lead_id,brand,address,municipality,county,state,offer,ask_usd,acres,gate,source_url,
              critical_caveat,first_observed,updated_utc,score,score_quality)
              VALUES(:lead_id,:brand,:address,:municipality,:county,:state,:offer,:ask_usd,:acres,:gate,:source_url,
              :critical_caveat,:first_observed,:updated_utc,:score,:score_quality)''',{**arr,'score':score,'score_quality':qual})
            add_observation(db,arr['lead_id'],arr['offer'],arr['ask_usd'],arr['acres'],arr['gate'],arr['source_url'],arr['first_observed'],'Phase 3 baseline; NO evidence this listing is new')
            new+=1
    db.commit()
    return new


def fetch_json(url,params,timeout=25):
    uri=url+'?'+urlencode(params)
    req=Request(uri,headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    with urlopen(req,timeout=timeout) as resp:
        raw=resp.read(3_000_001)
        if len(raw)>3_000_000:raise ValueError('API response exceeded safety cap of 3 MB')
    result=json.loads(raw.decode('utf-8-sig'))
    if 'error' in result:raise RuntimeError(str(result['error'])[:300])
    return result,uri


def record_evidence(db, lead, source, kind, status, source_url, details):
    db.execute('''INSERT INTO research_evidence
      (lead_id,checked_utc,source,record_type,status,source_url,details_json)
      VALUES(?,?,?,?,?,?,?)''',
      (lead['lead_id'],now(),source,kind,status,source_url,json.dumps(details,ensure_ascii=False,default=str)[:14000]))


def official_chester_parcel_search(db, lead):
    """Queries official public GIS index; NOT an authoritative deed/title determination."""
    address=lead['address']
    m=re.match(r'^\s*(\d+)\s+(.+?)(?:,|$)',address)
    if not m:return {'status':'UNSEARCHABLE_ADDRESS'}
    n=int(m.group(1)); street=m.group(2).strip()
    toks=street.split()
    dirs={'N','S','E','W','NORTH','SOUTH','EAST','WEST'}
    types={'ST','STREET','RD','ROAD','PIKE','PK','AVE','AVENUE','BLVD','BOULEVARD','LANE','LN','DR','DRIVE','HWY','HIGHWAY','PL'}
    toks=[t.upper() for t in toks if t.upper().strip('.') not in dirs]
    if toks and toks[-1].strip('.') in types:toks.pop()
    base=(' '.join(toks))[:22].replace("'","''")
    if not base:return {'status':'NO_STREET'}
    params={'where':f"ST_NUM = {n} AND UPPER(ST_NAME) LIKE '{base.split()[0]}%'",'outFields':'UPI,PIN_ASMNT,ACRE_PLAN_,LOC_ADDRES,ST_NAME,ST_NUM,MUNI,OWN1,OWN2,DEED_REC_D,ASMT_DATE,OBJECTID','returnGeometry':'false','f':'json','resultRecordCount':20}
    try:
        j,uri=fetch_json(CHESTER_LAYER,params)
        feats=j.get('features',[])
        trimmed=[x.get('attributes',{}) for x in feats][:20]
        record_evidence(db,lead,'Chester County / PASDA','ASSESSOR_GIS_CANDIDATES','REVIEW_REQUIRED',uri,{'match_count':len(feats),'records':trimmed})
        return {'status':'CANDIDATES_NEED_REVIEW','matches':len(feats)}
    except Exception as exc:
        record_evidence(db,lead,'Chester County / PASDA','ASSESSOR_GIS_CANDIDATES','FETCH_ERROR',CHESTER_LAYER,{'error':str(exc)})
        return {'status':'FETCH_ERROR','message':str(exc)}


def census_geocode(address):
    # Census benchmark sometimes differs from current parcel/address authoritative datasets.
    j,uri=fetch_json(CENSUS_ENDPOINT,{'address':address,'benchmark':'Public_AR_Current','vintage':'Current_Current','format':'json'})
    matches=j.get('result',{}).get('addressMatches',[])
    if len(matches)!=1:return None,uri
    c=matches[0].get('coordinates') or {}
    if c.get('x') is None or c.get('y') is None:return None,uri
    return {'longitude':c['x'],'latitude':c['y'],'matchedAddress':matches[0].get('matchedAddress')},uri


def official_pennDOT_nearby_traffic(db, lead):
    try:
        geocode,geocode_url=census_geocode(lead['address'])
        if not geocode:
            record_evidence(db,lead,'US Census Geocoder','ADDRESS_POINT','NO_EXACT_MATCH',geocode_url,{})
            return {'status':'NO_EXACT_GEOCODE'}
        params={
          'geometry':f"{geocode['longitude']},{geocode['latitude']}",
          'geometryType':'esriGeometryPoint','inSR':4326,'spatialRel':'esriSpatialRelIntersects',
          'distance':150,'units':'esriSRUnit_Meter','outFields':'RMSTRAFFIC_LRS_KEY,CUR_AADT,VOL_CNT_DATE,BASE_ADT_YR,ST_RT_NO,OBJECTID',
          'returnGeometry':'false','f':'json','resultRecordCount':20}
        j,uri=fetch_json(PENNDOT_LAYER,params)
        fs=[x.get('attributes',{}) for x in j.get('features',[])][:20]
        record_evidence(db,lead,'PennDOT / TIRe','NEARBY_ROAD_TRAFFIC','NEARBY_NOT_SITE_VERIFIED',uri,{'geocode':geocode,'segments':fs})
        return {'status':'NEARBY—HUMAN SEGMENT MATCH REQUIRED','segments':len(fs)}
    except Exception as exc:
        record_evidence(db,lead,'PennDOT / TIRe','NEARBY_ROAD_TRAFFIC','FETCH_ERROR',PENNDOT_LAYER,{'error':str(exc)})
        return {'status':'FETCH_ERROR','message':str(exc)}


def collect_philly_permits(days=14,fixture=None):
    """Only a redevelopment INDICATOR, never a listing or company expansion approval."""
    if fixture:
        with open(fixture,encoding='utf-8') as f:return json.load(f),f'fixture:{fixture}'
    cutoff=(dt.date.today()-dt.timedelta(days=days)).isoformat()
    # Fixed query: only useful property-activity permit types; bounded volume.
    sql=("SELECT permitnumber,address,permitissuedate,permittype,typeofwork,"
         "permitdescription,approvedscopeofwork,commercialorresidential,status,opa_account_num "
         "FROM permits WHERE permitissuedate >= '"+cutoff+"' AND "
         "(UPPER(COALESCE(typeofwork,'')) LIKE '%DEMOLITION%' OR "
         "UPPER(COALESCE(typeofwork,'')) LIKE '%NEW CONSTRUCTION%' OR "
         "UPPER(COALESCE(typeofwork,'')) LIKE '%CHANGE OF USE%' OR "
         "UPPER(COALESCE(permittype,'')) LIKE '%ZONING%') "
         "AND (commercialorresidential IS NULL OR UPPER(commercialorresidential) <> 'RESIDENTIAL') "
         "ORDER BY permitissuedate DESC LIMIT 250")
    j,uri=fetch_json(PHILLY_SQL_ENDPOINT,{'q':sql})
    rows=j.get('rows')
    if not isinstance(rows,list):raise ValueError('Unexpected Philadelphia permit response')
    return rows,uri


def collect_philly_permits_arcgis(days=14):
    """Official ArcGIS feature-layer fallback when Carto SQL is unavailable.

    The query schema has been cross-checked against published ArcGIS layer
    metadata but still needs its first network-run validation.
    """
    cutoff=(dt.date.today()-dt.timedelta(days=days)).isoformat()
    fields='permitnumber,address,permitissuedate,permittype,typeofwork,permitdescription,approvedscopeofwork,commercialorresidential,status,opa_account_num'
    where=(f"permitissuedate >= DATE '{cutoff}' AND "
        "(UPPER(typeofwork) LIKE '%DEMOLITION%' OR "
        "UPPER(typeofwork) LIKE '%NEW CONSTRUCTION%' OR "
        "UPPER(typeofwork) LIKE '%CHANGE OF USE%' OR "
        "UPPER(permittype) LIKE '%ZONING%') AND "
        "(commercialorresidential IS NULL OR UPPER(commercialorresidential) <> 'RESIDENTIAL')")
    data,uri=fetch_json(PHILLY_ARCGIS_ENDPOINT,{
        'where':where,'outFields':fields,'returnGeometry':'false',
        'orderByFields':'permitissuedate DESC','resultRecordCount':250,'f':'json'})
    if not isinstance(data.get('features'),list):
        raise ValueError('Unexpected Philadelphia ArcGIS permit response')
    return [x.get('attributes',{}) for x in data['features']],uri


def parse_event_date(value):
    if isinstance(value,(int,float)) and value>10**11:
        return dt.datetime.fromtimestamp(value/1000,dt.timezone.utc).date().isoformat()
    if isinstance(value,(int,float)) and 10**9<value<10**11:
        return dt.datetime.fromtimestamp(value,dt.timezone.utc).date().isoformat()
    return str(value or '')[:10]


def classify_signal(row):
    text=' '.join(str(row.get(k) or '') for k in ('typeofwork','permitdescription','approvedscopeofwork','permittype')).lower()
    if any(x in text for x in ('restaurant','drive-thru','drive through','fast food')):return 'Taco Bell'
    if any(x in text for x in ('fuel','gasoline','convenience store','service station')):return 'Sheetz'
    if any(x in text for x in ('bank','financial center','atm')):return 'Bank of America'
    return 'UNASSIGNED—MANUAL REVIEW'


def save_signals(db, rows, source_url):
    """Idempotent permit IDs with a separate status/content-change event ledger."""
    added=0
    for r in rows:
        permit=str(r.get('permitnumber') or '').strip()
        address=str(r.get('address') or '').strip()
        if not permit or not address:continue
        sid='PHL-PERMIT:'+permit
        target=classify_signal(r)
        descr=' | '.join(str(r.get(k) or '')[:300] for k in ('permittype','typeofwork','permitdescription','approvedscopeofwork')).strip(' |')
        status=str(r.get('status') or '')
        evt_date=parse_event_date(r.get('permitissuedate'))
        content_hash=fp(evt_date,normalized(address),descr,status,target)
        old=db.execute('SELECT * FROM signals WHERE signal_id=?',(sid,)).fetchone()
        prev=db.execute('SELECT fingerprint FROM signal_observations WHERE signal_id=? ORDER BY id DESC LIMIT 1',(sid,)).fetchone()
        if not old:
            db.execute('''INSERT INTO signals
              (signal_id,source,first_seen_utc,last_seen_utc,event_date,address,title,description,status,evidence_url,target_hint,classification,event_json)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (sid,'Philadelphia L&I / Carto API',now(),now(),evt_date,address,
               f"Permit {permit}: {r.get('permittype') or 'unknown'}",descr,status,
               source_url,target,'MUNICIPAL PERMIT SIGNAL — NOT LISTED PROPERTY',json.dumps(r,ensure_ascii=False,default=str)))
            added+=1
        else:
            db.execute('''UPDATE signals SET last_seen_utc=?,event_date=?,address=?,description=?,status=?,evidence_url=?,target_hint=?,event_json=?
              WHERE signal_id=?''',(now(),evt_date,address,descr,status,source_url,target,json.dumps(r,ensure_ascii=False,default=str),sid))
        if not prev or prev['fingerprint'] != content_hash:
            db.execute('''INSERT OR IGNORE INTO signal_observations
              (signal_id,fingerprint,detected_utc,event_date,status,address,activity,hint,evidence_url,change_type)
              VALUES(?,?,?,?,?,?,?,?,?,?)''',
              (sid,content_hash,now(),evt_date,status,address,descr,target,source_url,'FIRST OBSERVED' if not prev else 'PERMIT CONTENT OR STATUS CHANGE'))
    db.commit()
    return added

def ingest_reviewed_csv(db, path):
    """Update a known lead only after explicit analyst approval and source reference.

    Reopening an excluded site requires manual database review, never CSV alone.
    """
    changed=0; skipped=[]
    with open(path,newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            lid=(r.get('lead_id') or '').strip()
            old=db.execute('SELECT * FROM leads WHERE lead_id=?',(lid,)).fetchone()
            if not old:
                skipped.append((lid,'Unknown Lead ID'));continue
            if (r.get('analyst_approved') or '').strip().lower()!='yes':
                skipped.append((lid,'Not analyst-approved'));continue
            if not r.get('source_url') or not r.get('observed_date'):
                skipped.append((lid,'Missing source_url or observed_date'));continue
            offer=r.get('offer') or old['offer'];gate=r.get('gate') or old['gate'];url=r['source_url']
            if gate_code(old['gate'])=='EXCLUDED' and gate_code(gate)!='EXCLUDED':
                skipped.append((lid,'Excluded site cannot be reopened through a CSV'));continue
            ask=price(r.get('ask_usd')) if r.get('ask_usd') else old['ask_usd']
            acres=price(r.get('acres')) if r.get('acres') else old['acres']
            score,qual=score_lead({**dict(old),'offer':offer,'gate':gate,'source_url':url,'ask_usd':ask,'acres':acres})
            if add_observation(db,lid,offer,ask,acres,gate,url,r['observed_date'],r.get('note') or 'Analyst reviewed'):
                db.execute('UPDATE leads SET offer=?,ask_usd=?,acres=?,gate=?,source_url=?,score=?,score_quality=?,updated_utc=? WHERE lead_id=?',
                           (offer,ask,acres,gate,url,score,qual,now(),lid))
                changed+=1
    db.commit()
    return changed,skipped

def write_reports(db, out=OUT):
    out.mkdir(parents=True,exist_ok=True)
    leads=[dict(x) for x in db.execute('SELECT * FROM leads').fetchall()]
    leads.sort(key=lambda x:(BRAND_ORDER.get(x['brand'],9),gate_code(x['gate'])=='EXCLUDED',-int(x['score'] or 0),x['lead_id']))
    events=[dict(x) for x in db.execute('SELECT * FROM signals ORDER BY event_date DESC, signal_id DESC LIMIT 150').fetchall()]
    evid=[dict(x) for x in db.execute('SELECT * FROM research_evidence ORDER BY evidence_id DESC LIMIT 500').fetchall()]
    def save_csv(name,items,columns):
        with open(out/name,'w',encoding='utf-8-sig',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore'); wr.writeheader();wr.writerows(items)
    save_csv('property_pipeline.csv',leads,['lead_id','brand','address','municipality','county','state','offer','ask_usd','acres','gate','score','score_quality','source_url','parcel_id','recorded_owner_verified','officially_verified_aadt','critical_caveat'])
    save_csv('municipal_signals.csv',events,['signal_id','first_seen_utc','event_date','address','title','description','status','target_hint','classification','evidence_url'])
    event_changes=[dict(x) for x in db.execute('SELECT * FROM signal_observations ORDER BY id DESC LIMIT 1500').fetchall()]
    save_csv('permit_signal_changes.csv',event_changes,['id','signal_id','fingerprint','detected_utc','event_date','status','address','activity','hint','evidence_url','change_type'])
    runs=[dict(x) for x in db.execute('SELECT * FROM runs ORDER BY run_id DESC LIMIT 150').fetchall()]
    save_csv('run_history.csv',runs,['run_id','started_utc','finished_utc','mode','status','total_new_signals','total_changed_leads','warnings_json'])
    save_csv('official_evidence_review.csv',evid,['lead_id','checked_utc','source','record_type','status','source_url','details_json'])
    changes=[dict(x) for x in db.execute('SELECT * FROM lead_observations ORDER BY observation_id DESC LIMIT 500').fetchall()]
    save_csv('lead_changes.csv',changes,['observation_id','lead_id','observed_utc','offer','ask_usd','acres','gate','change_type','source_url','note'])
    with open(out/'signals.json','w',encoding='utf-8') as f:json.dump(events,f,indent=2,ensure_ascii=False)
    sections=['# Secured Innovations — Phase 5 Cloud Acquisition Intelligence Report','',
              f'_Generated {now()} · research signals only; not brokerage advice or offers_','',
              f'**Pipeline:** {len(leads)} baseline properties · {len(events)} distinct municipal signals · {len(evid)} evidence checks','',
              '**Gating rule:** EXCLUDED is never a qualified lead; HOLD cannot be marketed as ready even if its preliminary score is high.','']
    for brand in BRAND_ORDER:
        sections.append('## '+brand)
        sections.append('| Lead | Site | Screening score | Stage | Evidence / next blocker |')
        sections.append('|---|---|---:|---|---|')
        for x in [a for a in leads if a['brand']==brand]:
            caveat=(x['critical_caveat'] or 'Further verification required').replace('|','/').replace('\n',' ')
            sections.append(f"| {x['lead_id']} | {x['address']} | {x['score']}/100 | {x['gate']} | {caveat[:150]} |")
        sections.append('')
    sections+=['## Municipal-development signals','',
               'A permit is a **planning/construction activity signal**, not proof a site is vacant, for sale, or approved for one of the three target brands.','']
    if not events: sections.append('No municipal signals recorded in this run.')
    else:
        for x in events[:20]:sections.append(f"- **{x['event_date']} — {x['address']}**: {x['title']}; target relevance: {x['target_hint']} ({x['evidence_url']})")
    last_run=runs[0] if runs else None
    if last_run:
        warnings=json.loads(last_run.get('warnings_json') or '[]')
        sections+=['','## Most recent collection run',f"Run #{last_run['run_id']}: **{last_run['status']}** ({last_run['mode']}); {last_run['total_new_signals'] or 0} new permit signals."]
        if warnings: sections.extend(['','**Source warnings (data may be incomplete):**',*[f'- {str(w)[:500]}' for w in warnings]])
    sections+=['','## Acquisition due diligence protocol','',
              '1. Obtain parcel geometry and deed ownership from official records. GIS assessor names are a lead, not a title opinion.',
              '2. Confirm active marketing, broker instructions and site control; off-market does not mean an owner is willing to sell.',
              '3. Check municipal use permissions, drive-through/fuel special exceptions, traffic station location/year and access.',
              '4. Request brand-approval criteria through authorized, licensed commercial real estate channels.',
              '5. Only appropriately licensed professionals handle solicitation, negotiation, referral structures and commissions.','']
    (out/'weekly_report.md').write_text('\n'.join(sections),encoding='utf-8')
    return {'leads':len(leads),'signals':len(events),'evidence':len(evid),'report':str(out/'weekly_report.md')}


def scan(db,offline=False,fixture=None,verify_limit=8):
    start=now();new_signals=0;changed=0;warnings=[]
    db.execute('INSERT INTO runs(started_utc,mode,status) VALUES(?,?,?)',(start,'OFFLINE DEMO' if offline else 'LIVE','RUNNING'))
    rid=db.execute('SELECT last_insert_rowid()').fetchone()[0]
    if offline:
        fixture=fixture or ROOT/'fixtures'/'philadelphia_permits_fixture.json'
    try:
        if offline:
            r,src=collect_philly_permits(fixture=fixture)
        else:
            try:
                r,src=collect_philly_permits()
            except Exception as carto_exc:
                # The City publishes both Carto and ArcGIS APIs. Neither is
                # a guarantee of site availability or proposed brand approval.
                try:
                    r,src=collect_philly_permits_arcgis()
                except Exception as arcgis_exc:
                    raise RuntimeError(f'Carto: {carto_exc}; ArcGIS: {arcgis_exc}') from arcgis_exc
        new_signals=save_signals(db,r,src)
    except Exception as exc:
        warnings.append('Philadelphia permits: '+str(exc))
    if not offline:
        selected=db.execute('''SELECT * FROM leads WHERE county='Chester' AND UPPER(gate) NOT LIKE '%EXCLUDED%'
                               ORDER BY CASE brand WHEN 'Taco Bell' THEN 1 WHEN 'Sheetz' THEN 2 ELSE 3 END, lead_id
                               LIMIT ?''',(verify_limit,)).fetchall()
        for lead in selected:
            a=official_chester_parcel_search(db,lead)
            if a.get('status')=='FETCH_ERROR':warnings.append(f"GIS {lead['lead_id']}: {a.get('message','source error')}")
            time.sleep(0.6)
            b=official_pennDOT_nearby_traffic(db,lead)
            if b.get('status')=='FETCH_ERROR':warnings.append(f"Traffic {lead['lead_id']}: {b.get('message','source error')}")
            time.sleep(0.6)
    db.execute('UPDATE runs SET finished_utc=?,status=?,total_new_signals=?,total_changed_leads=?,warnings_json=? WHERE run_id=?',
        (now(),'PARTIAL—SOURCE WARNINGS' if warnings else 'COMPLETED',new_signals,changed,json.dumps(warnings),rid))
    db.commit()
    summary=write_reports(db)
    summary.update({'new_signals_this_run':new_signals,'warnings':warnings,'mode':'OFFLINE DEMO' if offline else 'LIVE'})
    return summary


def main():
    ap=argparse.ArgumentParser(description='Secured Innovations CRE property signals and diligence bot')
    ap.add_argument('command',choices=['init','scan','report','ingest'])
    ap.add_argument('--input',type=Path,help='Analyst-approved changes CSV')
    ap.add_argument('--offline',action='store_true',help='No network: uses clearly marked synthetic permit fixture')
    ap.add_argument('--db',type=Path,default=DB)
    ap.add_argument('--fixture',type=Path)
    ap.add_argument('--verify-limit',type=int,default=8)
    args=ap.parse_args()
    db=connect(args.db)
    count=seed(db,DATA/'seed_phase3.csv')
    if args.command=='init':print(json.dumps({'status':'initialized','baseline_leads_added':count,'db':str(args.db)},indent=2));return
    if args.command=='report':print(json.dumps(write_reports(db),indent=2));return
    if args.command=='ingest':
        if not args.input:ap.error('ingest requires --input approved_changes.csv')
        changed,skipped=ingest_reviewed_csv(db,args.input)
        print(json.dumps({'changed_leads':changed,'skipped':skipped,'report':write_reports(db)},indent=2));return
    result=scan(db,args.offline,args.fixture,verify_limit=max(0,min(16,args.verify_limit)))
    print(json.dumps({'baseline_leads_added':count,**result},indent=2))
    if result['warnings']:sys.exit(2) # surface degraded source integrity to CI, preserve existing DB

if __name__=='__main__':main()
