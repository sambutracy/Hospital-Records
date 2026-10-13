"""Native PostgreSQL transactions must handle two first callbacks safely."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, connections
from django.test import TransactionTestCase

from identity import services
from identity.models import (
    AccessCapability, AuditEvent, CapabilityRule, OIDCIdentity,
    PatientProfile, PatientWorkspace, Person, User, WorkspaceMembership,
)


@skipUnless(connection.vendor == 'postgresql', 'Requires independent PostgreSQL transactions')
class ConcurrentOnboardingTests(TransactionTestCase):
    def setUp(self):
        from identity.authorization import SELF_ACTIONS
        for action in SELF_ACTIONS:
            CapabilityRule.objects.get_or_create(
                authority_kind='membership', capability_key=action, scope_kind='workspace',
            )

    def test_same_new_subject_race_creates_one_complete_workspace(self):
        barrier = Barrier(2, timeout=10)
        thread_state = local()
        original_existing = services._existing

        def synchronized_first_read(issuer, subject):
            result = original_existing(issuer, subject)
            if not getattr(thread_state, 'read_once', False):
                thread_state.read_once = True
                self.assertIsNone(result)
                # Both callbacks observe no identity before either inserts it.
                barrier.wait()
            return result

        def onboard():
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute("SET statement_timeout = '15s'")
                return services.resolve_verified_identity(
                    'https://test.example/issuer', 'concurrent-subject', 'Concurrent patient',
                ).pk
            finally:
                connections['default'].close()

        with patch('identity.services._existing', side_effect=synchronized_first_read):
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(onboard) for _ in range(2)]
                identities = [future.result(timeout=20) for future in futures]

        self.assertEqual(identities[0], identities[1])
        for model in (Person, User, OIDCIdentity, PatientProfile, PatientWorkspace,
                      WorkspaceMembership):
            with self.subTest(model=model.__name__):
                self.assertEqual(model.objects.count(), 1)
        self.assertEqual(AccessCapability.objects.count(), 4)
        self.assertEqual(AuditEvent.objects.filter(action='onboarding.new_subject').count(), 1)
