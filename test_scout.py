import csv
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scout
class BotTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory()
  self.db=scout.connect(Path(self.t.name)/'state.db')
  count=scout.seed(self.db,scout.DATA/'seed_phase3.csv')
  self.assertEqual(count,16)
 def tearDown(self):self.db.close();self.t.cleanup()
 def test_idempotent_baseline(self):
  self.assertEqual(scout.seed(self.db,scout.DATA/'seed_phase3.csv'),0)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM leads').fetchone()[0],16)
 def test_excluded_score_hard_zero(self):
  x=self.db.execute("SELECT * FROM leads WHERE lead_id='T-001'").fetchone()
  self.assertEqual(x['score'],0)
 def test_hold_cap(self):
  x=self.db.execute("SELECT * FROM leads WHERE lead_id='S-002'").fetchone()
  self.assertLessEqual(x['score'],49)
 def test_fixture_dedup(self):
  fixture=scout.ROOT/'fixtures'/'philadelphia_permits_fixture.json'
  events,source=scout.collect_philly_permits(fixture=fixture)
  self.assertEqual(scout.save_signals(self.db,events,source),2)
  self.assertEqual(scout.save_signals(self.db,events,source),0)
 def test_manual_excluded_cannot_reopen(self):
  c=Path(self.t.name)/'changes.csv'
  with open(c,'w',newline='') as f:
   wr=csv.DictWriter(f,fieldnames=['lead_id','offer','ask_usd','acres','gate','source_url','analyst_approved','observed_date']);wr.writeheader()
   wr.writerow(dict(lead_id='T-001',offer='For sale',ask_usd=100000,acres=1.5,gate='REVIEW',source_url='https://example.org',analyst_approved='yes',observed_date='2026-10-24'))
  n,skipped=scout.ingest_reviewed_csv(self.db,c)
  self.assertEqual(n,0)
  self.assertEqual(len(skipped),1)
 def test_true_changed_lead_only_once(self):
  x=self.db.execute("SELECT * FROM leads WHERE lead_id='B-002'").fetchone()
  self.assertTrue(scout.add_observation(self.db,'B-002',x['offer'],1800000,x['acres'],x['gate'],x['source_url'],'2026-10-24','TEST ONLY'))
  self.assertFalse(scout.add_observation(self.db,'B-002',x['offer'],1800000,x['acres'],x['gate'],x['source_url'],'2026-10-24','TEST ONLY'))
if __name__=='__main__':unittest.main()
