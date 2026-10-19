import copy
from datetime import date, timedelta
import json
from pathlib import Path
import unittest

from recommendations import fingerprint, rank_signals


class RecommendationTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.items = json.loads((root / 'data' / 'profile_examples.json').read_text(encoding='utf-8'))
        self.records = [dict(item, id=str(index), status='pending', version=1) for index, item in enumerate(self.items)]
        self.books = json.loads((root / 'data' / 'recommendation_playbooks.json').read_text(encoding='utf-8'))
        self.today = date(2026, 10, 15)

    def rank(self, records=None):
        return rank_signals(self.records if records is None else records, self.today, self.books)['recommendations']

    def test_prioritizes_broad_facility_developments_over_narrow_education_deal(self):
        ranked = self.rank()
        self.assertIn('Villages', ranked[0]['action_title'])
        self.assertIn('college', ranked[-1]['action_title'])
        self.assertEqual([r['score'] for r in ranked], [72, 68, 66, 61, 47, 41])
        for r in ranked:
            self.assertEqual(r['score'], sum(f['points'] for f in r['factors']))
            self.assertTrue(r['assessment_current'])
            self.assertTrue(r['steps'])

    def test_rejecting_top_item_removes_it_and_approval_does_not_verify_evidence(self):
        top = self.rank()[0]
        next(r for r in self.records if r['id'] == top['id'])['status'] = 'rejected'
        ranked = self.rank()
        self.assertNotIn(top['id'], [r['id'] for r in ranked])
        self.records[0]['status'] = 'approved'
        approved = next(r for r in self.rank() if r['id'] == '0')
        self.assertEqual(next(f['points'] for f in approved['factors'] if f['key'] == 'evidence'), 0)
        self.assertEqual(approved['evidence_status'], 'profile_only')

    def test_revised_evidence_cannot_inherit_previous_editorial_assessment(self):
        changed = copy.deepcopy(self.records[0])
        changed['summary'] = 'The project has been cancelled.'
        result = self.rank([changed])[0]
        self.assertFalse(result['assessment_current'])
        self.assertNotIn('Carrollwood', result['action_title'])
        self.assertEqual([f['points'] for f in result['factors'][:3]], [0, 0, 0])

    def test_recency_boundaries_and_future_dates(self):
        for age, points in [(-1,0),(0,15),(30,15),(31,10),(90,10),(91,5),(180,5),(181,0)]:
            with self.subTest(age=age):
                record = dict(self.records[0], source_date=(self.today - timedelta(days=age)).isoformat())
                result = self.rank([record])[0]
                self.assertEqual(next(f['points'] for f in result['factors'] if f['key'] == 'recency'), points)

    def test_ties_are_stable_and_use_date_then_id(self):
        records = [dict(self.records[0], id=key) for key in ['z', 'a']]
        self.assertEqual([r['id'] for r in self.rank(records)], ['a', 'z'])
        records[0]['source_date'] = '2026-06-19'
        self.books[records[0]['source_url']]['evidence_digest'] = fingerprint(records[0])
        # Independent source records are needed to retain equal editorial factors.
        records[1]['source_url'] += '?copy'
        self.books[records[1]['source_url']] = copy.deepcopy(self.books[records[0]['source_url']])
        self.books[records[1]['source_url']]['evidence_digest'] = fingerprint(records[1])
        self.assertEqual([r['id'] for r in self.rank(records)], ['z', 'a'])

    def test_empty_and_fully_rejected_inputs_have_no_recommendations(self):
        self.assertEqual(self.rank([]), [])
        self.assertEqual(self.rank([dict(r, status='rejected') for r in self.records]), [])


if __name__ == '__main__':
    unittest.main()
