import argparse
import hashlib
import json
import tempfile
import unittest
import urllib.error
import io
from pathlib import Path
from unittest.mock import patch

from medlit.cli import cmd_search_pubmed, cmd_recover_feedback, cmd_export_retrieval
from medlit.evolution.diagnostics import Diagnoser
from medlit.http import ApiError
from medlit.http import HttpClient
from medlit.retrieval.audit import feedback_coverage, export_retrieval
from medlit.state.store import StateStore, StateOps
from test_agent_query_workflow import CaptureConsole


class RetrievalAuditTests(unittest.TestCase):
    def test_http_500_retries_without_real_network(self):
        class Response:
            status=200
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return b'{}'
        error=urllib.error.HTTPError('https://example.org',500,'transient',{},io.BytesIO(b'error'))
        with patch('medlit.http.urllib.request.urlopen',side_effect=[error,Response()]) as call, patch('medlit.http.time.sleep'), patch('medlit.http.ssl_context',return_value=None):
            self.assertEqual(HttpClient(retries=1)._fetch('https://example.org'),b'{}')
            self.assertEqual(call.call_count,2)

    def test_missing_is_distinct_from_empty_abstract(self):
        c = feedback_coverage(['1','2'], [{'pmid':'1','abstract':''}])
        self.assertEqual(c['missing_pmids'], ['2'])
        self.assertEqual(c['no_abstract_pmids'], ['1'])

    def state(self):
        return {'question':'test', 'task_mode':'retrieval', 'accepted_query_attempt_id':'q1',
                'final_ranked_pmids':['1','2'], 'query_attempts':[{
                    'attempt_id':'q1','exact_query':'test[tiab]','pmids':['1','2'],
                    'status':'success','feedback_records':[{'pmid':'1','abstract':''}],
                    'feedback_coverage':feedback_coverage(['1','2'],[{'pmid':'1','abstract':''}])}]}

    def test_export_seal_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'export'
            export_retrieval(self.state(),output)
            manifest=json.loads((output/'manifest.sha256.json').read_text())
            for entry in manifest['files']:
                self.assertEqual(hashlib.sha256((output/entry['path']).read_bytes()).hexdigest(),entry['sha256'])
            with self.assertRaises(ValueError):
                export_retrieval(self.state(),output)
            broken=self.state()
            broken['final_ranked_pmids']=['2','1']
            with self.assertRaises(ValueError):
                export_retrieval(broken,Path(tmp)/'broken')

    def test_recovery_keeps_ranking_and_mode_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=StateStore(Path(tmp)/'state.json')
            store.save(self.state())
            args=argparse.Namespace(state=str(store.path),attempt_id='q1')
            with patch('medlit.cli.PubMedClient') as cls:
                cls.return_value.fetch_records.return_value=[{'pmid':'2','abstract':'text'}]
                self.assertEqual(cmd_recover_feedback(args,CaptureConsole()),0)
                cls.return_value.fetch_records.assert_called_once_with(['2'])
            state=store.load()
            self.assertEqual(state['final_ranked_pmids'],['1','2'])
            self.assertTrue(state['query_attempts'][0]['feedback_coverage']['complete'])
            self.assertEqual(Diagnoser().diagnose(state)['status'],'ready_to_export_retrieval')
            self.assertEqual(cmd_export_retrieval(argparse.Namespace(state=str(store.path),output_dir=str(Path(tmp)/'export')),CaptureConsole()),0)
            state=store.load()
            self.assertEqual(Diagnoser().diagnose(state)['status'],'complete')
            StateOps.clear_downstream(state)
            self.assertNotIn('retrieval_export',state)

    def test_failed_search_is_audited_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=StateStore(Path(tmp)/'state.json')
            store.init('test')
            query=Path(tmp)/'query.json'
            query.write_text(json.dumps({'attempt_id':'q1','exact_query':'test[tiab]'}))
            args=argparse.Namespace(state=str(store.path),query_file=str(query),retmax=100,max_date='',feedback_records=10)
            with patch('medlit.cli.PubMedClient') as cls:
                cls.return_value.search.side_effect=ApiError('HTTP 500')
                self.assertEqual(cmd_search_pubmed(args,CaptureConsole()),6)
            state=store.load()
            self.assertEqual(state['query_attempts'][0]['status'],'api_failed')
            self.assertEqual(state['query_attempts'][0]['pmids'],[])
            self.assertEqual(state['counters']['pubmed_queries'],1)

if __name__=='__main__':
    unittest.main()
