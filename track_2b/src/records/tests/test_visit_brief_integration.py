"""Fictional application/worker integration under disposable PostgreSQL only."""
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid
from unittest import skipUnless
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
import pypdf

from identity.models import AccessCapability, PatientPersonalDetails
from records import assistant, assistant_worker, journal, services, visit_brief
from records.models import (AssistantSource, AssistantTask, JournalEvent, JournalHistory,
                            PacketSourceItem, ShareGrant, TextExtraction)
from .test_assistant import AssistantTests
from .test_backend import pdf


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL immutable context, history and authority guards')
class VisitBriefIntegrationTests(TestCase):
    setUpTestData = classmethod(AssistantTests.setUpTestData.__func__)
    sign_in = AssistantTests.sign_in

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(PRIVATE_STORAGE_ROOT=Path(directory.name))
        settings.enable()
        self.addCleanup(settings.disable)
        self.sign_in(self.alice)
        self.base = f'/api/workspaces/{self.workspace.pk}/'
        self.pages = [
            {'page': 1, 'text': 'Document date: 2026-10-12\nSymptoms\n'
             'Fictional headache rated six out of ten. No nausea.\nPast medical history\n' +
             '\n'.join(f'Fictional context statement {number}; interpretation not supplied.' for number in range(45))},
            {'page': 2, 'text': 'Medications\nFictional Medicine A 5 mg was prescribed. Whether taken is unknown.\n'
             'Allergies\nNo allergy status was documented.'},
            {'page': 3, 'text': 'Investigations\nFictional haemoglobin 12.1 g/dL; interpretation not supplied.\n'
             'Plan\nFictional follow-up review planned for 2026-11-01; completion not recorded.'},
        ]
        writer = pypdf.PdfWriter()
        for page in self.pages:
            writer.add_page(pypdf.PdfReader(BytesIO(pdf(page['text']))).pages[0])
        original = BytesIO()
        writer.write(original)
        self.version, _ = services.ingest(self.alice, self.workspace.pk,
            SimpleUploadedFile('fictional-multipage-visit.pdf', original.getvalue(), content_type='application/pdf'))
        TextExtraction.objects.create(workspace=self.workspace, source_version=self.version,
            pages=self.pages, extractor_version='fictional-integration-fixture-v1', text_sha256=assistant.digest(self.pages))
        self.packet = services.create_packet(self.alice, self.workspace.pk,
            'Fictional headache follow-up preparation', [str(self.version.pk)])

    def create(self, *, include_journal=False, include_profile=False, legacy=False):
        parameters = {'packet_id': str(self.packet.pk)}
        if not legacy:
            parameters.update(visit_brief=True, visit_focus='Discuss the fictional headache history',
                patient_goals='Understand what the source documents say', patient_questions='What was documented for follow-up?',
                include_context={'profile': include_profile, 'medications': False, 'journal': include_journal, 'care': False})
        response = self.client.post(self.base + 'assistant/tasks/',
            json.dumps({'kind': 'packet_overview', 'parameters': parameters}), content_type='application/json')
        self.assertEqual(response.status_code, 202, response.content)
        return AssistantTask.objects.get(pk=response.json()['id'])

    def seed_journal(self):
        return journal.save(self.alice, self.workspace.pk, {
            'category': 'symptom', 'description': 'Fictional headache; no nausea. Cause unknown.',
            'occurrence': {'precision': 'month', 'year': 2026, 'month': 10, 'day': None},
            'time': None, 'timezone': 'Africa/Nairobi', 'fold': None, 'severity': 6, 'concern_id': None}, 0)

    def claim(self, task):
        task.state = 'processing'
        task.started_at = timezone.now()
        task.lease_token = uuid.uuid4()
        task.lease_expires_at = timezone.now() + timedelta(minutes=5)
        task.save()
        return task.lease_token

    def response(self, task):
        context, sources = assistant.task_context(task)
        plan = visit_brief.build_plan(task, context, sources)
        grouped = {}
        total = 0
        for number, item in plan['evidence'].items():
            area = item['area'] or item['hint'] or 'history'
            if len(grouped.get(area, [])) >= 8 or total >= visit_brief.MAX_SELECTED:
                continue
            grouped.setdefault(area, []).append(number)
            total += 1
        self.assertTrue(any('headache' in item['text'] for item in plan['evidence'].values()))
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
            'sections': [{'area': area, 'evidence': numbers} for area, numbers in grouped.items()]})}}],
            'usage': {'prompt_tokens': 300, 'completion_tokens': 90, 'total_tokens': 390}}

    def complete(self, task, hook=None):
        token = self.claim(task)
        response = self.response(task)
        def respond(*args, **kwargs):
            if hook:
                hook()
            return response
        with patch('intelligence.trial.configuration', return_value={
                'model': 'fictional-apertus-integration-test', 'base': 'http://fictional-inference.invalid/v1',
                'key': 'fictional-key-never-real', 'request_timeout': 300}), \
             patch('intelligence.trial.available_models'), \
             patch('intelligence.trial.request_json', side_effect=respond) as request:
            outcome = assistant_worker.process_one(task.pk, token)
        task.refresh_from_db()
        return outcome, request

    def test_new_application_request_freezes_context_and_preserves_later_report_pages(self):
        task = self.create()
        snapshot = task.parameters['visit_context']
        self.assertEqual(task.parameters['visit_context_sha256'], assistant.digest(snapshot))
        self.assertEqual(snapshot['version'], 'visit-context-v1')
        self.assertFalse(any(snapshot['included'].values()))
        self.assertEqual(snapshot['entries'], [])
        self.assertEqual(snapshot['visit']['focus'], 'Discuss the fictional headache history')
        text = '\n'.join(chunk['text'] for chunk in task.sources.get().chunks if chunk['locator']['kind'] == 'source_text')
        self.assertIn(self.pages[2]['text'], text)
        self.assertGreater(len(text), assistant.TEXT_LIMIT)
        self.assertEqual(task.coverage['text_chars_per_source'], 16000)

    def test_legacy_request_remains_document_only_and_uses_original_bound(self):
        task = self.create(legacy=True)
        self.assertEqual(task.parameters, {'packet_id': str(self.packet.pk)})
        self.assertEqual(task.coverage['text_chars_per_source'], assistant.TEXT_LIMIT)
        text = '\n'.join(chunk['text'] for chunk in task.sources.get().chunks if chunk['locator']['kind'] == 'source_text')
        self.assertNotIn(self.pages[2]['text'], text)

    def test_actual_worker_dispatch_completes_shared_pipeline_without_domain_writes_or_sensitive_provenance(self):
        event = self.seed_journal()
        task = self.create(include_journal=True)
        before = (PacketSourceItem.objects.count(), ShareGrant.objects.count(), JournalEvent.objects.count(), JournalHistory.objects.count())
        outcome, request = self.complete(task)
        self.assertEqual(outcome, 'completed')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(task.result['representation'], 'visit_brief')
        self.assertTrue(task.result['review_required'])
        self.assertTrue(task.result['patient_context'])
        self.assertFalse(task.result['modifies_packet'])
        self.assertEqual(task.result['packet_revision_id'], str(self.packet.revisions.get().pk))
        self.assertEqual(task.configuration['generation_strategy'], 'source_grounded_visit_brief')
        self.assertEqual(task.configuration['context_snapshot_sha256'], task.parameters['visit_context_sha256'])
        safe_configuration = json.dumps(task.configuration)
        for private in ('fictional-key-never-real', event.description, self.pages[0]['text'], self.pages[2]['text']):
            self.assertNotIn(private, safe_configuration)
        self.assertEqual(task.usage['completion_tokens'], 90)
        self.assertIn('pipeline_version', task.configuration)
        self.assertEqual(before, (PacketSourceItem.objects.count(), ShareGrant.objects.count(), JournalEvent.objects.count(), JournalHistory.objects.count()))
        event.refresh_from_db()
        self.assertEqual(event.revision, 1)
        response = self.client.get(self.base + f'assistant/tasks/{task.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base + f'assistant/tasks/{task.pk}/').status_code, 404)

    def test_revoked_optional_context_authority_hides_task_and_prevents_inference(self):
        self.seed_journal()
        task = self.create(include_journal=True)
        AccessCapability.objects.filter(membership__user=self.alice,
            rule__capability_key='manage_profile').update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(self.base + f'assistant/tasks/{task.pk}/').status_code, 404)
        listing = self.client.get(self.base + 'assistant/tasks/')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()['tasks'], [])
        outcome, request = self.complete(task)
        self.assertEqual(outcome, 'failed')
        request.assert_not_called()
        self.assertEqual(task.safe_error_code, 'authority_unavailable')
        self.assertIsNone(task.result)

    def test_revocation_during_model_call_discards_generated_result(self):
        self.seed_journal()
        task = self.create(include_journal=True)
        def revoke():
            AccessCapability.objects.filter(membership__user=self.alice,
                rule__capability_key='manage_profile').update(revoked_at=timezone.now())
        outcome, request = self.complete(task, hook=revoke)
        self.assertEqual(outcome, 'failed')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(task.safe_error_code, 'authority_unavailable')
        self.assertIsNone(task.result)

    def test_context_params_sources_and_completed_result_are_database_immutable(self):
        self.seed_journal()
        task = self.create(include_journal=True)
        original = json.loads(json.dumps(task.parameters))
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssistantTask.objects.filter(pk=task.pk).update(parameters={**task.parameters, 'visit_context': {}})
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssistantSource.objects.filter(task=task).update(chunks=[])
        outcome, _ = self.complete(task)
        self.assertEqual(outcome, 'completed')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssistantTask.objects.filter(pk=task.pk).update(result={'representation': 'invented'})
        task.refresh_from_db()
        self.assertEqual(task.parameters, original)

    def test_later_profile_revision_does_not_rewrite_frozen_context(self):
        profile = PatientPersonalDetails.objects.create(workspace=self.workspace, updated_by=self.alice,
            blood_group='O+', gender='Fictional reported gender')
        task = self.create(include_profile=True)
        frozen = json.loads(json.dumps(task.parameters['visit_context']))
        profile.blood_group = 'A+'
        profile.revision += 1
        profile.updated_at = timezone.now()
        profile.save(update_fields=['blood_group', 'revision', 'updated_at'])
        outcome, _ = self.complete(task)
        self.assertEqual(outcome, 'completed')
        self.assertEqual(task.parameters['visit_context'], frozen)
        self.assertIn('Blood group (patient reported, unverified): O+', json.dumps(task.result))
        self.assertNotIn('Blood group (patient reported, unverified): A+', json.dumps(task.result))
        response = self.client.get(self.base + f'assistant/tasks/{task.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['context_changed_since_request'])
