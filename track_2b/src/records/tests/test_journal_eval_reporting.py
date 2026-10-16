from django.test import SimpleTestCase
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from tools import journal_ai_eval
from tools.journal_ai_eval import failure_category, is_invalid_evidence, output_failure_diagnostics, reject_output


class JournalEvaluationReportingTests(SimpleTestCase):
    def test_one_case_hybrid_evaluator_scores_the_safe_proposal_and_discloses_discarded_fields(self):
        config={'model':'fictional-local-apertus','base':'http://inference:8080/v1','key':''}
        payload={'category':'symptom','occurrence':{'precision':'day','year':2026,'month':10,'day':16},
            'time':None,'severity':6,'evidence':{'category':{'quote':'headache'}},
            'unknown':[],'ambiguities':[],'abstained':False}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload)}}],
            'usage':{'completion_tokens':90}}
        with tempfile.TemporaryDirectory(prefix='comfort-journal-eval-') as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
            with patch.object(journal_ai_eval,'REPORTS',Path(directory)), \
                 patch('intelligence.trial.configuration',return_value=config), \
                 patch('intelligence.trial.available_models'),patch('intelligence.trial.request_json',return_value=response) as infer:
                path,summary=journal_ai_eval.evaluate(config,'development',0,['dev-03'])
            report=json.loads(path.read_text(encoding='utf-8'))
        infer.assert_called_once()
        self.assertEqual(summary['transport_successes'],1)
        self.assertEqual(summary['validator_accepted_outputs'],1)
        self.assertEqual(summary['passed_cases'],1)
        self.assertEqual(summary['field_accuracy'],1)
        self.assertEqual(summary['exact_case_accuracy'],1)
        self.assertEqual(summary['invalid_evidence_cases'],0)
        self.assertEqual(summary['proposals_with_discarded_optional_suggestions'],1)
        self.assertEqual(summary['accuracy_scope'],'validated_hybrid_proposals_after_source_normalization')
        self.assertEqual(report['selected_case_ids'],['dev-03'])
        self.assertEqual(report['results'][0]['discarded_model_fields'],['occurrence'])
        self.assertEqual(report['results'][0]['source_normalized_fields'],['severity'])
        self.assertNotIn('Fictional note:',json.dumps(report))

    def test_console_failures_include_safe_diagnostic_without_other_result_content(self):
        result={'case_id':'fictional-1','private_narrative':'fictional private writing',
            'model_output':'fictional raw response'}
        reject_output(result,'severity_unsupported',{'stage':'severity_unsupported',
            'field':'severity','reason':'required_quote_missing'})
        self.assertEqual(output_failure_diagnostics([result,{'status':'response_received'}]),[{
            'case_id':'fictional-1','failure_category':'severity_validation',
            'failure_code':'severity_unsupported','failure_diagnostic':{
                'stage':'severity_unsupported','field':'severity','reason':'required_quote_missing'}}])

    def test_json_or_date_failures_are_not_misreported_as_bad_evidence(self):
        result={'case_id':'fictional-1','response_received':True}
        reject_output(result,'invalid_model_json',{'stage':'invalid_model_json'})
        self.assertEqual(result['failure_category'],'json_parsing')
        self.assertIsNone(result['grading']['evidence_valid'])
        self.assertFalse(is_invalid_evidence(result))

        result={'case_id':'fictional-2','response_received':True}
        reject_output(result,'relative_date_unsupported',{'stage':'relative_date_unsupported'})
        self.assertEqual(result['failure_category'],'date_validation')
        self.assertFalse(is_invalid_evidence(result))

        result={'case_id':'fictional-severity','response_received':True}
        reject_output(result,'severity_unsupported',{'stage':'severity_unsupported',
            'field':'severity','reason':'required_quote_missing'})
        self.assertEqual(result['failure_category'],'severity_validation')
        self.assertEqual(result['failure_diagnostic']['reason'],'required_quote_missing')
        self.assertIsNone(result['grading']['evidence_valid'])
        self.assertFalse(is_invalid_evidence(result))

    def test_only_citation_rejection_or_accepted_fixture_mismatch_counts_as_evidence_failure(self):
        result={'case_id':'fictional-3','response_received':True}
        reject_output(result,'citation_invalid',{'stage':'citation_invalid',
            'field':'severity','reason':'quote_not_in_source'})
        self.assertEqual(result['failure_category'],'evidence_quotation')
        self.assertEqual(result['failure_diagnostic'],
            {'stage':'citation_invalid','field':'severity','reason':'quote_not_in_source'})
        self.assertTrue(is_invalid_evidence(result))

        accepted={'validator_accepted':True,'grading':{'evidence_valid':False}}
        self.assertTrue(is_invalid_evidence(accepted))
        self.assertEqual(failure_category('severity_negated'),'severity_validation')
        self.assertEqual(failure_category('time_unsupported'),'time_validation')
        self.assertEqual(failure_category('output_schema_invalid'),'structural_schema')
        self.assertEqual(failure_category('category_context_unsupported'),'category_validation')

