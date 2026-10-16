"""Fictional, field-level reliability regressions; never calls a model."""
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from django.test import SimpleTestCase
from records import journal_ai


MANIFEST=json.loads((Path(__file__).resolve().parents[3]/'data/journal-ai-v1/manifest.json').read_text(encoding='utf-8'))
CASES={case['id']:case for case in MANIFEST['cases']}


class JournalNormalizationTests(SimpleTestCase):
    def run_proposal(self,text,payload=None,zone='Africa/Nairobi'):
        request=SimpleNamespace(input_snapshot=text,reference_at=datetime(2026,10,16,1,tzinfo=timezone.utc),
            reference_timezone=zone)
        if payload is None: payload=self.payload()
        return journal_ai.validate(payload,request,{})

    def payload(self):
        return {'category':'symptom','occurrence':{'precision':'unknown','year':None,'month':None,'day':None},
            'time':None,'severity':None,'evidence':{'category':{'quote':'headache'}},
            'unknown':[],'ambiguities':[],'abstained':False}

    def test_frozen_dev03_missing_occurrence_evidence_returns_safe_partial_proposal(self):
        payload=self.payload()
        payload['occurrence']={'precision':'day','year':2026,'month':10,'day':16}
        payload['severity']=6
        result=self.run_proposal(CASES['dev-03']['text'],payload)
        self.assertEqual((result['fields']['category'],result['fields']['precision'],result['fields']['time'],
            result['fields']['severity']),('symptom','unknown','','6'))
        self.assertNotIn('occurrence',result['evidence'])
        self.assertEqual(result['evidence']['severity']['quote'],'six out of ten')
        self.assertEqual(result['evidence']['severity']['origin'],'source_extraction')
        self.assertIn({'field':'occurrence','reason':'no_explicit_source'},result['field_abstentions'])
        self.assertTrue(any('confirm before applying' in item for item in result['ambiguities']))
        self.assertEqual(result['fields']['description'],CASES['dev-03']['text'])

    def test_invented_optional_quote_is_omitted_and_never_laundered(self):
        payload=self.payload(); payload['severity']=6
        payload['evidence']['severity']={'quote':'six out of 10'}
        result=self.run_proposal(CASES['dev-03']['text'],payload)
        self.assertEqual(result['fields']['severity'],'')
        self.assertNotIn('severity',result['evidence'])
        self.assertIn({'field':'severity','reason':'quote_not_verified'},result['field_abstentions'])

    def test_incomplete_scale_quote_abstains_without_replacing_its_evidence(self):
        payload=self.payload(); payload['severity']=6
        payload['evidence']['severity']={'quote':'six'}
        result=self.run_proposal(CASES['dev-03']['text'],payload)
        self.assertEqual(result['fields']['severity'],'')
        self.assertNotIn('severity',result['evidence'])
        self.assertIn({'field':'severity','reason':'quote_does_not_support_field'},result['field_abstentions'])

    def test_value_disagreement_is_not_silently_corrected_to_the_source_value(self):
        payload=self.payload(); payload['severity']=8
        payload['evidence']['severity']={'quote':'six out of ten'}
        result=self.run_proposal(CASES['dev-03']['text'],payload)
        self.assertEqual(result['fields']['severity'],'')
        self.assertIn({'field':'severity','reason':'model_source_disagreement'},result['field_abstentions'])

    def test_number_word_scales_are_copied_with_exact_offsets_and_zero_preserved(self):
        for phrase,value in (('zero out of ten','0'),('SEVEN out of TEN','7'),('ten out of ten','10')):
            with self.subTest(phrase=phrase):
                text='Fictional note: headache '+phrase+'.'
                result=self.run_proposal(text)
                self.assertEqual(result['fields']['severity'],value)
                evidence=result['evidence']['severity']
                self.assertEqual(text[evidence['start']:evidence['end']],evidence['quote'])
                self.assertEqual(evidence['quote'],phrase)

    def test_qualitative_and_decimal_intensity_are_not_turned_into_an_integer(self):
        for text in ('Fictional note: headache was very severe.', 'Fictional note: headache was 6.5/10.'):
            with self.subTest(text=text):
                self.assertEqual(self.run_proposal(text)['fields']['severity'],'')

    def test_two_source_ratings_abstain_instead_of_choosing_one(self):
        payload=self.payload(); payload['severity']=6
        payload['evidence']['severity']={'quote':'6/10'}
        result=self.run_proposal('Fictional note: headache was 6/10, or perhaps 8/10; I am unsure.',payload)
        self.assertEqual(result['fields']['severity'],'')
        self.assertIn({'field':'severity','reason':'conflicting_source'},result['field_abstentions'])

    def test_invalid_calendar_date_does_not_discard_a_supported_rating(self):
        payload=self.payload(); payload['occurrence']={'precision':'day','year':2026,'month':2,'day':31}
        payload['evidence']['occurrence']={'quote':'2026-02-31'}
        result=self.run_proposal('Fictional note: headache on 2026-02-31 was 6/10.',payload)
        self.assertEqual((result['fields']['precision'],result['fields']['severity']),('unknown','6'))
        self.assertIn({'field':'occurrence','reason':'invalid_source_date'},result['field_abstentions'])

    def test_model_date_components_are_checked_instead_of_silently_resolved_from_quote(self):
        payload=self.payload(); payload['occurrence']={'precision':'day','year':2027,'month':3,'day':2}
        payload['evidence']['occurrence']={'quote':'2026-03-02'}
        result=self.run_proposal('Fictional note: headache on 2026-03-02 was 6/10.',payload)
        self.assertEqual((result['fields']['precision'],result['fields']['severity']),('unknown','6'))
        self.assertIn({'field':'occurrence','reason':'model_source_disagreement'},result['field_abstentions'])

    def test_exact_date_time_and_severity_have_independent_verified_source_spans(self):
        payload=self.payload(); payload['evidence']['category']={'quote':'Headache'}
        result=self.run_proposal(CASES['val-02']['text'],payload)
        self.assertEqual({key:result['fields'][key] for key in ('precision','year','month','day','time','severity')},
            {'precision':'day','year':'2026','month':'3','day':'2','time':'14:30','severity':'7'})
        for item in result['evidence'].values():
            self.assertEqual(CASES['val-02']['text'][item['start']:item['end']],item['quote'])

    def test_partial_date_stays_partial_and_relative_date_uses_trusted_local_day(self):
        result=self.run_proposal(CASES['dev-06']['text'])
        self.assertEqual((result['fields']['precision'],result['fields']['year'],result['fields']['month'],result['fields']['day']),
            ('month','2025','10',''))
        result=self.run_proposal('Fictional note: headache yesterday.',zone='America/Chicago')
        self.assertEqual((result['fields']['year'],result['fields']['month'],result['fields']['day']),('2026','10','14'))

    def test_uncertain_onset_and_conflicting_dates_remain_unknown(self):
        payload=self.payload(); payload['evidence']['category']={'quote':'stomach discomfort'}
        result=self.run_proposal(CASES['dev-11']['text'],payload)
        self.assertEqual(result['fields']['precision'],'unknown')
        result=self.run_proposal('Fictional note: headache on 2026-03-02 or 2026-03-04.')
        self.assertEqual(result['fields']['precision'],'unknown')
        self.assertIn({'field':'occurrence','reason':'conflicting_source'},result['field_abstentions'])

    def test_negated_scale_is_not_suggested(self):
        result=self.run_proposal('Fictional note: I did not rate my headache as six out of ten.')
        self.assertEqual(result['fields']['severity'],'')
        self.assertIn({'field':'severity','reason':'negated_source'},result['field_abstentions'])

    def test_unsupported_symptom_context_and_missing_core_evidence_still_hard_fail(self):
        for text in ('Fictional note: I have no headache today.',
                'Fictional note: I never had a headache today.',
                'Fictional note: I deny any headache today.',
                'Fictional note: If I get a headache tomorrow I will record it.',
                'Fictional note: My aunt had a headache yesterday.'):
            with self.subTest(text=text),self.assertRaises(journal_ai.JournalOutputFailure) as failure:
                self.run_proposal(text)
            self.assertEqual(failure.exception.code,'category_context_unsupported')
        payload=self.payload(); payload['evidence']['category']={'quote':'fever'}
        with self.assertRaises(journal_ai.JournalOutputFailure) as failure:
            self.run_proposal('Fictional note: I do not have any fever today.',payload)
        self.assertEqual(failure.exception.code,'category_context_unsupported')
        payload=self.payload(); payload['evidence']={}
        with self.assertRaises(journal_ai.JournalOutputFailure): self.run_proposal(CASES['dev-03']['text'],payload)

    def test_free_text_model_claims_are_not_exposed_as_review_explanations(self):
        payload=self.payload(); payload['ambiguities']=['A fictional unsupported diagnosis is certain.']
        result=self.run_proposal(CASES['dev-03']['text'],payload)
        self.assertNotIn('unsupported diagnosis',json.dumps(result))
        payload['diagnosis']='fictional unsupported diagnosis'
        with self.assertRaises(journal_ai.JournalOutputFailure): self.run_proposal(CASES['dev-03']['text'],payload)

    def test_clock_without_date_and_dst_gap_or_fold_require_manual_confirmation(self):
        result=self.run_proposal('Fictional note: headache at 14:30.')
        self.assertEqual(result['fields']['time'],'')
        self.assertIn({'field':'time','reason':'time_needs_date'},result['field_abstentions'])
        for day in ('2026-03-29','2026-10-25'):
            with self.subTest(day=day):
                result=self.run_proposal('Fictional note: headache on '+day+' at 02:30.',zone='Europe/Zurich')
                self.assertEqual(result['fields']['time'],'')
                self.assertIn({'field':'time','reason':'time_needs_confirmation'},result['field_abstentions'])

    def test_model_uncertainty_can_only_remove_a_suggestion(self):
        payload=self.payload(); payload['unknown']=['Severity is uncertain.']
        result=self.run_proposal(CASES['dev-03']['text'],payload)
        self.assertEqual(result['fields']['severity'],'')
        self.assertIn({'field':'severity','reason':'model_uncertain'},result['field_abstentions'])
