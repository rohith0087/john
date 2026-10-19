import json
from pathlib import Path
import tempfile
import unittest
import app


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name)/'test.db'
        self.items = json.loads((app.ROOT/'data'/'profile_examples.json').read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def test_replay_keeps_review_and_does_not_duplicate(self):
        self.assertEqual(app.ingest(self.items,self.db)['created'],6)
        row = app.current(self.db)[0]
        app.review(row['id'],1,'approved',self.db)
        self.assertEqual(app.ingest(self.items,self.db)['unchanged'],6)
        self.assertEqual(len(app.current(self.db)),6)
        kept = next(x for x in app.current(self.db) if x['id']==row['id'])
        self.assertEqual(kept['status'],'approved')
        self.assertEqual(kept['evidence_status'],'profile_only')

    def test_revision_retains_history_and_requires_new_review(self):
        app.ingest(self.items,self.db)
        before = next(x for x in app.current(self.db) if x['title']==self.items[0]['title'])
        app.review(before['id'],1,'approved',self.db)
        self.items[0]['summary'] += ' Additional context.'
        self.assertEqual(app.ingest(self.items,self.db)['revised'],1)
        after = next(x for x in app.current(self.db) if x['id']==before['id'])
        self.assertEqual((after['version'],after['status']),(2,'pending'))
        h = app.history(before['id'],self.db)
        self.assertEqual(len(h['versions']),2)
        self.assertEqual(h['reviews'][0]['status'],'approved')
        with self.assertRaises(RuntimeError):
            app.review(before['id'],1,'approved',self.db)

    def test_invalid_batch_has_no_partial_import(self):
        self.items[-1]['source_url']='javascript:alert(1)'
        with self.assertRaises(ValueError):app.ingest(self.items,self.db)
        self.assertEqual(app.current(self.db),[])

    def test_distinct_systems_remain_separate(self):
        item=dict(self.items[0],system='hca')
        app.ingest([self.items[0],item],self.db)
        self.assertEqual(len(app.current(self.db)),2)

    def test_invalid_review_does_not_change_state(self):
        app.ingest(self.items,self.db)
        row=app.current(self.db)[0]
        with self.assertRaises(ValueError):app.review(row['id'],1,'published',self.db)
        self.assertEqual(app.current(self.db)[0]['status'],'pending')


if __name__=='__main__':unittest.main()
