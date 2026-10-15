from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase,override_settings
from unittest.mock import patch,Mock
from types import SimpleNamespace
from records.management.commands.ecosystem_jobs import check_fixture_sources


class EcosystemGuardTests(SimpleTestCase):
    def test_capture_rejects_unlisted_originals_even_for_a_fixture_account(self):
        suite={'documents':[{'sha256':'known'}],'auxiliary_documents':[]}
        with self.assertRaisesRegex(CommandError,'Non-fixture source bytes'):
            check_fixture_sources(SimpleNamespace(source_version=SimpleNamespace(sha256='unlisted')),'record',suite)
        check_fixture_sources(SimpleNamespace(source_version=SimpleNamespace(sha256='known')),'record',suite)

    def test_capture_rejects_mixed_or_empty_assistant_source_sets(self):
        suite={'documents':[{'sha256':'known'}],'auxiliary_documents':[]}
        sources=Mock()
        for values in ([],['known','unlisted']):
            sources.values_list.return_value=values
            with self.assertRaisesRegex(CommandError,'Non-fixture source bytes'):
                check_fixture_sources(SimpleNamespace(sources=sources),'assistant',suite)
    @override_settings(DEMO_MODE=True)
    def test_ordinary_application_cannot_dispatch_fixture_jobs(self):
        with patch.dict('os.environ',{'COMFORT_SYNTHETIC_ECOSYSTEM':''}):
            with self.assertRaisesRegex(CommandError,'Dedicated synthetic stack'):
                call_command('ecosystem_jobs',mode='inspect')

    @override_settings(DEMO_MODE=False)
    def test_marker_cannot_enable_dispatch_outside_demo_mode(self):
        with patch.dict('os.environ',{'COMFORT_SYNTHETIC_ECOSYSTEM':'comfort-ecosystem-v1'}):
            with self.assertRaisesRegex(CommandError,'Dedicated synthetic stack'):
                call_command('ecosystem_jobs',mode='live',ids=['00000000-0000-0000-0000-000000000000'])

    @override_settings(DEMO_MODE=False)
    def test_private_capture_cannot_run_in_ordinary_stack(self):
        with self.assertRaisesRegex(CommandError,'Dedicated synthetic stack'):
            call_command('ecosystem_capture','record','00000000-0000-0000-0000-000000000000','00000000-0000-0000-0000-000000000000')
