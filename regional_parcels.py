#!/usr/bin/env python3
"""Phase 6 regional assessor/GIS candidate enrichment, NOT title or deal verification.

No canvassing/scraping; reads only documented public ArcGIS/Census services.
These observations NEVER update `leads.parcel_id` or `recorded_owner_verified`.
A Census point can hit the wrong adjacent polygon: all hits remain REVIEW_REQUIRED.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import scout

@dataclass(frozen=True)
class Layer:
    jurisdiction: str
    url: str
    label: str
    id_fields: tuple[str, ...]
    address_fields: tuple[str, ...]
    acreage_fields: tuple[str, ...] = ()
    quality: str = 'GOVERNMENT_GIS'
    geometry: str = 'esriGeometryPolygon'

LAYERS = {
    ('PA','Chester'): Layer('Chester County, PA', 'https://mapservices.pasda.psu.edu/server/rest/services/pasda/ChesterCounty/MapServer/11', 'PASDA Chester County parcels', ('UPI','PIN_ASMNT'), ('LOC_ADDRES',), ('ACRE_PLAN_',)),
    ('PA','Delaware'): Layer('Delaware County, PA','https://gis.delcopa.gov/arcgis/rest/services/Parcels/Parcels_Public_Access/FeatureServer/0','Delaware County Public Access parcels',('PIN','PARID','MAPID'),('ADRCAT',),('CALCULATED',)),
    ('PA','Montgomery'): Layer('Montgomery County, PA','https://gis.montcopa.org/arcgis/rest/services/Parcels/Montgomery_County_Parcels/FeatureServer/10','Montgomery County parcels',('TAXPIN','ALTERNATEID'),(),('CALCACREAGE','TrueCalculatedAcres')),
    ('PA','Bucks'): Layer('Bucks County, PA','https://services.pasda.psu.edu/server/rest/services/pasda/BucksCounty/MapServer/17','PASDA Bucks County 2026 parcels',('PARCEL_NUM',),('ADDRESS',),('DEED_AREA',)),
    ('PA','Philadelphia'): Layer('Philadelphia, PA','https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/OPA_PROPERTIES_PUBLIC/FeatureServer/0','City of Philadelphia OPA assessment points',('parcel_number','PARCEL_NUMBER','account_number'),('street_address','address_std','street_name'),(),geometry='esriGeometryPoint'),
    ('DE','New Castle'): Layer('New Castle County, DE','https://gis.nccde.org/agsserver/rest/services/BaseMaps/Addresses/MapServer/4','New Castle County assessment parcel geometry',('PRCLID',),('ADDRESS',),('LOTSZ',)),
    ('NJ','STATEWIDE'): Layer('New Jersey statewide','https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0','NJGIN current parcel composite',('PAMS_PIN','PIN_NODUP','GIS_PIN'),('PROP_LOC',),('CALC_ACRE',)),
}
HEADERS = ['Snapshot key','Checked UTC','Lead ID','Brand','Jurisdiction','Result','Candidate count',
           'Candidate IDs','Candidate addresses','Candidate acreages','GIS quality','Geo match','Source URL',
           'Warning','Review requirement']
SOURCE_HEADERS=['Run UTC','Jurisdiction','Source name','Status','Checked leads','Matched leads','Warnings','Service URL']


def _now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def key_for_lead(lead):
    state=(lead.get('state') or 'PA').strip().upper()
    if state=='NJ':return 'NJ','STATEWIDE'
    if state=='DE':return 'DE','New Castle' if (lead.get('county') or '').lower().strip() in {'new castle','newcastle'} else 'UNSUPPORTED'
    if state=='PA':return 'PA',(lead.get('county') or '').strip().title()
    return state,'UNSUPPORTED'


def request_json(url,params=None,timeout=24):
    link=url+'?'+urlencode(params) if params else url
    req=Request(link,headers={'User-Agent':'SecuredInnovationsCRE-CandidateGIS/0.6 (low-volume research)','Accept':'application/json'})
    with urlopen(req,timeout=timeout) as response:
        data=response.read(2_000_001)
    if len(data)>2_000_000:raise RuntimeError('Source exceeded 2MB safe response limit')
    result=json.loads(data.decode('utf-8-sig'))
    if not isinstance(result,dict) or 'error' in result:
        raise RuntimeError('GIS error: '+str(result.get('error') if isinstance(result,dict) else 'invalid response')[:400])
    return result,link


def metadata_fields(document):
    # ArcGIS metadata advertises fields; a missing capabilities property is normal.
    fields=document.get('fields') or []
    return {x.get('name'):x for x in fields if isinstance(x,dict) and x.get('name')}


def safe_fields(layer,meta):
    known=metadata_fields(meta)
    # Limit to public parcel identifiers, physical land attributes, *not owner names*
    chosen=[]
    for value in layer.id_fields+layer.address_fields+layer.acreage_fields:
        if value in known and value not in chosen:chosen.append(value)
    if not chosen:raise ValueError('No recognized parcel identifier/address fields in metadata; source schema changed')
    return chosen


def address_number(text):
    r=re.search(r'\b(\d{1,6})\b',text or '')
    return r.group(1) if r else None


def validate_geocode_match(lead,geo):
    if not geo or 'longitude' not in geo or 'latitude' not in geo:return False,'NO_UNIQUE_GEOCODE'
    # Census does not guarantee a rooftop: check street number, state, and where possible postal code.
    source=(lead.get('address') or '').upper()
    matched=(geo.get('matchedAddress') or '').upper()
    if address_number(source)!=address_number(matched):return False,'STREET_NUMBER_MISMATCH'
    state=(lead.get('state') or 'PA').upper()
    if not re.search(r'\b'+re.escape(state)+r'\b',matched):return False,'STATE_MISMATCH'
    source_zip=re.search(r'\b\d{5}\b',source)
    matched_zip=re.search(r'\b\d{5}\b',matched)
    if source_zip and matched_zip and source_zip.group()!=matched_zip.group():return False,'POSTAL_CODE_MISMATCH'
    return True,'CENSUS_ADDRESS_MATCH—POINT_NOT_BOUNDARY'


def point_query_params(layer,geo,fields):
    query={'f':'json','where':'1=1', 'geometry':f'{geo["longitude"]},{geo["latitude"]}',
        'geometryType':'esriGeometryPoint','inSR':4326,'spatialRel':'esriSpatialRelIntersects',
        'outFields':','.join(fields),'returnGeometry':'false','resultRecordCount':8}
    if layer.geometry=='esriGeometryPoint':
        query.update({'distance':40,'units':'esriSRUnit_Meter'})
    return query


def compare_address(lead,attrs,layer):
    # Site match is provisional even when all recorded strings look the same.
    original=scout.normalized(lead.get('address','').split(',')[0])
    observed=[scout.normalized(str(attrs.get(k,''))) for k in layer.address_fields if attrs.get(k)]
    number=address_number(original)
    if number and any(address_number(a)==number for a in observed):return 'STREET_NUMBER_POSSIBLE'
    return 'POINT_INTERSECTION_ONLY'


def compact_features(features,fields,layer,lead):
    out=[]
    for feature in features[:8]:
        a=feature.get('attributes') or {}
        # Schema-driven attr whitelist excludes owner, mailing, protected person data.
        attrs={k:str(a[k])[:180] for k in fields if a.get(k) is not None}
        out.append({'attrs':attrs,'address_check':compare_address(lead,a,layer)})
    return out


def ensure_schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS phase6_snapshots(
      id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT NOT NULL,
      jurisdiction TEXT NOT NULL, checked_utc TEXT NOT NULL,
      fingerprint TEXT, result TEXT NOT NULL, candidates_json TEXT,
      source_url TEXT, geocode_status TEXT, warning TEXT,
      FOREIGN KEY (lead_id) REFERENCES leads(lead_id));
    CREATE TABLE IF NOT EXISTS phase6_events(
      event_key TEXT PRIMARY KEY, lead_id TEXT NOT NULL,
      first_seen_utc TEXT, kind TEXT NOT NULL, current_fingerprint TEXT,
      previous_fingerprint TEXT, status TEXT NOT NULL, source_url TEXT);
    CREATE TABLE IF NOT EXISTS phase6_source_health(
      id INTEGER PRIMARY KEY AUTOINCREMENT, run_utc TEXT, jurisdiction TEXT,
      source_name TEXT, status TEXT, checked_leads INTEGER, matched_leads INTEGER,
      warnings_json TEXT, source_url TEXT);
    ''')
    db.commit()


def stable_fingerprint(features):
    # Ignore collection order and descriptive metadata; compare public identifier+size/address fields.
    return hashlib.sha256(json.dumps(sorted([v['attrs'] for v in features],key=lambda d:json.dumps(d,sort_keys=True)),sort_keys=True).encode()).hexdigest()


def persist_snapshot(db,lead,layer,result,candidates,url,geostatus,warning='',checked=None):
    checked=checked or _now()
    prior=db.execute('SELECT * FROM phase6_snapshots WHERE lead_id=? AND result IN ("GIS_CANDIDATES_NEED_REVIEW","NO_CANDIDATE") ORDER BY id DESC LIMIT 1',(lead['lead_id'],)).fetchone()
    fingerprint=stable_fingerprint(candidates) if result in ('GIS_CANDIDATES_NEED_REVIEW','NO_CANDIDATE') else None
    db.execute('''INSERT INTO phase6_snapshots(lead_id,jurisdiction,checked_utc,fingerprint,result,candidates_json,source_url,geocode_status,warning)
      VALUES(?,?,?,?,?,?,?,?,?)''',(lead['lead_id'],layer.jurisdiction,checked,fingerprint,result,json.dumps(candidates,sort_keys=True),url,geostatus,str(warning)[:400]))
    if fingerprint is not None and (prior is None or prior['fingerprint']!=fingerprint):
        kind='FIRST_GIS_OBSERVATION' if prior is None else 'GIS_SOURCE_DATA_CHANGED—REVIEW'
        event_key=hashlib.sha256(f'{lead["lead_id"]}|{fingerprint}|{kind}'.encode()).hexdigest()
        db.execute('INSERT OR IGNORE INTO phase6_events VALUES(?,?,?,?,?,?,?,?)',
             (event_key,lead['lead_id'],checked,kind,fingerprint,prior['fingerprint'] if prior else None,'UNVERIFIED_GIS_CANDIDATE',url))
    db.commit()
    return {'lead_id':lead['lead_id'],'result':result,'count':len(candidates),'warning':warning}


def evaluate_lead(db,lead,fetch=request_json,geocoder=None,checked=None):
    key=key_for_lead(lead)
    layer=LAYERS.get(key)
    if not layer:return {'lead_id':lead['lead_id'],'result':'NO_PUBLIC_LAYER_CONFIGURED','count':0}
    if scout.gate_code(lead.get('gate'))=='EXCLUDED':return {'lead_id':lead['lead_id'],'result':'EXCLUDED_NOT_QUERIED','count':0}
    checked=checked or _now()
    try:
        if geocoder is None:
            geo,geo_link=scout.census_geocode(lead['address'])
        else:geo,geo_link=geocoder(lead['address'])
        valid,geo_status=validate_geocode_match(lead,geo)
        if not valid:
            return persist_snapshot(db,lead,layer,'GEOCODE_REJECTED',[],geo_link,geo_status,checked=checked)
        meta,_=fetch(layer.url,{'f':'json'})
        fields=safe_fields(layer,meta)
        data,url=fetch(layer.url+'/query',point_query_params(layer,geo,fields))
        candidates=compact_features(data.get('features') or [],fields,layer,lead)
        # If truncated, do not create a misleading data-change event for a partial result.
        if data.get('exceededTransferLimit') or len(data.get('features') or [])>8:
            return persist_snapshot(db,lead,layer,'AMBIGUOUS_QUERY_LIMIT',candidates,url,geo_status,'More matches than review limit',checked)
        state='GIS_CANDIDATES_NEED_REVIEW' if candidates else 'NO_CANDIDATE'
        return persist_snapshot(db,lead,layer,state,candidates,url,geo_status,checked=checked)
    except Exception as exc:
        return persist_snapshot(db,lead,layer,'FETCH_OR_SCHEMA_ERROR',[],layer.url,'NOT_CONFIRMED',str(exc),checked)


def write_exports(db,out=None):
    out=Path(out or scout.OUT);out.mkdir(parents=True,exist_ok=True)
    latest=db.execute('''SELECT t.* FROM phase6_snapshots t JOIN
      (SELECT lead_id,MAX(id) AS latest_id FROM phase6_snapshots GROUP BY lead_id) q ON t.id=q.latest_id
      ORDER BY CASE (SELECT brand FROM leads WHERE lead_id=t.lead_id)
        WHEN 'Taco Bell' THEN 1 WHEN 'Sheetz' THEN 2 ELSE 3 END,t.lead_id''').fetchall()
    with (out/'regional_parcel_candidates.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(HEADERS)
        for row in latest:
            c=json.loads(row['candidates_json'] or '[]')
            ids=[];addresses=[];acres=[]
            for el in c:
                a=el.get('attrs',{});ids.append(next((str(v) for k,v in a.items() if re.search(r'PIN|PARCEL|PRCL|UPI|ACCOUNT',k,re.I)),''))
                addresses.append(next((str(v) for k,v in a.items() if re.search(r'ADDRESS|ADRCAT|PROP_LOC',k,re.I)),''))
                acres.append(next((str(v) for k,v in a.items() if re.search(r'ACRE|LOT|AREA|CALCULATED',k,re.I)),''))
            lead=db.execute('SELECT * FROM leads WHERE lead_id=?',(row['lead_id'],)).fetchone()
            w.writerow([row['id'],row['checked_utc'],row['lead_id'],lead['brand'] if lead else '',row['jurisdiction'],row['result'],len(c),'; '.join(ids),'; '.join(addresses),'; '.join(acres),'OFFICIAL GIS CANDIDATE (NOT DEED)',row['geocode_status'],row['source_url'],row['warning'],'Recorded deed, legal boundaries, zoning, access and traffic still need confirmation'])
    with (out/'regional_gis_change_log.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['Event Key','Lead ID','Event type','First observed UTC','Status','Source'])
        for row in db.execute('SELECT * FROM phase6_events ORDER BY first_seen_utc,lead_id'):
            w.writerow([row['event_key'],row['lead_id'],row['kind'],row['first_seen_utc'],row['status'],row['source_url']])
    with (out/'regional_source_registry.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['State','County scope','Jurisdiction','Public ArcGIS layer URL','Source type','Automatic title proof','Automatic availability proof'])
        for (state,county),layer in LAYERS.items():w.writerow([state,county,layer.jurisdiction,layer.url,layer.quality,'NO','NO'])
    return len(latest)


def run(db,limit=16,offline=False,fixture=None,pace=1.2):
    ensure_schema(db)
    leads=db.execute("SELECT * FROM leads ORDER BY CASE brand WHEN 'Taco Bell' THEN 1 WHEN 'Sheetz' THEN 2 ELSE 3 END, lead_id").fetchall()
    # Hard cap protects source services; expanded counties can be cycled in configuration.
    leads=[dict(x) for x in leads if scout.gate_code(x['gate'])!='EXCLUDED'][:max(0,min(limit,60))]
    results=[]
    run_utc=_now()
    for i,l in enumerate(leads):
        if offline:
            # Offline mode only tests projection and code paths: never creates production observations.
            results.append({'lead_id':l['lead_id'],'result':'OFFLINE_VALIDATION_ONLY','county':l['county'],'state':l['state']})
        else:
            results.append(evaluate_lead(db,l))
            if i<len(leads)-1:time.sleep(pace)
    if not offline:
        by_jurisdiction={}
        for l,r in zip(leads,results):
            code=key_for_lead(l);layer=LAYERS.get(code)
            if layer is None:continue
            key=layer.jurisdiction
            if key not in by_jurisdiction:by_jurisdiction[key]={'layer':layer,'checked':0,'matches':0,'warnings':[]}
            item=by_jurisdiction[key];item['checked']+=1
            if r['result']=='GIS_CANDIDATES_NEED_REVIEW':item['matches']+=1
            if r['result'] in ('FETCH_OR_SCHEMA_ERROR','GEOCODE_REJECTED','AMBIGUOUS_QUERY_LIMIT'):
                item['warnings'].append(f"{l['lead_id']}: {r['result']} ({str(r.get('warning',''))[:140]})")
        for j,item in sorted(by_jurisdiction.items()):
            db.execute('''INSERT INTO phase6_source_health(run_utc,jurisdiction,source_name,status,checked_leads,matched_leads,warnings_json,source_url)
            VALUES(?,?,?,?,?,?,?,?)''',(run_utc,j,item['layer'].label,'DEGRADED' if item['warnings'] else 'RESPONDED',item['checked'],item['matches'],json.dumps(item['warnings']),item['layer'].url))
        db.commit()
        write_exports(db)
        with (scout.OUT/'regional_source_health.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(SOURCE_HEADERS)
            for r in db.execute('SELECT * FROM phase6_source_health ORDER BY id'):
                w.writerow([r['run_utc'],r['jurisdiction'],r['source_name'],r['status'],r['checked_leads'],r['matched_leads'],r['warnings_json'],r['source_url']])
    status='UNVERIFIED_SOURCE_RUN' if not offline else 'OFFLINE_NO_SOURCE_CALLS'
    return {'status':status,'leads_considered':len(leads),'results':results,
        'errors':sum(x['result'] == 'FETCH_OR_SCHEMA_ERROR' for x in results),
        'review_holds':sum(x['result'] in ('GEOCODE_REJECTED','AMBIGUOUS_QUERY_LIMIT') for x in results)}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['scan','report','registry'])
    p.add_argument('--db',type=Path,default=scout.DB)
    p.add_argument('--limit',type=int,default=16)
    p.add_argument('--offline',action='store_true')
    args=p.parse_args(argv)
    db=scout.connect(args.db);ensure_schema(db)
    if args.command=='registry':
        print(json.dumps({str(k):l.url for k,l in LAYERS.items()},indent=2));return 0
    if args.command=='report':
        print(json.dumps({'exported_leads':write_exports(db),'mode':'REPORT_FROM_EXISTING_DB'},indent=2));return 0
    result=run(db,args.limit,args.offline)
    print(json.dumps(result,indent=2))
    if result['errors'] and not args.offline:return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
