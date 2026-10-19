import copy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
import collector
from intelligence import build_visual, normalize_article, recommend, validate_facts

URL = 'https://www.hcafloridahealthcare.com/about-us/newsroom/raulerson-hospital-announces-21-million-dollar-emergency-room-expansion'
TITLE = 'HCA Florida Raulerson Hospital announces emergency room expansion'
TEXT = ('HCA Florida Raulerson Hospital announces plans to expand its emergency department.\n'
        'Construction on the more than $21 million project is expected to begin in late summer 2026, with completion anticipated near the end of 2027.\n'
        'The expansion will increase the number of emergency room beds from 14 to 25.\n'
        'The department cared for more than 30,000 patients in both 2024 and 2025.')


def article(text=TEXT, title=TITLE):
    return dict(url=URL, title=title, text=text, publication_date='2026-05-27',
                source_id='hca-florida', snapshot_id='fixture', capture_method='http')


def html(text=TEXT):
    return ('<html><head><title>'+TITLE+' | HCA Florida</title></head><body><nav>'+('Navigation ' * 300)+
            '</nav><main><h1>'+TITLE+'</h1><p>May 27, 2026</p><div class="rich-text-content">'+
            ''.join('<p>'+line+'</p>' for line in text.split('\n'))+
            '</div></main><footer><h2>Related news</h2>October 16, 2026</footer></body></html>')


class ExtractionTest(unittest.TestCase):
    def test_extracts_a_sourced_capacity_comparison_and_schedule(self):
        record, _ = normalize_article(article(), 'hca')
        validate_facts(record)
        self.assertEqual(record['entity'], 'HCA Florida Raulerson Hospital')
        self.assertEqual(record['development_status'], 'planned')
        self.assertEqual(record['metrics'][0]['baseline'], 14)
        self.assertEqual(record['metrics'][0]['target'], 25)
        self.assertEqual(record['budget']['amount'], 21000000)
        self.assertEqual(record['budget']['qualifier'], 'more_than')
        visual = build_visual(record)
        self.assertEqual(visual['growth_percent'], 78.6)
        self.assertTrue(visual['scenario_available'])
        self.assertIn('2027', record['milestones'][0]['date_text'])

    def test_header_date_is_not_taken_from_navigation_or_related_story(self):
        result = collector.parse_article(html(), URL)
        self.assertEqual(result['publication_date'], '2026-05-27')
        self.assertNotIn('Navigation', result['text'])
        self.assertNotIn('Related news', result['text'])

    def test_completed_expansion_does_not_imply_open_construction_purchasing(self):
        record, _ = normalize_article(article(title='HCA Florida Raulerson Hospital completes emergency room expansion'), 'hca')
        rec = recommend(dict(record,id='example',status='pending'), date(2026,10,16))
        self.assertIn('ongoing', rec['action_title'])
        self.assertEqual(rec['visual']['basis'], 'reported')
        self.assertFalse(rec['visual']['scenario_available'])

    def test_zero_or_missing_baseline_never_produces_a_growth_percentage(self):
        record, _ = normalize_article(article(), 'hca')
        record['metrics'][0]['baseline'] = 0
        self.assertIsNone(build_visual(record)['growth_percent'])
        self.assertFalse(build_visual(record)['scenario_available'])
        record['metrics'][0]['baseline'] = None
        self.assertIsNone(build_visual(record)['growth_percent'])

    def test_patient_volume_is_not_misinterpreted_as_bed_capacity(self):
        text='Visits increased from 14 to 25 percent. The hospital has 100 beds. '
        text+='The hospital announced an expansion; project details will be provided later. '*3
        record, _ = normalize_article(article(text=text), 'hca')
        self.assertEqual(record['metrics'], [])
        self.assertEqual(build_visual(record)['type'], 'timeline')

    def test_unknown_date_receives_no_freshness_points(self):
        source=article();source['publication_date']=None
        record, _ = normalize_article(source, 'hca')
        result=recommend(record,date(2026,10,16))
        self.assertEqual(next(f['points'] for f in result['factors'] if f['key']=='recency'),0)
        self.assertIsNone(record['source_date'])

    def test_awards_are_excluded_and_unknown_facility_stays_at_system_level(self):
        record, reason=normalize_article(article(title='HCA hospitals earn patient safety awards'), 'hca')
        self.assertIsNone(record)
        source=article(text='A newly named facility announces a patient tower expansion. '*6,title='A new patient tower is announced')
        record, _ = normalize_article(source,'hca')
        self.assertEqual(record['entity'],'HCA Healthcare')
        self.assertEqual(record['entity_match'],'system_only')

    def test_financial_comparison_keeps_units_and_has_no_forecast(self):
        source=article(title='HCA Healthcare Reports Second Quarter 2026 Results',text='Revenues totaled $17.2 billion, compared to $16.1 billion in the same period of the prior year. '+('The release reports financial results. '*6))
        record,_=normalize_article(source,'hca');validate_facts(record)
        visual=build_visual(record)
        self.assertEqual(visual['type'],'financial')
        self.assertEqual(visual['baseline'],16100000000)
        self.assertEqual(visual['target'],17200000000)
        self.assertNotIn('forecast', visual.get('basis',''))

    def test_invalid_capacity_and_cross_facility_comparison_are_rejected(self):
        record,_=normalize_article(article(),'hca')
        for change in [{'baseline':30},{'target':float('nan')},{'entity':'A different hospital'}]:
            with self.subTest(change=change):
                bad=copy.deepcopy(record);bad['metrics'][0].update(change)
                with self.assertRaises(ValueError):validate_facts(bad)

    def test_unconfigured_hosts_and_credentials_are_not_fetched(self):
        for value in ['https://127.0.0.1/private','https://user:password@www.adventhealth.com/news/story','http://www.adventhealth.com/news/story']:
            with self.assertRaises(ValueError):collector.allowed_url(value)

    def test_leadership_appointment_does_not_inherit_a_project_stage_from_strategy_text(self):
        source=article(title='HCA Florida North Florida Hospital names Stephanie Tijerina chief operating officer',text='The new chief operating officer plans to expand quality programs. '+TEXT)
        record,_=normalize_article(source,'hca')
        self.assertEqual(record['category'],'Leadership')
        self.assertEqual(record['development_status'],'announced')
        self.assertEqual(record['milestones'],[])


class LiveStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'watch.db'
        self.config=Path(self.temp.name)/'collectors.json'
        self.config.write_text(json.dumps([dict(id='hca-florida',system='hca',name='Test source',index_url='https://www.hcafloridahealthcare.com/about-us/newsroom',kind='official',max_articles=1,seeds=[URL],note='Test fixture')]),encoding='utf-8')

    def tearDown(self): self.temp.cleanup()

    def run_collect(self,fetcher):
        run_id,_=collector.start_run(['hca'],self.path)
        with patch.object(collector,'CONFIG',self.config):collector.run_collection(run_id,['hca'],self.path,app.ingest,fetcher)
        with patch.object(collector,'CONFIG',self.config):return collector.status(self.path)['last_run']

    def fetcher(self,url):return html() if url==URL else '<main><h1>Newsroom</h1></main>'

    def test_repeat_collection_does_not_duplicate_or_erase_editor_corrections(self):
        self.assertEqual(self.run_collect(self.fetcher)['totals']['created'],1)
        before=app.current(self.path)[0]
        app.edit_record(before['id'],before['version'],{'summary':'Reviewed project context.','editor_note':'Checked against the captured test article.','source_checked':True},self.path)
        edited=app.current(self.path)[0]
        app.review(edited['id'],edited['version'],'approved',self.path)
        self.assertEqual(self.run_collect(self.fetcher)['totals']['unchanged'],1)
        after=app.current(self.path)[0]
        self.assertEqual(after['summary'],'Reviewed project context.')
        self.assertEqual(after['version'],2)
        self.assertEqual(after['status'],'approved')

    def test_changed_source_retains_old_version_and_requires_review(self):
        self.run_collect(self.fetcher);before=app.current(self.path)[0]
        app.review(before['id'],1,'approved',self.path)
        result=self.run_collect(lambda url:html(TEXT.replace('14 to 25','14 to 27')) if url==URL else '<h1>News</h1>')
        self.assertEqual(result['totals']['revised'],1)
        after=app.current(self.path)[0]
        self.assertEqual((after['version'],after['status']),(2,'pending'))
        self.assertEqual(after['metrics'][0]['target'],27)
        self.assertEqual(len(app.history(after['id'],self.path)['versions']),2)
        with self.assertRaises(RuntimeError):app.edit_record(after['id'],1,{'editor_note':'Stale correction'},self.path)

    def test_source_failure_keeps_the_previous_valid_data(self):
        self.run_collect(self.fetcher)
        before=app.current(self.path)
        def unavailable(url):raise RuntimeError('Public source unavailable.')
        result=self.run_collect(unavailable)
        self.assertEqual(result['status'],'failed')
        self.assertGreater(result['totals']['failed'],0)
        self.assertEqual(app.current(self.path),before)

    def test_correction_cannot_display_numbers_absent_from_the_source(self):
        self.run_collect(self.fetcher);r=app.current(self.path)[0]
        metrics=copy.deepcopy(r['metrics']);metrics[0]['target']=999
        with self.assertRaises(ValueError):app.edit_record(r['id'],1,{'metrics':metrics,'editor_note':'Test unsupported figure'},self.path)
        self.assertEqual(app.current(self.path)[0]['version'],1)

    def test_canonical_import_replays_and_keeps_provenance(self):
        payload=dict(system='hca',url=URL+'?utm_source=test',title=TITLE,text=TEXT,publication_date='2026-05-27')
        self.assertEqual(app.import_article(payload,self.path)['created'],1)
        self.assertEqual(app.import_article(payload,self.path)['unchanged'],1)
        r=app.current(self.path)[0]
        saved=collector.snapshot(r['snapshot_id'],self.path)
        self.assertEqual(saved['capture_method'],'manual_import')
        self.assertEqual(saved['body'],TEXT)
        self.assertEqual(r['source_url'],URL)
        self.assertEqual(r['status'],'pending')

    def test_hca_discovery_reads_initial_newsroom_results(self):
        source=json.loads(self.config.read_text())[0]
        data='<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'defaultResponse':{'results':[{'url':URL,'title':TITLE}]}})+'</script>'
        self.assertEqual(collector.discover(data,source),[URL])


if __name__=='__main__':unittest.main()
