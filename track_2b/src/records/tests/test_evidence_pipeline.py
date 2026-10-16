from dataclasses import FrozenInstanceError
import json
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from records import evidence_pipeline as pipeline


class EvidencePipelineTests(SimpleTestCase):
    def setUp(self):
        self.registry=patch.dict(pipeline._specs,{},clear=True)
        self.registry.start(); self.addCleanup(self.registry.stop)
        pipeline.register(pipeline.TaskSpec('test','test-v1','Untrusted evidence only.',lambda:{'type':'object'},100,2,200))

    def test_selection_is_immutable_explicit_and_bounded(self):
        check=Mock()
        selected=pipeline.bounded('test',[pipeline.Evidence('e1','Fictional note')],check)
        check.assert_called_once()
        with self.assertRaises(FrozenInstanceError): selected[0].text='Changed'
        for rows in ([],[pipeline.Evidence('e1','a')]*3,[pipeline.Evidence('e1','x'*201)],
                     [pipeline.Evidence('e1','a'),pipeline.Evidence('e1','b')]):
            with self.assertRaises(ValueError): pipeline.bounded('test',rows,check)

    def test_citations_require_exact_quotes_from_selected_ids(self):
        evidence=(pipeline.Evidence('e1','No nausea was reported.'),)
        value=pipeline.citations([{'evidence_id':'e1','quote':'No nausea'}],evidence)[0]
        self.assertEqual((value['start'],value['end']),(0,9))
        for citation in ({'evidence_id':'e2','quote':'No nausea'},{'evidence_id':'e1','quote':'Nausea was present'},
                         {'evidence_id':'e1','quote':'No nausea','url':'https://example.com'}):
            with self.assertRaises(ValueError): pipeline.citations([citation],evidence)

    def test_one_shared_authenticated_request_and_safe_trace(self):
        config={'base':'http://inference:8080/v1','model':'local-apertus','key':'','request_timeout':300}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'valid':True})}}],
            'usage':{'prompt_tokens':10,'completion_tokens':4,'provider_debug':'omit'}}
        checkpoint=Mock(); record=Mock()
        with patch('intelligence.trial.configuration',return_value=config),patch('intelligence.trial.available_models'),patch('intelligence.trial.request_json',return_value=response) as infer:
            result,trace=pipeline.invoke('test','Fictional selected evidence',checkpoint,lambda value:value,record)
        self.assertTrue(result['valid']); self.assertEqual(infer.call_count,1)
        self.assertEqual(infer.call_args.args[0],config)
        self.assertNotIn('key',record.call_args.args[0]['configuration'])
        self.assertNotIn('provider_debug',trace['usage'])
        self.assertGreaterEqual(checkpoint.call_count,3)

    def test_care_excerpt_scope_preserves_negation_subjects_and_uncertainty(self):
        evidence=(pipeline.Evidence('e1','My aunt has migraines. I have no headache today. Maybe I felt tired.'),)
        for quote,expected in [('migraines','My aunt has migraines.'),('headache today','I have no headache today.'),('I felt tired','Maybe I felt tired.')]:
            result=pipeline.citations([{'evidence_id':'e1','quote':quote}],evidence,preserve_scope=True)[0]
            self.assertEqual(result['quote'],expected)

    def test_authority_revocation_before_inference_prevents_model_call(self):
        checkpoint=Mock(side_effect=[None,PermissionError('revoked')])
        with patch('intelligence.trial.configuration',return_value={'model':'test','base':'local','key':''}),patch('intelligence.trial.available_models'),patch('intelligence.trial.request_json') as infer:
            with self.assertRaises(PermissionError): pipeline.invoke('test','Fictional evidence',checkpoint,lambda value:value,Mock())
        infer.assert_not_called()

    def test_invalid_or_truncated_output_is_not_retried(self):
        for response in ({'choices':[{'finish_reason':'length'}]}, {'choices':[{'finish_reason':'stop','message':{'content':'not JSON'}}]}):
            with patch('intelligence.trial.configuration',return_value={'model':'test','base':'local'}),patch('intelligence.trial.available_models'),patch('intelligence.trial.request_json',return_value=response) as infer:
                with self.assertRaises(ValueError): pipeline.invoke('test','Fictional evidence',Mock(),lambda value:value,Mock())
                self.assertEqual(infer.call_count,1)
