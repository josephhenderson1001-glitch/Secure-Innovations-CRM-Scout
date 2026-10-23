import copy
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scout
import sheets_sync

class Phase5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=scout.connect(Path(self.tmp.name)/'data.db')
        scout.seed(self.db,scout.DATA/'seed_phase3.csv')
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()
    def test_initial_outbox_excludes_baseline_and_fixture(self):
        r=sheets_sync.outbox(self.db)
        self.assertEqual([len(r[k]) for k in list(sheets_sync.HEADERS)[:3]],[0,0,0])
        fixture=scout.ROOT/'fixtures'/'philadelphia_permits_fixture.json'
        rows,uri=scout.collect_philly_permits(fixture=fixture)
        scout.save_signals(self.db,rows,uri)
        self.assertEqual(len(sheets_sync.outbox(self.db)['Phase5 Permit Event History']),0)
    def test_signal_status_change_has_immutable_new_observation(self):
        orig={'permitnumber':'TEST-100','address':'100 TEST AVE','permitissuedate':'2026-10-23','permittype':'ZONING','typeofwork':'CHANGE OF USE','status':'ISSUED'}
        self.assertEqual(scout.save_signals(self.db,[orig],'https://example.com/real-public-data'),1)
        self.assertEqual(scout.save_signals(self.db,[orig],'https://example.com/real-public-data'),0)
        change=copy.deepcopy(orig);change['status']='EXPIRED'
        self.assertEqual(scout.save_signals(self.db,[change],'https://example.com/real-public-data'),0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM signal_observations').fetchone()[0],2)
        out=sheets_sync.outbox(self.db)['Phase5 Permit Event History']
        self.assertEqual(out[-1][2],'PERMIT CONTENT OR STATUS CHANGE')
        self.assertEqual(out[-1][6],'EXPIRED')
        self.assertNotEqual(out[0][0],out[1][0])
    def test_append_only_no_duplicate_keys(self):
        rows=[['k1',1],['k2',2],['k2',3],['k3',4]]
        self.assertEqual(sheets_sync.missing_rows(rows,{'k1'}),[['k2',2],['k3',4]])
    def test_run_sync_filters_offline_fixtures(self):
        self.db.execute("INSERT INTO runs(started_utc,mode,status) VALUES('2026-10-23T00:00:00Z','OFFLINE DEMO','COMPLETED')")
        self.db.execute("INSERT INTO runs(started_utc,mode,status,warnings_json) VALUES('2026-10-23T01:00:00Z','LIVE','PARTIAL—SOURCE WARNINGS','[\"API error\"]')")
        r=sheets_sync.outbox(self.db)['Phase5 Collection Runs']
        self.assertEqual(len(r),1)
        self.assertIn('API error',r[0][7])
    def test_arcgis_date_conversion(self):
        from datetime import datetime,timezone
        ms=int(datetime(2026,10,23,tzinfo=timezone.utc).timestamp()*1000)
        self.assertEqual(scout.parse_event_date(ms),'2026-10-23')
        self.assertEqual(scout.parse_event_date('2026-10-23T04:00:00.000Z'),'2026-10-23')
    def test_score_excluded_still_zero(self):
        excluded=self.db.execute("SELECT * FROM leads WHERE lead_id='T-001'").fetchone()
        self.assertEqual(scout.score_lead(dict(excluded))[0],0)

if __name__=='__main__': unittest.main()
