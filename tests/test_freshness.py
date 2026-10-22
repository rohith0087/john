import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import app
import openai_pipeline as ai
from intelligence import canonical_url, classify, normalize_article, extract_budget
from recommendations import rank_signals, unique_sources


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'watch.db'
        self.url = 'https://www.piedmont.org/news/piedmont-to-invest-nearly-$600-million-in-relocation-hospital'
        article = dict(url=self.url, title='Piedmont Newton plans a new hospital',
                       text='Piedmont Newton plans a new hospital. The project represents an investment of nearly $600 million.',
                       publication_date=date.today().isoformat(),snapshot_id='fixture',source_id='fixture',capture_method='http')
        self.item, _ = normalize_article(article, 'piedmont')

    def test_real_opening_and_hospital_approval_headlines_are_supported(self):
        for title in ['Novant Health approved to build its first hospital in Lincoln County',
                      'Piedmont Athens Regional opens Building 400 at Oconee Health Campus',
                      'Wellstar Opens New Locations in Dallas']:
            with self.subTest(title=title):
                self.assertEqual(classify(title, '')[0], 'Expansion')
        self.assertIsNone(classify('Piedmont Heart recognized as best in Southeast for cardiology', '')[0])

    def test_approval_to_build_keeps_project_in_planned_stage(self):
        article = dict(url='https://www.novanthealth.org/newsroom/lincoln',
                       title='Novant Health approved to build its first hospital in Lincoln County',
                       text='Novant Health received approval to build a 24-bed community hospital. It is expected to open in 2031.',
                       publication_date=date.today().isoformat(),snapshot_id='fixture',source_id='fixture',capture_method='http')
        row, _ = normalize_article(article, 'novant')
        self.assertEqual(row['development_status'], 'planned')

    def test_url_spelling_does_not_duplicate_or_reset_reviewed_source(self):
        app.ingest([self.item],self.path,origin='collector')
        original=app.current(self.path)[0]
        app.review(original['id'],1,'approved',self.path)
        alias=copy.deepcopy(self.item)
        alias['source_url']=self.url.replace('$','%24')
        counts=app.ingest([alias],self.path,origin='collector')
        self.assertEqual(counts,dict(created=0,revised=0,unchanged=1))
        self.assertEqual(len(app.current(self.path)),1)
        self.assertEqual(app.current(self.path)[0]['status'],'approved')
        self.assertEqual(canonical_url(alias['source_url']),self.url)
        self.assertIn('%2F',canonical_url('https://www.piedmont.org/news/a%2fb'))

    def test_old_alias_record_does_not_bypass_canonical_review_decision(self):
        canonical_id=hashlib.sha256(('piedmont|'+self.url).encode()).hexdigest()[:24]
        primary=dict(self.item,id=canonical_id,status='rejected',version=2)
        alias=dict(self.item,id='historical-encoded-url',source_url=self.url.replace('$','%24'),status='approved',version=1)
        self.assertEqual(unique_sources([alias,primary]),[primary])
        self.assertEqual(rank_signals([alias,primary])['recommendations'],[])

    def test_search_uses_recent_window_and_known_source_context(self):
        app.ingest([self.item],self.path)
        payloads=[]
        def transport(payload):
            payloads.append(payload)
            return {'status':'completed','id':'fixture','output':[{'type':'web_search_call','status':'completed','action':{'sources':[]}}]}
        client=ai.GPTClient(ai.Settings(mode='gpt',lookback_days=30),transport)
        client.search('piedmont',self.path)
        self.assertIn((date.today()-timedelta(days=30)).isoformat(),payloads[0]['input'])
        self.assertIn(self.url,payloads[0]['input'])
        self.assertIn('newest qualifying',payloads[0]['input'])

    def test_search_ignores_known_newsroom_index_pages(self):
        response={'output':[{'type':'web_search_call','status':'completed','action':{'sources':[
            {'url':'https://investor.hcahealthcare.com/news/default.aspx'},
            {'url':'https://www.hcafloridahealthcare.com/about-us/newsroom'},
            {'url':'https://www.hcafloridahealthcare.com/about-us/newsroom/new-hospital'}]}}]}
        self.assertEqual(ai.cited_urls(response,'hca'),['https://www.hcafloridahealthcare.com/about-us/newsroom/new-hospital'])

    def test_cumulative_investment_is_not_a_single_project_budget(self):
        self.assertIsNone(extract_budget('Since joining Piedmont Healthcare in 2021, the hospital has invested more than $60 million in facility expansions, advanced technology, infrastructure improvements and clinical programs.'))
        self.assertEqual(extract_budget('The hospital expansion project represents an investment of more than $60 million.')['amount'],60000000)

    def test_background_sources_do_not_displace_selected_recent_articles(self):
        chosen='https://www.piedmont.org/news/recent-opening'
        response={'output':[
            {'type':'web_search_call','status':'completed','action':{'sources':[{'url':self.url}]}},
            {'type':'message','content':[{'type':'output_text','text':'A recent opening.',
                                        'annotations':[{'type':'url_citation','url':chosen}]}]}]}
        self.assertEqual(ai.cited_urls(response,'piedmont'),[chosen])
        response['output'][-1]['content'][0]={'type':'output_text','text':'No qualifying recent articles found.','annotations':[]}
        self.assertEqual(ai.cited_urls(response,'piedmont'),[])


if __name__=='__main__':
    unittest.main()
