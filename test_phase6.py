import copy
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scout
import regional_parcels as reg

class RegionalParcelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=scout.connect(Path(self.tmp.name)/'check.sqlite')
        scout.seed(self.db,scout.DATA/'seed_phase3.csv')
        reg.ensure_schema(self.db)
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def lead(self,lead_id='T-002'):
        return dict(self.db.execute('SELECT * FROM leads WHERE lead_id=?',(lead_id,)).fetchone())
    def fake_geo(self, address):
        return {'longitude':-75.5,'latitude':39.9,'matchedAddress':'363 WILMINGTON PIKE, GLEN MILLS, PA 19342'},'https://geocoding.geo.census.gov/fixture'
    def fake_fetch(self,url,params=None):
        if url.endswith('/query'):
            return {'features':[{'attributes':{'PIN':'13-00-01056-00','ADRCAT':'363 WILMINGTON PIKE','CALCULATED':0.32}}]},url+'?query=point'
        return {'capabilities':'Query','geometryType':'esriGeometryPolygon',
                'fields':[{'name':'PIN'},{'name':'ADRCAT'},{'name':'CALCULATED'},{'name':'PRIVATE_MAIL_ADDR'}]},url+'?f=json'
    def test_seven_jurisdictions_have_distinct_government_layers(self):
        self.assertGreaterEqual(len(reg.LAYERS),7)
        self.assertEqual(reg.key_for_lead({'state':'NJ','county':'Gloucester'}),('NJ','STATEWIDE'))
        self.assertEqual(reg.key_for_lead({'state':'DE','county':'New Castle'}),('DE','New Castle'))
        self.assertNotIn(('AL','Montgomery'),reg.LAYERS)
    def test_excluded_lead_is_never_queried(self):
        def impossible(*args,**kwargs):raise AssertionError('excluded lead made a network request')
        r=reg.evaluate_lead(self.db,self.lead('T-001'),fetch=impossible,geocoder=impossible)
        self.assertEqual(r['result'],'EXCLUDED_NOT_QUERIED')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM phase6_snapshots').fetchone()[0],0)
    def test_spatial_candidate_never_auto_verifies_deed(self):
        r=reg.evaluate_lead(self.db,self.lead(),fetch=self.fake_fetch,geocoder=self.fake_geo,checked='2026-10-23T12:00:00Z')
        self.assertEqual(r['result'],'GIS_CANDIDATES_NEED_REVIEW')
        x=self.db.execute("SELECT * FROM leads WHERE lead_id='T-002'").fetchone()
        self.assertEqual(x['recorded_owner_verified'],0)
        self.assertIsNone(x['parcel_id'])
        j=self.db.execute('SELECT candidates_json FROM phase6_snapshots').fetchone()[0]
        self.assertNotIn('PRIVATE_MAIL_ADDR',j)
    def test_changed_candidate_is_new_event_but_unchanged_is_not(self):
        lead=self.lead()
        reg.evaluate_lead(self.db,lead,fetch=self.fake_fetch,geocoder=self.fake_geo)
        reg.evaluate_lead(self.db,lead,fetch=self.fake_fetch,geocoder=self.fake_geo)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM phase6_events').fetchone()[0],1)
        def updated(url,params=None):
            obj,link=self.fake_fetch(url,params)
            if url.endswith('/query'):obj['features'][0]['attributes']['CALCULATED']=1.2
            return obj,link
        reg.evaluate_lead(self.db,lead,fetch=updated,geocoder=self.fake_geo)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM phase6_events').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT kind FROM phase6_events ORDER BY first_seen_utc DESC LIMIT 1').fetchone()[0] in
                         ('FIRST_GIS_OBSERVATION','GIS_SOURCE_DATA_CHANGED—REVIEW'),True)
    def test_geocode_mismatch_creates_review_hold_not_fake_parcel(self):
        def wrong(_):return {'longitude':-75.5,'latitude':39.9,'matchedAddress':'999 OTHER RD, GLEN MILLS, PA 19342'},'https://geo'
        r=reg.evaluate_lead(self.db,self.lead(),fetch=self.fake_fetch,geocoder=wrong)
        self.assertEqual(r['result'],'GEOCODE_REJECTED')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM phase6_events').fetchone()[0],0)
    def test_response_limit_requires_review_and_no_event(self):
        def limited(url,params=None):
            r,link=self.fake_fetch(url,params)
            if url.endswith('/query'):r['exceededTransferLimit']=True
            return r,link
        r=reg.evaluate_lead(self.db,self.lead(),fetch=limited,geocoder=self.fake_geo)
        self.assertEqual(r['result'],'AMBIGUOUS_QUERY_LIMIT')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM phase6_events').fetchone()[0],0)
    def test_export_only_public_gis_candidates(self):
        reg.evaluate_lead(self.db,self.lead(),fetch=self.fake_fetch,geocoder=self.fake_geo)
        output=Path(self.tmp.name)/'export'
        self.assertEqual(reg.write_exports(self.db,output),1)
        s=(output/'regional_parcel_candidates.csv').read_text()
        self.assertIn('13-00-01056-00',s)
        self.assertIn('NOT DEED',s)
        self.assertNotIn('PRIVATE_MAIL_ADDR',s)
        self.assertEqual(len((output/'regional_gis_change_log.csv').read_text().splitlines()),2)
    def test_state_postal_zip_conflict_rejected(self):
        valid,state=reg.validate_geocode_match(self.lead(),{'longitude':-75,'latitude':39.9,'matchedAddress':'363 WILMINGTON PIKE, NJ 19342'})
        self.assertFalse(valid);self.assertEqual(state,'STATE_MISMATCH')

if __name__=='__main__':unittest.main()

class WatchlistAndSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=scout.connect(Path(self.tmp.name)/'test.db')
        scout.seed(self.db,scout.DATA/'seed_phase3.csv')
        reg.ensure_schema(self.db)
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def test_proposed_watchlist_import_does_not_infer_sale(self):
        import watchlist_import
        p=Path(self.tmp.name)/'in.csv'
        p.write_text('brand,address,municipality,county,state,source_url,research_note\nSheetz,"123 Market St, Wilmington, DE 19801",Wilmington,New Castle,DE,https://www.newcastlede.gov/parcel,Government watchlist location to research\n')
        d=watchlist_import.load(self.db,p,dry_run=True)
        self.assertEqual(len(d['candidates']),1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM leads WHERE state='DE'").fetchone()[0],0)
        real=watchlist_import.load(self.db,p)
        self.assertEqual(real['imported_ids'],['S-100'])
        v=dict(self.db.execute("SELECT * FROM leads WHERE lead_id='S-100'").fetchone())
        self.assertEqual(v['gate'],'WATCH—NEEDS VERIFICATION')
        self.assertFalse(v['recorded_owner_verified'])
        self.assertIsNone(v['ask_usd'])
        self.assertEqual(watchlist_import.load(self.db,p)['imported_ids'],[])
    def test_sync_no_demo_rows_or_undisclosed_owner(self):
        import sheets_sync
        layer=reg.LAYERS[('PA','Delaware')]
        reg.persist_snapshot(self.db,dict(self.db.execute("SELECT * FROM leads WHERE lead_id='T-002'").fetchone()),
                  layer,'GIS_CANDIDATES_NEED_REVIEW',[{'attrs':{'PIN':'11-22','ADRCAT':'363 WILMINGTON PIKE'},'address_check':'STREET_NUMBER_POSSIBLE'}],
                  'https://gis.delcopa.gov/arcgis/rest/services/Parcels/Parcels_Public_Access/FeatureServer/0/query',
                  'CENSUS_ADDRESS_MATCH—POINT_NOT_BOUNDARY')
        out=sheets_sync.outbox(self.db)
        self.assertEqual(len(out['Phase6 GIS Observations']),1)
        self.assertEqual(len(out['Phase6 GIS Changes']),1)
        self.assertIn('NO RECORDED DEED',out['Phase6 GIS Observations'][0][-1])
    def test_fixture_url_not_written_to_google_sheets(self):
        import sheets_sync
        layer=reg.LAYERS[('PA','Delaware')]
        reg.persist_snapshot(self.db,dict(self.db.execute("SELECT * FROM leads WHERE lead_id='T-002'").fetchone()),
                  layer,'NO_CANDIDATE',[],'fixture:fake-parcels','NO_UNIQUE_GEOCODE')
        out=sheets_sync.outbox(self.db)
        self.assertEqual(len(out['Phase6 GIS Observations']),0)
        self.assertEqual(len(out['Phase6 GIS Changes']),0)
