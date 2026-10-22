from datetime import date
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
import collector
import openai_pipeline as ai
from intelligence import normalize_article


URL = 'https://www.hcafloridahealthcare.com/about-us/newsroom/test-expansion'
TITLE = 'HCA Florida Raulerson Hospital announces emergency room expansion'
PASSAGE = 'The expansion will increase the number of emergency room beds from 14 to 25.'
TEXT = ('HCA Florida Raulerson Hospital announces plans to expand its emergency department. '
        'Construction on the more than $21 million project is expected to begin in 2026. ' + PASSAGE)
CLAIMS = [{'sentence': 'HCA Florida Raulerson Hospital plans to expand emergency room capacity from 14 to 25 beds.',
           'evidence': TEXT}]


def summary_response(sentence=None, evidence_id=2):
    return complete(json.dumps({'claims': [{'sentence': sentence or CLAIMS[0]['sentence'], 'evidence_id': evidence_id}]}))


def complete(text='', sources=None, response_id='fixture-response'):
    output = []
    if sources is not None:
        output.append({'type': 'web_search_call', 'status': 'completed',
                       'action': {'type': 'search', 'sources': [{'url': u} for u in sources]}})
    if text:
        output.append({'type': 'message', 'content': [{'type': 'output_text', 'text': text}]})
    return {'id': response_id, 'status': 'completed', 'output': output,
            'usage': {'input_tokens': 100, 'output_tokens': 50}}


class GPTPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'watch.db'
        self.config = ai.Settings(key='sk-' + 'test-placeholder-' * 2, mode='gpt')
        self.article = {'url': URL, 'title': TITLE, 'text': TEXT, 'publication_date': date.today().isoformat(),
                        'snapshot_id': 'fixture', 'source_id': 'gpt-search-hca', 'capture_method': 'http'}
        self.record, _ = normalize_article(self.article, 'hca')

    def client(self, replies):
        pending = iter(replies)
        self.payloads = []
        def transport(payload):
            self.payloads.append(payload)
            return next(pending)
        return ai.GPTClient(self.config, transport)

    def test_search_accepts_only_tool_sources_on_correct_hosts(self):
        response = complete('Guessed link: https://www.hcafloridahealthcare.com/about-us/newsroom/guess',
                            [URL + '?utm_source=test', 'https://example.com/article',
                             'http://www.hcafloridahealthcare.com/article', 'https://www.wellstar.org/articles/test',
                             'https://user:password@www.hcafloridahealthcare.com/about-us/newsroom/bad', URL])
        response['output'][-1]['content'][0]['annotations'] = [
            {'type':'url_citation','url':URL+'?utm_source=test'},
            {'type':'url_citation','url':'https://example.com/article'}]
        client = self.client([response])
        found = client.search('hca', self.path)
        self.assertEqual(found['urls'], [URL])
        payload = self.payloads[0]
        self.assertEqual(payload['tools'][0]['filters']['allowed_domains'], sorted(ai.SYSTEM_HOSTS['hca']))
        self.assertEqual(payload['tool_choice'], 'required')
        self.assertEqual(payload['max_tool_calls'], 2)
        self.assertFalse(payload['store'])

    def test_search_without_completed_tool_call_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No completed web search'):
            self.client([complete('A plausible article')]).search('hca', self.path)

    def test_summary_is_generated_cached_and_keeps_structured_facts(self):
        client = self.client([summary_response()])
        record, cached = client.summarize(self.article, self.record, self.path)
        self.assertFalse(cached)
        self.assertEqual(record['summary'], CLAIMS[0]['sentence'])
        self.assertEqual(record['metrics'], self.record['metrics'])
        self.assertFalse(record['source_checked'])
        self.assertEqual(record['evidence_status'], 'source_retrieved')
        again, cached = client.summarize(self.article, self.record, self.path)
        self.assertTrue(cached)
        self.assertEqual(again, record)
        self.assertEqual(len(self.payloads), 1)
        self.assertEqual(self.payloads[0]['text']['format']['type'], 'json_schema')
        self.assertNotIn(self.config.key, json.dumps(self.payloads))

    def test_missing_passage_and_invented_number_are_rejected(self):
        for response in [summary_response(evidence_id=999),
                         summary_response(sentence='HCA Florida plans to increase its emergency room capacity to 999 beds.')]:
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.client([response]).summarize(self.article, self.record, self.path)
        with ai.database(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM gpt_summary_cache').fetchone()[0], 0)

    def test_incomplete_response_and_refusal_do_not_generate_summary(self):
        for response in [dict(complete('partial'), status='incomplete'),
                         {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]}]:
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.client([response]).summarize(self.article, self.record, self.path)

    def run_collection(self, client, html=None):
        run_id, _ = collector.start_run(['hca'], self.path)
        body = html or f'<html><head><meta property="article:published_time" content="{date.today().isoformat()}"></head><body><main><h1>{TITLE}</h1><p>{TEXT}</p></main></body></html>'
        collector.run_collection(run_id, ['hca'], self.path, app.ingest, lambda url: body, client)
        return collector.status(self.path)['last_run']

    def test_collection_review_and_repeat_preserve_editor_corrections(self):
        client = self.client([complete(sources=[URL]), summary_response(),
                              complete(sources=[URL], response_id='new-search')])
        first = self.run_collection(client)
        self.assertEqual(first['totals']['created'], 1)
        row = app.current(self.path)[0]
        self.assertEqual(row['status'], 'pending')
        app.edit_record(row['id'], 1, {'summary': 'Editor corrected summary.', 'editor_note': 'Checked source.'}, self.path)
        app.review(row['id'], 2, 'approved', self.path)
        repeated = self.run_collection(client)
        self.assertEqual(repeated['totals']['unchanged'], 1)
        self.assertEqual(repeated['totals']['cached_summaries'], 1)
        self.assertEqual(len(self.payloads), 3)
        row = app.current(self.path)[0]
        self.assertEqual(row['summary'], 'Editor corrected summary.')
        self.assertEqual((row['version'], row['status']), (2, 'approved'))

    def test_search_failure_keeps_saved_approved_data(self):
        self.run_collection(self.client([complete(sources=[URL]), summary_response()]))
        row = app.current(self.path)[0]
        app.review(row['id'], 1, 'approved', self.path)
        before = app.current(self.path)
        broken = ai.GPTClient(self.config, lambda payload: {'status': 'failed'})
        result = self.run_collection(broken)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(app.current(self.path), before)

    def test_failed_article_fetch_does_not_summarize_search_snippets(self):
        client = self.client([complete(sources=[URL])])
        run_id, _ = collector.start_run(['hca'], self.path)
        def blocked(url):
            raise RuntimeError('Official page unavailable.')
        collector.run_collection(run_id, ['hca'], self.path, app.ingest, blocked, client)
        self.assertEqual(len(self.payloads), 1)
        self.assertEqual(app.current(self.path), [])

    def test_imported_excerpt_uses_gpt_without_becoming_verified(self):
        client = self.client([summary_response()])
        with patch('app.openai_pipeline.configured_client', return_value=client):
            app.import_article({'system': 'hca', 'url': URL, 'title': TITLE, 'text': TEXT}, self.path)
        row = app.current(self.path)[0]
        self.assertEqual(row['evidence_status'], 'imported_text')
        self.assertFalse(row['source_checked'])
        self.assertEqual(row['summary'], CLAIMS[0]['sentence'])

    def test_config_is_private_and_can_be_completed_without_restart(self):
        folder = Path(self.temp.name)
        with patch.object(ai, 'ROOT', folder), patch.dict(os.environ, {}, clear=True):
            (folder / '.env').write_text('IDN_AI_MODE=gpt\nOPENAI_API_KEY=\n')
            self.assertFalse(ai.public_status()['ready'])
            with self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
                ai.configured_client()
            (folder / '.env').write_text('IDN_AI_MODE=gpt\nOPENAI_API_KEY=' + self.config.key + '\n')
            self.assertTrue(ai.public_status()['ready'])
            self.assertNotIn(self.config.key, repr(ai.settings()))
            self.assertNotIn(self.config.key, json.dumps(ai.public_status()))
            self.assertIsInstance(ai.configured_client(), ai.GPTClient)
            with patch.dict(os.environ, {'IDN_AI_MODE': 'rules'}):
                self.assertIsNone(ai.configured_client())


if __name__ == '__main__':
    unittest.main()
