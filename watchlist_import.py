#!/usr/bin/env python3
"""Import analyst-sourced geographic watchlist candidates; never infer active listings.

No new lead is considered an approved brand expansion target. Watchlist imports
must include an independently inspectable public source; candidate selection and
licensed CRE due diligence remain human responsibilities.
"""
import argparse
import csv
import json
import re
from pathlib import Path
import scout

HEADERS=['brand','address','municipality','county','state','source_url','research_note']
JURISDICTIONS={('PA','Chester'),('PA','Delaware'),('PA','Montgomery'),('PA','Bucks'),
               ('PA','Philadelphia'),('DE','New Castle'),('NJ','Burlington'),('NJ','Camden'),
               ('NJ','Gloucester'),('NJ','Salem'),('NJ','Mercer'),('NJ','Cumberland'),('NJ','Atlantic'),('NJ','Cape May')}


def clean_address(a):
    return re.sub(r'\s+',' ',scout.normalized(a))


def inspect(db,path):
    add=[];skip=[]
    with open(path,newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        if not set(HEADERS).issubset(reader.fieldnames or []):
            raise ValueError('CSV needs columns: '+', '.join(HEADERS))
        existing={(r['brand'],clean_address(r['address'])) for r in db.execute('SELECT brand,address FROM leads')}
        ids={r['lead_id'] for r in db.execute('SELECT lead_id FROM leads')}
        counters={'Taco Bell':100,'Sheetz':100,'Bank of America':100}
        for n,r in enumerate(reader,2):
            r={k:(v or '').strip() for k,v in r.items()}
            brand=r['brand'];state=r['state'].upper();county=r['county'].title();url=r['source_url']
            reason=None
            if brand not in scout.BRAND_ORDER:reason='unknown target brand'
            elif (state,county) not in JURISDICTIONS:reason='outside configured geography'
            elif not re.match(r'^\d{1,6}\s+\S',r['address']):reason='address must begin with street number'
            elif not url.startswith('https://') or not re.match(r'^https://[a-zA-Z0-9.-]+/',url):reason='public HTTPS evidence URL required'
            elif len(r['research_note'])<15:reason='research rationale too short'
            elif (brand,clean_address(r['address'])) in existing:reason='duplicate brand/address (existing or imported)'
            if reason:
                skip.append({'line':n,'reason':reason,'brand':brand,'address':r['address']});continue
            existing.add((brand,clean_address(r['address'])))
            prefix={'Taco Bell':'T','Sheetz':'S','Bank of America':'B'}[brand]
            k=counters[brand]
            while f'{prefix}-{k:03d}' in ids:k+=1
            counters[brand]=k+1
            lid=f'{prefix}-{k:03d}';ids.add(lid)
            add.append({'lead_id':lid,'brand':brand,'address':r['address'],
                        'municipality':r['municipality'],'county':county,'state':state,
                        'offer':'UNVERIFIED—WATCHLIST ONLY','ask_usd':None,'acres':None,
                        'gate':'WATCH—NEEDS VERIFICATION','source_url':url,
                        'critical_caveat':r['research_note'],'first_observed':scout.now(),
                        'updated_utc':scout.now(),'parcel_id':None,
                        'recorded_owner_verified':0,'officially_verified_aadt':0})
    return add,skip


def load(db,path,dry_run=False):
    candidates,skipped=inspect(db,path)
    if dry_run:return {'dry_run':True,'candidates':candidates,'skipped':skipped}
    for d in candidates:
        score,quality=scout.score_lead(d)
        db.execute('''INSERT INTO leads(lead_id,brand,address,municipality,county,state,offer,ask_usd,acres,gate,source_url,
          critical_caveat,first_observed,updated_utc,parcel_id,recorded_owner_verified,officially_verified_aadt,score,score_quality,source_kind)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (d['lead_id'],d['brand'],d['address'],d['municipality'],d['county'],d['state'],d['offer'],None,None,d['gate'],
           d['source_url'],d['critical_caveat'],d['first_observed'],d['updated_utc'],None,0,0,score,quality,'Phase6 ANALYST WATCHLIST—NOT NEW LISTING'))
        scout.add_observation(db,d['lead_id'],d['offer'],None,None,d['gate'],d['source_url'],d['first_observed'],
                              'First observed in analyst watchlist; source listing/availability unverified')
    db.commit()
    return {'dry_run':False,'imported_ids':[x['lead_id'] for x in candidates],'skipped':skipped}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('file',type=Path)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--db',type=Path,default=scout.DB)
    args=p.parse_args()
    db=scout.connect(args.db)
    scout.seed(db,scout.DATA/'seed_phase3.csv')
    print(json.dumps(load(db,args.file,args.dry_run),indent=2))

if __name__=='__main__':main()
