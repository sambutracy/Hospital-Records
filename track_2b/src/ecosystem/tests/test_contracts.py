"""Fixture safety and independent scoring contracts; no provider calls."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
import requests
from ecosystem import prepare,run,evaluate,environment
from ecosystem.client import Client,loopback_login_cookies,provision
from ecosystem.reporting import distribution,public_case,human_review_summary


class EcosystemContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite=json.loads((prepare.PUBLIC/'population.json').read_text(encoding='utf-8'))

    def test_profiles_preserve_empty_patient_and_history_capacity(self):
        people,actors,docs=run.selected(self.suite,'functional')
        self.assertEqual((len(people),len(actors),len(docs)),(15,10,308))
        self.assertEqual([d for d in docs if d['patient']=='P14'],[])
        self.assertEqual(sum(d['patient']=='P13' for d in docs),100)
        people,actors,docs=run.selected(self.suite,'smoke')
        self.assertEqual((len(people),len(actors),len(docs)),(3,3,23))
        self.assertEqual(len(run.selected(self.suite,'stress')[0]),50)

    def test_mixed_patient_documents_are_rejected(self):
        suite=copy.deepcopy(self.suite)
        suite['documents'][0]['source_patient_id']='some-other-patient'
        with self.assertRaisesRegex(ValueError,'Mixed source patients'):prepare.validate_manifest(suite)

    def test_path_escape_and_windows_drive_are_rejected(self):
        for path in ('../outside','C:/Windows/system.ini',str(prepare.RUNTIME.parent/'other')):
            with self.subTest(path=path),self.assertRaises(ValueError):prepare.runtime_path(path)
        self.assertTrue(prepare.runtime_path('prepared/a.pdf').is_relative_to(prepare.RUNTIME.resolve()))

    def test_tampered_original_is_rejected_before_network_use(self):
        suite=copy.deepcopy(self.suite)
        with tempfile.TemporaryDirectory() as directory,patch.object(prepare,'RUNTIME',Path(directory)):
            doc=suite['documents'][0]
            doc.pop('text_path',None)
            target=prepare.runtime_path(doc['prepared_path']);target.parent.mkdir(parents=True);target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):prepare.validate_manifest(suite)

    def test_ledger_cannot_resume_against_another_population(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(run,'RUNTIME',Path(directory)):
            prepare.write_json(Path(directory)/'seed-state.json',{'version':prepare.VERSION,'population_sha256':'changed'})
            with self.assertRaisesRegex(ValueError,'different population'):run.ledger()

    def test_rank_metrics_keep_abstention_and_fixed_denominators(self):
        score=evaluate.retrieval_scores(['a','b'],['c','b','b'])
        self.assertEqual(score['recall_at_5'],.5)
        self.assertEqual(score['precision_at_5'],.2)
        self.assertEqual(score['returned_precision'],.5)
        self.assertEqual(score['reciprocal_rank'],.5)
        self.assertTrue(evaluate.retrieval_scores([],[])['correct_abstention'])
        self.assertIsNone(evaluate.retrieval_scores([],[])['recall_at_5'])
        self.assertFalse(evaluate.retrieval_scores([],['invented'])['correct_abstention'])

    def test_cookie_adapter_is_limited_to_isolated_realm(self):
        session=requests.Session()
        session.cookies.set('KC_RESTART','test',domain='127.0.0.1',path='/realms/continuity/',secure=True)
        session.cookies.set('sessionid','test',domain='127.0.0.1',path='/',secure=True)
        session.cookies.set('KC_RESTART','test',domain='example.org',path='/realms/continuity/',secure=True)
        loopback_login_cookies(session)
        flags={(c.name,c.domain):c.secure for c in session.cookies}
        self.assertFalse(flags[('KC_RESTART','127.0.0.1')])
        self.assertTrue(flags[('sessionid','127.0.0.1')])
        self.assertTrue(flags[('KC_RESTART','example.org')])
        with patch.object(environment,'KEYCLOAK','http://example.org'),self.assertRaises(ValueError):loopback_login_cookies(session)

    def test_population_operations_cannot_overlap(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(environment,'RUNTIME',Path(directory)):
            with environment.operation_lock():
                with self.assertRaisesRegex(ValueError,'Another synthetic population operation'):
                    with environment.operation_lock():pass
            with environment.operation_lock():pass

    def test_existing_account_requires_exact_saved_subject_without_password_reset(self):
        session=Mock();session.headers={}
        session.post.return_value=Mock(status_code=200,json=lambda:{'access_token':'synthetic-test-token'})
        session.get.return_value=Mock(status_code=200,json=lambda:[{'id':'subject-one','username':'ecosystem.p01'}])
        saved={'P01':{'username':'ecosystem.p01','password':'fictional-password','keycloak_subject':'subject-one'}}
        with patch('ecosystem.client.requests.Session',return_value=session),patch.object(environment,'credentials',return_value={'KEYCLOAK_ADMIN_PASSWORD':'fictional'}),patch.object(environment,'accounts',return_value=saved),patch.object(environment,'save_accounts'):
            provision([{'id':'P01','account':'ecosystem.p01'}])
            self.assertEqual(session.post.call_count,1)
            saved['P01']['keycloak_subject']='different-subject'
            with self.assertRaisesRegex(ValueError,'not owned by this fixture'):
                provision([{'id':'P01','account':'ecosystem.p01'}])
            self.assertEqual(session.post.call_count,2) # administrator token only

    def test_resource_summary_does_not_invent_missing_samples(self):
        self.assertEqual(distribution([None]),{'n':0})
        self.assertEqual(distribution([1,None,3]),{'n':2,'min':1,'median':2,'max':3})

    def test_expired_fixture_reauth_uses_fresh_cookies_and_same_identity(self):
        client=Client({'username':'fictional','password':'fictional-only'})
        old=client.http;client.data={'expires_at':0};client.user='actor';client.workspace='workspace'
        session=Mock();session.headers={};session.cookies=requests.cookies.RequestsCookieJar()
        session.cookies.set('csrftoken','fictional-csrf')
        session.post.side_effect=[Mock(url=environment.KEYCLOAK+'/login',text='<form id="kc-form-login" action="'+environment.KEYCLOAK+'/authenticate"></form>'),Mock(url=environment.APP+'/app/')]
        payload={'actor':{'id':'actor'},'contexts':[{'workspace_id':'workspace','capacity':'Self'}]}
        session.get.side_effect=[Mock(status_code=200),Mock(status_code=200,json=lambda:payload)]
        with patch.object(old,'close') as close,patch('ecosystem.client.requests.Session',return_value=session):
            client.sign_in();close.assert_called_once()
        self.assertEqual((client.user,client.workspace),('actor','workspace'))
        self.assertEqual(session.post.call_args_list[1].kwargs['data']['username'],'fictional')

    def test_report_keeps_failed_abstention_separate_from_success(self):
        case={'kind':'search','patient':'P15','task':{'id':'missing','state':'failed','error_code':'invalid_model_output',
          'configuration':{'temperature':0}},'schema_and_source_quotes_valid':False,'model_retrieval':None}
        with patch('ecosystem.reporting.capture_for',return_value={}):row=public_case('q06',case,{}, {},[])
        self.assertIsNone(row['model_retrieval'])
        self.assertTrue(row['model_attempted'])
        self.assertEqual(row['clinical_semantic_validity'],'not_established')

    def test_report_uses_actual_protocol_instead_of_mislabeling_a_repeated_old_case(self):
        case={'kind':'search','patient':'P01','task':{'id':'fixture','state':'completed',
            'configuration':{'context_serialization':'local-evidence-v4'},'result':{}}}
        reference={'scope':'local_cpu_v2_followup','execution_requirement':'local-evidence-v2; frozen comparison'}
        with patch('ecosystem.reporting.capture_for',return_value={}):row=public_case('cpu2-q01',case,reference,{},[])
        self.assertEqual(row['requested_scope'],'local_cpu_v2_followup')
        self.assertEqual(row['scope'],'local_cpu_v4_followup')
        self.assertFalse(row['protocol_requirement_matches'])

    def test_exact_excerpt_with_dangling_qualification_is_flagged_separately(self):
        case={'kind':'packet_overview','patient':'P15','task':{'id':'fixture','state':'completed',
            'result':{'items':[{'text':'A conflicting source says the current strength is','citations':[]}]}}}
        with patch('ecosystem.reporting.capture_for',return_value={}):row=public_case('boundary',case,{}, {},[])
        self.assertEqual(row['excerpt_boundary_warnings'],[1])
        self.assertEqual(row['clinical_semantic_validity'],'not_established')

    def test_report_distinguishes_supplied_and_truncated_reference_spans(self):
        case={'kind':'search','patient':'P11','task':{'id':'fixture','state':'completed','configuration':{
          'source_snapshots':[{'source_version_id':'uuid-1'}]},'result':{}}}
        capture={'request':{'messages':[{'content':json.dumps({'sources':[{'source_id':'s1','chunks':[
          {'text':'Beginning of page one.'}]}]})}]},'response':{}}
        reference={'expected_evidence':[{'document':'fixture-doc','page':2,'quote':'BP 132/84'}]}
        with patch('ecosystem.reporting.capture_for',return_value=capture):
            row=public_case('q07',case,reference,{'uuid-1':'fixture-doc'},[])
        self.assertFalse(row['reference_span_screens'][0]['full_quote_visible'])

    def test_rejected_metadata_candidate_is_not_counted_as_usable(self):
        expected={'document_type':'consultation_note','facility_name':'Fictional clinic',
          'document_date':{'precision':'year','year':2025,'month':None,'day':None}}
        candidate={**expected,'document_date':{'precision':'month','year':2025,'month':12,'day':None}}
        case={'kind':'metadata','patient':'P15','software_job':{'id':'fixture','state':'failed','configuration':{'temperature':0}},
          'schema_and_source_quotes_valid':False,'field_correct':None}
        capture={'response':{'choices':[{'message':{'content':json.dumps(candidate)}}]}}
        with patch('ecosystem.reporting.capture_for',return_value=capture):
            row=public_case('metadata-year',case,{'expected':expected},{},[])
        self.assertEqual(row['invented_date_components'],['month'])
        self.assertTrue(row['raw_field_matches']['document_type'])
        self.assertFalse(row['raw_field_matches']['document_date'])
        self.assertIsNone(row['field_correct'])
        self.assertFalse(row['schema_and_source_quotes_valid'])

    def test_runtime_gate_requires_two_near_timeout_local_access_failures(self):
        def failed(url='http://inference:8080/v1',latency=300,error='model_access_failed'):
            return {'task':{'state':'failed','error_code':error,'latency_seconds':latency,
                'configuration':{'base_url':url,'request_timeout_seconds':300}}}
        with tempfile.TemporaryDirectory() as directory,patch.object(evaluate,'RUNTIME',Path(directory)):
            target=Path(directory)/'runtime-gate.json'
            evaluate.runtime_failure_gate({'cases':{'first':failed(),'invalid':failed(error='invalid_model_output'),
                'fast':failed(latency=1),'remote':failed(url='https://example.org/v1')}})
            self.assertFalse(target.exists())
            evaluate.runtime_failure_gate({'cases':{'first':failed(),'second':failed(latency=299)}})
            gate=json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(gate['failed_cases'],['first','second'])
            self.assertTrue(gate['compact_single_source_controls_permitted'])

    def test_runtime_gate_uses_dispatch_wall_time_when_failed_task_latency_is_null(self):
        case={'dispatch_elapsed_seconds':303,'task':{'state':'failed','error_code':'model_access_failed',
            'latency_seconds':None,'configuration':{'base_url':'http://inference:8080/v1','request_timeout_seconds':300}}}
        with tempfile.TemporaryDirectory() as directory,patch.object(evaluate,'RUNTIME',Path(directory)):
            evaluate.runtime_failure_gate({'cases':{'q01':case,'o01':copy.deepcopy(case)}})
            self.assertTrue((Path(directory)/'runtime-gate.json').exists())

    def test_rejected_summary_retains_candidate_without_claiming_acceptance(self):
        case={'kind':'packet_overview','patient':'P14','task':{'id':'fixture','state':'failed',
            'error_code':'invalid_model_output','configuration':{},'result':None}}
        capture={'response':{'choices':[{'message':{'content':json.dumps({'items':[{'text':'Unsupported visit date'}]})}}]}}
        with patch('ecosystem.reporting.capture_for',return_value=capture):
            row=public_case('co01',case,{}, {},[])
        self.assertEqual(row['candidate_summary_texts'],['Unsupported visit date'])
        self.assertFalse(row['candidate_summary_accepted'])
        self.assertIsNone(row['validated_answer'])

    def test_inconclusive_human_response_is_not_a_correctness_assessment(self):
        case={'case':'co02','kind':'packet_overview','configuration':{'context_sha256':'context'},
            'validated_answer':{'items':[{'text':'Source-supported candidate'}]}}
        review={'case':'co02','judgement':'unable_to_assess',
            'reviewed_output_sha256':prepare.sha(b'Source-supported candidate'),'reviewed_context_sha256':'context'}
        result=human_review_summary([review],[case])
        self.assertEqual((result['status'],result['assessed_cases'],result['inconclusive_cases']),('inconclusive',0,1))
        review['reviewed_context_sha256']='different-context'
        with self.assertRaisesRegex(ValueError,'does not match'):human_review_summary([review],[case])

    def test_authored_pdf_preserves_unicode_and_is_deterministic(self):
        from pypdf import PdfReader
        doc={'id':'P01-X-001','document_type':'lab_report','document_date':prepare.date_parts('2026-01-02'),
          'facility':'Fictional clinic','source_document_id':'authored:test','text':'12.1 g/dL; café; 37 °C; no asthma.'}
        first=prepare.pdf_bytes(doc);self.assertEqual(first,prepare.pdf_bytes(doc))
        text=PdfReader(io.BytesIO(first)).pages[0].extract_text()
        self.assertIn(doc['text'],text)

    def test_legacy_fixtures_remain_frozen(self):
        expected={'comfort-evaluation-v1.json':'c78b5b7d036676311708f360b80e2cffc44cdc21255e8293decf1a51356ec6b1',
          'comfort-evaluation-v2.json':'b4f548cc49d0413fda7244d01f8be3b5c12d32045f7f2b4daf58ddab13b8d770'}
        for name,digest in expected.items():
            files=list((prepare.ROOT/'data').rglob(name));self.assertEqual(len(files),1)
            self.assertEqual(hashlib.sha256(files[0].read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main()
