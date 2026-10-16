"""Fictional source-grounding regressions, distinct from live Apertus accuracy."""
from copy import deepcopy
import json
import re

from django.test import SimpleTestCase

from intelligence import visit_brief_benchmark as benchmark
from records import visit_brief as brief, evidence_pipeline as pipeline


class VisitBriefContractTests(SimpleTestCase):
    def setUp(self):
        self.suite, self.fixture_hash = benchmark.load_fixture()

    def case(self, index=0):
        case = self.suite['cases'][index]
        task, context, sources = benchmark.context_for(case)
        plan = brief.build_plan(task, context, sources)
        return case, task, context, sources, plan

    def test_multisection_multpage_note_retains_each_authored_fact(self):
        for index in range(len(self.suite['cases'])):
            with self.subTest(case=index):
                case, task, _, sources, plan = self.case(index)
                payload = benchmark.baseline(plan)
                result = brief.validate(task, payload, plan, sources)
                grading = benchmark.grade(case, payload, plan)
                self.assertTrue(grading['exact_case_match'])
                self.assertTrue(result['review_required'])
                self.assertFalse(result['modifies_packet'])
                self.assertEqual(result['representation'], 'visit_brief')
                self.assertEqual(grading['duplicate_passages'], 0)

    def test_identical_medication_passage_has_one_item_and_both_originals(self):
        _, task, _, sources, plan = self.case(1)
        result = brief.validate(task, benchmark.baseline(plan), plan, sources)
        medication_items = next(section for section in result['sections'] if section['id'] == 'medications')['items']
        shared = [item for item in medication_items if len({c.get('source_version_id') for c in item['citations']}) > 1]
        self.assertTrue(shared)
        self.assertGreater(result['coverage_summary']['duplicate_passages_merged'], 0)
        self.assertEqual(len(medication_items), len({item['text'] for item in medication_items}))

    def test_schema_is_bounded_to_actual_source_candidates(self):
        _, task, _, _, plan = self.case()
        content = brief.wire_context(task, plan)
        schema = brief.output_schema(content)
        ids = schema['properties']['sections']['items']['properties']['evidence']['items']['enum']
        self.assertEqual(ids, list(plan['evidence']))
        self.assertLessEqual(len(content), pipeline.specification('visit_brief').max_characters)
        self.assertEqual(pipeline.specification('visit_brief').source_schema, brief.output_schema)

    def test_generated_prose_invented_identifiers_and_duplicate_selections_rejected(self):
        _, task, _, sources, plan = self.case()
        payload = benchmark.baseline(plan)
        for mutate in (
            lambda p: p.update(text='Invented clinical conclusion'),
            lambda p: p['sections'][0]['evidence'].append(99999),
            lambda p: p['sections'].append(deepcopy(p['sections'][0])),
            lambda p: p['sections'][0]['evidence'].append(p['sections'][0]['evidence'][0]),
            lambda p: p['sections'][0].update(text='Invented treatment advice'),
        ):
            invalid = deepcopy(payload); mutate(invalid)
            with self.assertRaises(pipeline.OutputFailure): brief.validate(task, invalid, plan, sources)

    def test_explicit_family_or_allergy_heading_cannot_be_reassigned_by_model(self):
        _, task, _, sources, plan = self.case()
        number = next(n for n, item in plan['evidence'].items() if item['area'] == 'medications')
        with self.assertRaises(pipeline.OutputFailure) as failure:
            brief.validate(task, {'sections': [{'area': 'history', 'evidence': [number]}]}, plan, sources)
        self.assertEqual(failure.exception.code, 'brief_attribution_invalid')

    def test_exact_source_verification_still_rejects_forged_passage(self):
        _, task, _, sources, plan = self.case()
        payload = benchmark.baseline(plan)
        number = payload['sections'][0]['evidence'][0]
        forged = deepcopy(plan)
        forged['evidence'][number]['refs'][0]['quote'] = 'This statement does not exist in the original.'
        with self.assertRaises(pipeline.OutputFailure) as failure:
            brief.validate(task, payload, forged, sources)
        self.assertEqual(failure.exception.code, 'brief_evidence_invalid')

    def test_qualifications_and_inline_headings_are_preserved_whole(self):
        text = 'Family history: Mother has diabetes. Patient denies diabetes.\nAllergies: No known drug allergies.\nPlan: Review requested; date unknown.'
        values = list(brief.passages(text))
        self.assertEqual(values[0], ('Family history: Mother has diabetes. Patient denies diabetes.', 'history'))
        self.assertEqual(values[1], ('Allergies: No known drug allergies.', 'medications'))
        self.assertEqual(values[2][1], 'followup')

    def test_input_truncation_omits_trailing_incomplete_section(self):
        text = 'Allergies\nNo known drug allergies.\nPlan\nMedicine Q was prescribed but'
        values = list(brief.passages(text, truncated=True))
        self.assertEqual(len(values), 1)
        self.assertIn('No known drug allergies.', values[0][0])
        self.assertNotIn('Medicine Q', json.dumps(values))

    def test_historical_plan_date_is_not_presented_as_completion_or_current_instruction(self):
        _, task, _, sources, plan = self.case()
        result = brief.validate(task, benchmark.baseline(plan), plan, sources)
        followup = next(section for section in result['sections'] if section['id'] == 'followup')
        self.assertTrue(all('completion and current status need confirmation' in item['caution'] for item in followup['items']))
        self.assertTrue(all('Document date 2025-12-20' in citation['date_label'] for item in followup['items'] for citation in item['citations']))

    def test_unknown_dates_stay_unknown_not_replaced_with_preparation_date(self):
        _, task, context, sources, _ = self.case(3)
        for source in sources:
            for chunk in source.chunks:
                chunk['text'] = re.sub(r'^Document date:.*\n', '', chunk['text'])
        plan = brief.build_plan(task, context, sources)
        result = brief.validate(task, benchmark.baseline(plan), plan, sources)
        document_citations = [c for section in result['sections'] for item in section['items']
                              if item['source_kind'] == 'document' for c in item['citations']]
        self.assertTrue(document_citations)
        self.assertTrue(all(c['date_label'] == 'Document date unknown' for c in document_citations))

    def test_patient_purpose_and_questions_are_copied_even_if_model_abstains(self):
        _, task, _, sources, plan = self.case()
        visit = task.parameters['visit_context']['visit']
        visit.update(focus='Fictional symptoms have changed.', goals='Understand the records.', questions='Was this planned test completed?')
        result = brief.validate(task, {'sections': []}, plan, sources)
        self.assertTrue(result['abstained'])
        texts = [item['text'] for section in result['sections'] for item in section['items']]
        self.assertIn(visit['focus'], texts)
        self.assertIn(visit['goals'], texts)
        self.assertIn(visit['questions'], texts)
        self.assertFalse(any(gap['id'] == 'patient_priorities' for gap in result['critical_gaps']))

    def test_unknown_allergy_status_is_a_gap_not_a_negative_allergy_finding(self):
        _, task, context, sources, _ = self.case(3)
        sources[0].chunks[0]['text'] = 'Allergies\nAllergy status unknown; not documented.'
        plan = brief.build_plan(task, context, sources)
        result = brief.validate(task, benchmark.baseline(plan), plan, sources)
        self.assertTrue(any(gap['id'] == 'allergy_status' for gap in result['critical_gaps']))
        self.assertTrue(any(gap['id'] == 'medication_context' for gap in result['critical_gaps']))

    def test_different_reported_medication_accounts_are_flagged_without_reconciliation(self):
        _, task, _, sources, plan = self.case()
        task.parameters['visit_context']['entries'] = [
            {'medication': {'name': 'Fictional Medicine A', 'use_status': 'reported_prescribed', 'dose': '5 mg', 'frequency': 'daily'}},
            {'medication': {'name': 'Fictional Medicine A', 'use_status': 'not_taken', 'dose': '5 mg', 'frequency': 'daily'}},
        ]
        result = brief.validate(task, benchmark.baseline(plan), plan, sources)
        self.assertTrue(any(gap['id'] == 'medication_accounts' for gap in result['critical_gaps']))
        self.assertFalse(result['modifies_packet'])

    def test_more_recent_report_dates_prioritize_candidates_without_changing_quotes(self):
        _, task, context, sources, _ = self.case(1)
        sources[0].chunks[0]['text'] = 'Document date: 2025-01-02\nHistory\nFictional older history.'
        sources[1].chunks[0]['text'] = 'Document date: 2026-10-01\nHistory\nFictional recent history.'
        plan = brief.build_plan(task, context, sources)
        history = [item for item in plan['evidence'].values() if item['area'] == 'history']
        self.assertIn('recent', history[0]['text'])
        self.assertIn('older', history[1]['text'])

    def test_evaluator_keeps_transport_separate_and_failed_outputs_in_denominators(self):
        rows = [{'case_id': 'fictional', 'status': 'invalid_output', 'response_received': True,
                 'expected_section_count': 2, 'expected_fact_count': 3, 'latency_seconds': 1},
                {'case_id': 'unrun', 'status': 'unattempted', 'response_received': False}]
        summary = benchmark._summary(rows, 2, True)
        self.assertEqual(summary['transport_successes'], 1)
        self.assertEqual(summary['valid_outputs'], 0)
        self.assertEqual(summary['field_accuracy_attempted'], 0)
        self.assertIsNone(summary['field_accuracy_valid_outputs'])
        self.assertEqual(summary['unattempted_cases'], ['unrun'])
