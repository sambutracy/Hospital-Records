"""Fictional, database-free checks for explicitly included visit context."""
from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import json

from django.test import SimpleTestCase

from records import visit_context as context
from records.models import JournalEvent


STAMP = datetime(2026, 10, 16, 9, 0, tzinfo=dt_timezone.utc)
DAY = {'precision': 'day', 'year': 2026, 'month': 10, 'day': 12}
MONTH = {'precision': 'month', 'year': 2026, 'month': 10, 'day': None}


def row(**values):
    return SimpleNamespace(pk='00000000-0000-0000-0000-000000000001', revision=3,
                           workspace_id='workspace', updated_at=STAMP, **values)


def query(rows):
    result = MagicMock()
    result.annotate.return_value = result
    result.order_by.return_value = result
    result.count.return_value = len(rows)
    result.__getitem__.side_effect = lambda selected: rows[selected]
    result.__iter__.side_effect = lambda: iter(rows)
    result.first.return_value = rows[0] if rows else None
    return result


class VisitContextTests(SimpleTestCase):
    def options(self, **flags):
        return context.validate_options({
            'packet_id': '00000000-0000-0000-0000-000000000002', 'visit_brief': True,
            'include_context': {key: flags.get(key, False) for key in context.FLAGS},
        })

    def capture(self, options):
        workspace = SimpleNamespace(pk='workspace')
        packet = SimpleNamespace(pk=options['packet_id'], workspace_id='workspace', purpose='Fictional follow-up')
        with patch.object(context, 'authorize_context'):
            return context.snapshot('fictional-user', workspace, options, packet)

    def test_options_are_explicit_bounded_and_exclude_unknown_fields(self):
        result = self.options()
        self.assertFalse(any(result['include_context'].values()))
        self.assertEqual(result['patient_goals'], '')
        base = {'packet_id': result['packet_id'], 'visit_brief': True}
        for extra in ({'visit_brief': False}, {'visit_focus': 'x' * 601},
                      {'patient_goals': 'Read\x00this'}, {'include_context': {'profile': True}},
                      {'include_context': {key: 1 for key in context.FLAGS}},
                      {'patient_id': 'other'}, {'packet_id': None}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                context.validate_options({**base, **extra})
        result = context.validate_options({**base, 'visit_focus': '  Fictional pain review  '})
        self.assertEqual(result['visit_focus'], 'Fictional pain review')

    def test_no_opt_in_performs_no_private_source_query(self):
        with patch.object(context.PatientPersonalDetails, 'objects') as profile, \
             patch.object(context.MedicationEntry, 'objects') as medication, \
             patch.object(context.JournalEvent, 'objects') as journal, \
             patch.object(context.PatientHealthConcern, 'objects') as concern, \
             patch.object(context.CareTeamAssignment, 'objects') as care:
            result = self.capture(self.options())
        for manager in (profile, medication, journal, concern, care):
            manager.assert_not_called()
            self.assertEqual(manager.mock_calls, [])
        self.assertEqual(result['entries'], [])
        self.assertEqual(result['coverage']['available_counts'], {})

    def test_profile_is_allowlisted_and_preserves_unknown_measurements(self):
        item = row(blood_group='O+', gender='Fictional reported gender',
                   identifier_number='SECRET-FICTIONAL-ID', full_name='PRIVATE-NAME',
                   email='PRIVATE-EMAIL', phone='PRIVATE-PHONE')
        with patch.object(context.PatientPersonalDetails, 'objects') as manager:
            manager.select_for_update.return_value.filter.return_value = query([item])
            result = self.capture(self.options(profile=True))
        serialized = json.dumps(result)
        for protected in ('SECRET-FICTIONAL-ID', 'PRIVATE-NAME', 'PRIVATE-EMAIL', 'PRIVATE-PHONE'):
            self.assertNotIn(protected, serialized)
        entry = result['entries'][0]
        self.assertIn('Blood group (patient reported, unverified): O+', entry['text'])
        self.assertEqual(entry['date']['precision'], 'unknown')
        self.assertFalse(result['coverage']['structured_measurements_available'])

    def test_empty_profile_adds_no_invented_basics(self):
        with patch.object(context.PatientPersonalDetails, 'objects') as manager:
            manager.select_for_update.return_value.filter.return_value = query([row(blood_group='unknown', gender='')])
            result = self.capture(self.options(profile=True))
        self.assertEqual(result['entries'], [])
        self.assertEqual(result['coverage']['available_counts']['profile'], 0)

    def test_medication_date_caps_and_prescribed_versus_taken_are_preserved(self):
        item = row(medicine_name='Fictional Medicine A', dose='5 mg', frequency='As written', route='',
                   instructions='Historical plan; whether used is unknown.', use_status='reported_prescribed',
                   date_precision='month', value_year=2026, value_month=10, value_day=None)
        values = query([item] * 22)
        with patch.object(context.MedicationEntry, 'objects') as manager:
            manager.select_for_update.return_value.filter.return_value = values
            result = self.capture(self.options(medications=True))
        self.assertEqual(len(result['entries']), 20)
        self.assertEqual(result['coverage']['omitted_counts']['medication'], 2)
        self.assertEqual(result['entries'][0]['date'], MONTH)
        self.assertIn('actual use is not established', result['entries'][0]['text'])
        ordering = values.order_by.call_args.args
        self.assertEqual([item.expression.name for item in ordering[:3]], ['value_year', 'value_month', 'value_day'])
        self.assertTrue(all(item.nulls_last for item in ordering[:3]))

    def test_journal_uses_exact_history_and_does_not_rewrite_narrative(self):
        item = row(category='symptom', description='MUTATED fictional narrative', occurrence=DAY,
                   severity=1, occurrence_time=None, timezone_name='Africa/Nairobi')
        historical = SimpleNamespace(snapshot={'category': 'symptom', 'description': 'Fictional no nausea; headache six out of ten.',
                                               'occurrence': MONTH, 'severity': 6, 'occurrence_time': None,
                                               'timezone_name': 'Africa/Nairobi'})
        with patch.object(context.JournalEvent, 'objects') as manager, \
             patch.object(context.JournalHistory, 'objects') as history:
            manager.select_for_update.return_value.filter.return_value = query([item])
            history.filter.return_value.first.return_value = historical
            result = self.capture(self.options(journal=True))
        entry = result['entries'][0]
        self.assertIn('Fictional no nausea; headache six out of ten.', entry['text'])
        self.assertNotIn('MUTATED', entry['text'])
        self.assertIn('Reported severity: 6/10', entry['text'])
        self.assertEqual(entry['date'], MONTH)
        self.assertEqual(result['coverage']['missing_immutable_history'], 0)
        self.assertEqual(historical.snapshot['description'], 'Fictional no nausea; headache six out of ten.')

    def test_missing_history_is_disclosed_and_narrative_is_never_clipped(self):
        item = row(category='note', description='Fictional uncertainty. ' * 85, occurrence=DAY,
                   severity=None, occurrence_time=None, timezone_name='Africa/Nairobi')
        with patch.object(context.JournalEvent, 'objects') as manager, \
             patch.object(context.JournalHistory, 'objects') as history:
            manager.select_for_update.return_value.filter.return_value = query([item])
            history.filter.return_value.first.return_value = None
            result = self.capture(self.options(journal=True))
        self.assertIn(item.description, result['entries'][0]['text'])
        self.assertEqual(result['coverage']['missing_immutable_history'], 1)

    def test_care_preserves_uncertainty_historical_role_and_exact_snapshot(self):
        concern = row(title='Changed title', description='Changed', certainty='unconfirmed', kind='issue', onset=DAY)
        assignment = row(practitioner_id='doctor-id', role='Changed', participation='current',
                         start_date=DAY, end_date=context.UNKNOWN_DATE, notes='Changed')
        doctor = SimpleNamespace(pk='doctor-id', workspace_id='workspace', revision=2,
                                 name='Changed name', specialty='', facility='')
        snapshots = {
            'concern': {'title': 'Fictional concern', 'description': 'Cause remains unknown.',
                        'certainty': 'unconfirmed', 'kind': 'investigation', 'onset': MONTH},
            'assignment': {'role': 'Historical fictional review', 'participation': 'historical',
                           'start_date': MONTH, 'end_date': context.UNKNOWN_DATE, 'notes': 'No appointment date recorded.'},
            'practitioner': {'name': 'Fictional practitioner', 'specialty': 'Fictional specialty',
                             'facility': 'Fictional facility'},
        }
        with patch.object(context.PatientHealthConcern, 'objects') as concerns, \
             patch.object(context.CareTeamAssignment, 'objects') as assignments, \
             patch.object(context.ReportedPractitioner, 'objects') as doctors, \
             patch.object(context.CareHistory, 'objects') as history:
            concerns.select_for_update.return_value.filter.return_value = query([concern])
            assignments.select_for_update.return_value.filter.return_value = query([assignment])
            doctors.select_for_update.return_value.filter.return_value = query([doctor])
            history.filter.side_effect = lambda **kwargs: query([SimpleNamespace(snapshot=snapshots[kwargs['target_kind']])])
            result = self.capture(self.options(care=True))
        self.assertEqual([entry['kind'] for entry in result['entries']], ['concern', 'care'])
        self.assertIn('Unconfirmed patient concern', result['entries'][0]['text'])
        self.assertIn('Patient-reported participation: historical', result['entries'][1]['text'])
        self.assertIn('professional identity unverified', result['entries'][1]['text'])
        self.assertNotIn('Changed', json.dumps(result))
        self.assertEqual(result['entries'][1]['date'], MONTH)
        concerns.select_for_update.return_value.filter.assert_called_once_with(workspace=SimpleNamespace(pk='workspace'), status='active')

    def test_reported_date_order_does_not_use_upload_or_update_time(self):
        result = context._dated(JournalEvent.objects.all(), 'occurrence')
        ordering = result.query.order_by
        self.assertEqual([item.expression.name for item in ordering[:3]],
                         ['_reported_year', '_reported_month', '_reported_day'])
        self.assertTrue(all(item.descending and item.nulls_last for item in ordering[:3]))
        self.assertEqual(ordering[-1], 'id')

    def test_each_live_private_scope_is_rechecked(self):
        with patch.object(context.services, 'authorize', return_value=('workspace', 'capability')) as authorize:
            context.authorize_context('user', 'workspace-id', self.options(medications=True)['include_context'], lock=True)
        self.assertEqual([call.args[2] if len(call.args) > 2 else 'read_workspace_records'
                          for call in authorize.call_args_list],
                         ['read_workspace_records', 'manage_profile', 'manage_medications'])
        self.assertTrue(all(call.kwargs['lock'] for call in authorize.call_args_list))
