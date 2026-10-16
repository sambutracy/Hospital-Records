"""Fictional regressions for line/page scope and explicit parser omissions."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from records import visit_brief as brief


class VisitBriefScopeTests(SimpleTestCase):
    def plan(self, pages):
        source = SimpleNamespace(source_label='s1', source_version=SimpleNamespace(original_filename='fictional-scope.pdf'),
            chunks=[{'id':f's1-c{index}', 'text':text, 'locator':{'kind':'source_text', 'page':index + 1}}
                    for index, text in enumerate(pages)])
        task = SimpleNamespace(parameters={'visit_context':{'entries':[]}})
        return brief.build_plan(task, {}, [source])

    def text(self, plan):
        return '\n'.join(item['text'] for item in plan['evidence'].values())

    def test_long_negation_section_is_omitted_whole_and_counted(self):
        # A 1000-character slicing implementation would detach "asthma" from
        # "No history of" in this section's final two wrapped lines.
        text = 'Past medical history:\n' + 'Fictional historical context. ' * 34 + '\nNo history of:\nasthma.'
        self.assertGreater(len(text), brief.MAX_PASSAGE)
        plan = self.plan([text + '\nPlan:\nA fictional review was requested; date unknown.'])
        self.assertNotIn('asthma', self.text(plan))
        self.assertIn('fictional review', self.text(plan))
        self.assertEqual(plan['coverage']['omitted_passages'], 1)

    def test_long_family_section_never_exposes_its_unattributed_tail(self):
        text = 'Family history:\nThe following conditions refer only to a fictional parent.\n'
        text += 'Fictional family background remains uncertain. ' * 25
        text += '\nDiabetes and asthma.'
        plan = self.plan([text])
        self.assertEqual(plan['evidence'], {})
        self.assertEqual(plan['coverage']['omitted_passages'], 1)

    def test_page_negation_continuation_is_omitted_until_a_new_known_heading(self):
        plan = self.plan([
            'Allergies:\nNo known drug allergies.\nPast medical history:\nNo history of:',
            'asthma or diabetes.\nPlan:\nFictional review requested; appointment date unknown.',
        ])
        self.assertNotIn('asthma', self.text(plan))
        self.assertNotIn('No history of:', self.text(plan))
        self.assertIn('No known drug allergies.', self.text(plan))
        self.assertIn('appointment date unknown', self.text(plan))
        self.assertEqual(plan['coverage']['omitted_passages'], 2)

    def test_page_family_attribution_and_condition_are_never_reconstructed_as_patient_claims(self):
        for prefix, continuation in (
            ('Family history:\nThe fictional parent had:', 'asthma. The patient has no recorded diagnosis.'),
            ('Plan:\nOnly if the fictional test is positive:', 'the proposed procedure may be considered.'),
        ):
            with self.subTest(prefix=prefix):
                plan = self.plan([prefix, continuation + '\nSymptoms:\nFictional headache; no nausea.'])
                self.assertNotIn(continuation, self.text(plan))
                self.assertNotIn(prefix, self.text(plan))
                self.assertIn('Fictional headache; no nausea.', self.text(plan))
                self.assertEqual(plan['coverage']['omitted_passages'], 2)

    def test_administrative_footer_cannot_reset_negation_scope(self):
        text = 'Past medical history:\nNo history of:\nNo real patient data.\nasthma or diabetes.'
        accepted, omitted = brief.passage_analysis(text)
        self.assertEqual(accepted, [(text, 'history')])
        self.assertEqual(omitted, 0)
        self.assertNotEqual(accepted[0][0], 'asthma or diabetes.')

    def test_administrative_lines_at_next_page_start_do_not_disguise_continuation(self):
        plan = self.plan(['Family history:\nThe fictional parent had:',
            'No real patient data.\nDr. Fictional Example\nasthma.\nAllergies:\nNo known drug allergies.'])
        self.assertNotIn('asthma', self.text(plan))
        self.assertIn('No known drug allergies.', self.text(plan))
        self.assertEqual(plan['coverage']['omitted_passages'], 2)

    def test_single_unheaded_page_and_fresh_explicit_second_page_remain_supported(self):
        narrative = 'The fictional patient denied cough. No later assessment was supplied.'
        plan = self.plan([narrative, 'Plan:\nA fictional review was requested.'])
        self.assertIn(narrative, self.text(plan))
        self.assertIn('A fictional review was requested.', self.text(plan))
        self.assertEqual(plan['coverage']['omitted_passages'], 0)

    def test_long_unheaded_page_is_not_split_into_independent_claims(self):
        narrative = ('The fictional history is uncertain. ' * 35) + '\nA diagnosis was not established.'
        accepted, omitted = brief.passage_analysis(narrative)
        self.assertEqual(accepted, [])
        self.assertEqual(omitted, 1)
