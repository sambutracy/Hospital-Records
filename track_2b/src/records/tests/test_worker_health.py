import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock,patch
from django.test import SimpleTestCase,TestCase,override_settings
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from identity.models import PatientWorkspace
from identity.services import resolve_verified_identity
from records import worker_health,services,assistant
from records.tests.test_backend import pdf


class WorkerHealthTests(SimpleTestCase):
    def test_missing_stale_and_stopped_workers_are_not_reported_ready(self):
        with TemporaryDirectory() as directory,override_settings(PRIVATE_STORAGE_ROOT=Path(directory)):
            self.assertFalse(worker_health.status()['available'])
            worker_health.beat('fixture','assistant')
            self.assertTrue(worker_health.status()['available'])
            self.assertNotIn('instance',worker_health.status())
            with patch('records.worker_health.time.time',return_value=time.time()+25):
                self.assertFalse(worker_health.status()['available'])
            worker_health.beat('fixture','assistant','stopped')
            self.assertFalse(worker_health.status()['available'])
            worker_health.beat('fixture','record')
            self.assertFalse(worker_health.status()['available'])


class WorkerSchedulingTests(TestCase):
    def test_assistant_only_worker_does_not_claim_bulk_ingestion_jobs(self):
        self.assert_interactive_dispatch('assistant')

    def test_normal_worker_gives_interactive_requests_a_turn_before_bulk_metadata(self):
        self.assert_interactive_dispatch('all')

    def assert_interactive_dispatch(self,kind):
        with TemporaryDirectory() as directory,override_settings(PRIVATE_STORAGE_ROOT=Path(directory)):
            user=resolve_verified_identity('https://test.example/issuer','worker-fixture','Worker fixture')
            workspace=PatientWorkspace.objects.get(subject_patient__person=user.person)
            version,_=services.ingest(user,workspace.pk,SimpleUploadedFile('demo.pdf',pdf()))
            task=assistant.create_task(user,workspace.pk,'search',{'query':'demo'})
            process=Mock();process.poll.return_value=0;process.returncode=0
            from intelligence.trial import TrialError
            with patch('records.management.commands.process_records.subprocess.Popen',return_value=process),patch(
                'records.management.commands.process_records.configuration',side_effect=TrialError('missing')):
                call_command('process_records',kind=kind,once=True)
            task.refresh_from_db()
            self.assertEqual(task.state,'processing')  # Mock child claims no successful generation.
            self.assertEqual(version.jobs.get().state,'queued')
            self.assertFalse(worker_health.status()['available'])
