"""Offline contract checks. Mock replies are never presented as Apertus measurements."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from intelligence import trial

CASES = json.loads(trial.FIXTURES.read_text(encoding='utf-8'))['cases']
CONFIG = {'model': 'swiss-ai/Apertus-v1.5-8B', 'base': 'https://example.invalid/v1', 'key': 'secret-test-key'}


def reference_response(case):
    answer = {**case['expected'], 'evidence': case['reference_evidence']}
    return {'choices': [{'message': {'content': json.dumps(answer)}, 'finish_reason': 'stop'}],
            'model': CONFIG['model'], 'usage': {'prompt_tokens': 100, 'completion_tokens': 80}}


class TrialContractTests(unittest.TestCase):
    def test_local_quantized_model_identity_is_explicit(self):
        config=trial.configuration(Path('/no-local-env'),{'LLM_NAME':trial.LOCAL_TEXT_MODEL,
            'LLM_BASE_URL':'http://host.docker.internal:9001/v1','LLM_API_KEY':''})
        self.assertEqual(config['model'],trial.LOCAL_TEXT_MODEL)
        self.assertTrue(config['identity']['community_derivative'])
        self.assertEqual(config['identity']['modalities'],['text'])
        self.assertEqual(config['identity']['precision'],'Q4_K_M')
        with patch.object(trial,'request_json',return_value={'data':[{'id':trial.LOCAL_TEXT_MODEL}]}):
            self.assertEqual(trial.available_models(config),[trial.LOCAL_TEXT_MODEL])

    def test_missing_key_blocks_hosted_endpoint(self):
        with TemporaryDirectory() as folder:
            env = Path(folder) / '.env'
            env.write_text('LLM_NAME=swiss-ai/Apertus-v1.5-8B\nLLM_BASE_URL=https://example.invalid/v1\n')
            with self.assertRaisesRegex(trial.TrialError, 'LLM_API_KEY is missing'):
                trial.configuration(env, {})

    def test_environment_precedence_and_local_no_key(self):
        values = {'LLM_NAME': 'swiss-ai/Apertus-v1.5-8B', 'LLM_BASE_URL': 'http://host.docker.internal:9001/v1'}
        with TemporaryDirectory() as folder:
            env = Path(folder) / '.env'
            env.write_text('LLM_BASE_URL=https://old.example.invalid/v1\n')
            config = trial.configuration(env, values)
            self.assertEqual(config['base'], values['LLM_BASE_URL'])
            self.assertEqual(config['key'], '')

    def test_unsafe_or_wrong_config_fails_without_revealing_input(self):
        variations = [
            {'LLM_BASE_URL': 'http://remote.example.invalid/v1'},
            {'LLM_BASE_URL': 'https://user:secret-test-key@example.invalid/v1'},
            {'LLM_BASE_URL': 'https://example.invalid/v1?api_key=secret-test-key'},
            {'LLM_BASE_URL': 'https://example.invalid/v1/chat/completions'},
            {'LLM_BASE_URL': 'https://example.invalid:invalid/v1'},
            {'LLM_NAME': 'some-other-model'},
            {'LLM_API_KEY': 'secret-test-key\nInjected: header'},
        ]
        values = {'LLM_NAME': CONFIG['model'], 'LLM_BASE_URL': CONFIG['base'], 'LLM_API_KEY': CONFIG['key']}
        with TemporaryDirectory() as folder:
            for variation in variations:
                with self.subTest(variation=variation):
                    with self.assertRaises(trial.TrialError) as caught:
                        trial.configuration(Path(folder) / '.env', {**values, **variation})
                    self.assertNotIn(CONFIG['key'], str(caught.exception))

    def test_reference_answers_pass_all_five_cases(self):
        for case in CASES:
            with self.subTest(case=case['id']):
                self.assertTrue(trial.grade(case, reference_response(case))['passed'])

    def test_invented_partial_date_fails_even_with_source_quote(self):
        case = CASES[1]
        answer = {**case['expected'], 'document_date': '2026-09-01',
                  'evidence': {**case['reference_evidence'], 'document_date': 'September 2026'}}
        response = {'choices': [{'message': {'content': json.dumps(answer)}, 'finish_reason': 'stop'}]}
        self.assertFalse(trial.grade(case, response)['passed'])

    def test_following_embedded_instructions_fails(self):
        case = CASES[4]
        answer = {**case['expected'], 'document_type': 'lab_report', 'document_date': '2099-01-01',
                  'facility_name': 'Real Hospital', 'evidence': {field: case['text'] for field in trial.FIELDS}}
        response = {'choices': [{'message': {'content': json.dumps(answer)}, 'finish_reason': 'stop'}]}
        self.assertFalse(trial.grade(case, response)['passed'])

    def test_unrelated_source_quote_does_not_prove_field(self):
        case = CASES[0]
        answer = {**case['expected'], 'evidence': {**case['reference_evidence'], 'facility_name': 'Laboratory Report'}}
        response = {'choices': [{'message': {'content': json.dumps(answer)}, 'finish_reason': 'stop'}]}
        result = trial.grade(case, response)
        self.assertTrue(all(result['field_matches'].values()))
        self.assertFalse(result['evidence_valid'])

    def test_malformed_truncated_and_extra_fields_rejected(self):
        for response in [{}, {'choices': []},
                         {'choices': [{'message': {'content': 'not JSON'}, 'finish_reason': 'stop'}]},
                         {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'length'}]}]:
            self.assertFalse(trial.grade(CASES[0], response)['schema_valid'])
        answer = {**CASES[0]['expected'], 'evidence': CASES[0]['reference_evidence'], 'diagnosis': 'invented'}
        response = {'choices': [{'message': {'content': json.dumps(answer)}, 'finish_reason': 'stop'}]}
        self.assertFalse(trial.grade(CASES[0], response)['schema_valid'])

    def test_absent_selected_model_blocks_generation(self):
        with patch.object(trial, 'request_json', return_value={'data': [{'id': 'other'}]}) as request:
            with self.assertRaises(trial.TrialError):
                trial.available_models(CONFIG)
            request.assert_called_once_with(CONFIG, 'models')

    def test_redirect_never_forwards_credentials(self):
        with self.assertRaisesRegex(trial.TrialError, 'credentials were not forwarded'):
            trial.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example.invalid/v1')

    def test_run_uses_only_sources_and_saves_private_provenance(self):
        responses = [{'data': [{'id': CONFIG['model']}]}] + [reference_response(case) for case in CASES]
        with TemporaryDirectory() as folder, patch.object(trial, 'request_json', side_effect=responses) as request:
            path, summary = trial.run(CONFIG, Path(folder))
            report = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(summary['passed_cases'], 5)
            self.assertEqual(report['mode'], 'live_synthetic_text_trial')
            self.assertEqual(report['fixture_sha256'], trial.hashlib.sha256(trial.FIXTURES.read_bytes()).hexdigest())
            self.assertNotIn(CONFIG['key'], path.read_text())
            self.assertEqual(request.call_count, 6)
            for call, case in zip(request.call_args_list[1:], CASES):
                payload = call.args[2]
                self.assertEqual(payload['messages'][1]['content'], case['text'])
                self.assertNotIn('expected', payload)
                self.assertNotIn('reference_evidence', payload)

    def test_transport_failure_stops_and_preserves_partial_results(self):
        responses = [{'data': [{'id': CONFIG['model']}]}, reference_response(CASES[0]), trial.TrialError('HTTP 429')]
        with TemporaryDirectory() as folder, patch.object(trial, 'request_json', side_effect=responses) as request:
            path, summary = trial.run(CONFIG, Path(folder))
            report = json.loads(path.read_text())
            self.assertEqual(request.call_count, 3)
            self.assertFalse(summary['complete'])
            self.assertEqual(summary['response_cases'], 1)
            self.assertEqual(report['results'][1]['error'], 'HTTP 429')

    def test_response_echo_of_key_is_redacted_without_breaking_json(self):
        config = {**CONFIG, 'key': 'test-"quoted"-key'}
        response = reference_response(CASES[0])
        response['provider_debug'] = config['key']
        with TemporaryDirectory() as folder, patch.object(trial, 'request_json', side_effect=[
            {'data': [{'id': CONFIG['model']}]}, response, trial.TrialError('connection failed')
        ]):
            path, _ = trial.run(config, Path(folder))
            report = json.loads(path.read_text())
            self.assertEqual(report['results'][0]['response']['provider_debug'], '[REDACTED]')


if __name__ == '__main__':
    unittest.main()
