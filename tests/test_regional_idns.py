import unittest
from datetime import date
import collector
from intelligence import SYSTEM_NAMES, normalize_article, recommend, validate_facts


def normalize(system, title, text):
    article=dict(title=title,text=text,url={'piedmont':'https://www.piedmont.org/news/test','wellstar':'https://www.wellstar.org/articles/test','novant':'https://www.novanthealth.org/newsroom/test'}[system],publication_date='2026-09-22',source_id='fixture',snapshot_id='fixture',capture_method='http')
    record,_=normalize_article(article,system)
    validate_facts(record)
    return record


class RegionalIDNTests(unittest.TestCase):
    def test_idn_parent_and_qualified_budget(self):
        record=normalize('piedmont','Piedmont to invest nearly $600 million in relocation hospital in Newton County','Piedmont Newton Hospital plans a relocation hospital. The project represents an investment of nearly $600 million. The hospital will include 112 new inpatient rooms.')
        self.assertEqual(record['system'],'piedmont')
        self.assertEqual(record['entity'],'Piedmont Newton')
        self.assertEqual(record['budget']['qualifier'],'nearly')
        self.assertEqual(record['metrics'],[]) # rooms are not inferred as beds
        self.assertIn('nearly $600',record['summary'])

    def test_time_qualifier_does_not_modify_money(self):
        record=normalize('piedmont','Piedmont Henry expands patient tower','Nearly two years after starting its $212 million hospital expansion, Piedmont Henry is preparing rooms for patients.')
        self.assertEqual(record['budget']['qualifier'],'reported')

    def test_pending_approval_not_authorized_capacity(self):
        record=normalize('novant','Novant Health seeks state approval for new hospital beds in new patient tower','Novant Health has applied for state approval to add 225 inpatient hospital beds in a new patient tower. The master facility plan at New Hanover Regional Medical Center represents an investment of upwards of $1 billion.')
        self.assertEqual(record['metrics'][0]['target'],225)
        self.assertIsNone(record['metrics'][0]['baseline'])
        self.assertIsNone(record['budget']) # broader plan is not this tower's budget
        rec=recommend(record,date(2026,10,16))
        self.assertIsNone(rec['visual']['growth_percent'])
        self.assertEqual(next(f['points'] for f in rec['factors'] if f['key']=='scope'),25)
        self.assertFalse(rec['visual']['scenario_available'])
        self.assertTrue(any('pending approval' in w for w in record['extraction_warnings']))

    def test_opened_facility_stays_under_parent_idn(self):
        record=normalize('wellstar','First Patients Receive Care at Wellstar Columbia County Medical Center','Wellstar Columbia County Medical Center welcomed its first patients. The new hospital will expand access to emergency and surgical care.')
        self.assertEqual(record['development_status'],'completed')
        self.assertEqual(record['system'],'wellstar')
        self.assertIn('ongoing',recommend(record,date(2026,10,16))['action_title'])

    def test_equipment_purchase_is_not_an_ownership_transaction(self):
        record=normalize('piedmont','Piedmont Rockdale acquires third hyperbaric chamber, expanding treatment','Piedmont Rockdale expands treatment capability with a hyperbaric chamber.')
        self.assertEqual(record['category'],'Expansion')
        self.assertEqual(record['development_kind'],'service_capability')

    def test_system_leadership_not_assigned_to_an_incidental_hospital(self):
        record=normalize('wellstar','Wellstar Names Kem Mullins Executive Vice President and Chief Administrative Officer','Wellstar Health System has named a chief administrative officer. He will oversee integration work at Stephens County Hospital and Mountain Lakes Medical Center.')
        self.assertEqual(record['entity'],'Wellstar Health System')
        self.assertEqual(record['entity_match'],'system_level')

    def test_specialist_expansion_is_not_a_construction_project(self):
        record=normalize('novant','Novant Health welcomes foot and ankle specialist to expand care across the Triad','Novant Health welcomes a new physician who will see patients in the Triad. The service plans to provide access to specialist care.')
        self.assertEqual(record['development_kind'],'service_capability')
        self.assertEqual(record['development_status'],'announced')
        self.assertIn('service change',recommend(record,date(2026,10,16))['action_title'])

    def test_article_templates_exclude_related_story_numbers(self):
        for system,host,marker in [('piedmont','www.piedmont.org','rich-text--body'),('wellstar','www.wellstar.org','article-content'),('novant','www.novanthealth.org','content-article-body')]:
            with self.subTest(system=system):
                html='<h1>Hospital expansion</h1><p>September 22, 2026</p><div class="'+marker+'"><p>'+('The hospital project adds capacity. '*8)+'</p></div><aside>Related story: 900 new beds.</aside>'
                parsed=collector.parse_article(html,'https://'+host+'/news/test')
                self.assertNotIn('900',parsed['text'])
                self.assertEqual(parsed['publication_date'],'2026-09-22')

    def test_discovery_keeps_official_articles_and_skips_navigation(self):
        for system,path in [('piedmont','/news/'),('wellstar','/articles/'),('novant','/newsroom/')]:
            host={'piedmont':'www.piedmont.org','wellstar':'www.wellstar.org','novant':'www.novanthealth.org'}[system]
            source=dict(id=system+'-news',system=system,index_url='https://'+host+path,max_articles=3)
            html='<a href="'+path+'new-tower">New tower</a><a href="https://example.org/news/fake">Elsewhere</a><a href="/newsroom/releases">Navigation</a>'
            self.assertEqual(collector.discover(html,source),['https://'+host+path+'new-tower'])
        self.assertEqual(len(SYSTEM_NAMES),5)


if __name__=='__main__':unittest.main()
