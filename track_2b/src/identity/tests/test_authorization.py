import time
import uuid
from datetime import timedelta
from django.contrib.auth import authenticate
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase
from django.utils import timezone
from unittest import skipUnless
from identity.authorization import can_access_workspace
from identity.models import (
    AccessCapability, AuditEvent, CapabilityRule, OIDCIdentity,
    PatientProfile, PatientWorkspace, Person, User, WorkspaceMembership,
)
from identity.services import resolve_verified_identity
from identity.db_roles import configure_runtime_permissions


class IdentityFixture:
    @classmethod
    def setUpTestData(cls):
        cls.alice = resolve_verified_identity('https://test.example/issuer', 'alice', 'Alice')
        cls.bob = resolve_verified_identity('https://test.example/issuer', 'bob', 'Bob')
        cls.workspace = PatientWorkspace.objects.get(subject_patient__person=cls.alice.person)
        cls.membership = WorkspaceMembership.objects.get(user=cls.alice)
        cls.capability = AccessCapability.objects.get(membership=cls.membership, rule__capability_key='read_workspace_records')


class AuthorizationTests(IdentityFixture, TestCase):
    def sign_in(self, user=None):
        self.client.force_login(user or self.alice, backend='identity.backends.OIDCSessionBackend')
        session = self.client.session
        session['oidc_expires_at'] = int(time.time()) + 300
        session.save()

    def test_onboarding_is_atomic_and_idempotent(self):
        user = resolve_verified_identity('https://test.example/issuer', 'alice', 'Renamed')
        self.assertEqual(user.pk, self.alice.pk)
        self.assertEqual(Person.objects.count(), 2)
        self.assertEqual(PatientWorkspace.objects.count(), 2)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(AuditEvent.objects.filter(action='onboarding.new_subject').count(), 2)

    def test_patient_can_exist_without_login(self):
        profile = PatientProfile.objects.create(person=Person.objects.create(display_name='Dependent'))
        PatientWorkspace.objects.create(subject_patient=profile)
        self.assertFalse(User.objects.filter(person=profile.person).exists())

    def test_self_without_explicit_capability_is_denied(self):
        AccessCapability.objects.filter(pk=self.capability.pk).update(revoked_at=timezone.now())
        self.assertFalse(can_access_workspace(self.alice, self.workspace.pk))

    def test_own_empty_page_and_unrelated_workspace_denied(self):
        self.sign_in()
        page = self.client.get(f'/workspaces/{self.workspace.pk}/')
        self.assertContains(page, 'Your records, ready for your next visit.')
        self.assertEqual(self.client.get(f'/api/workspaces/{self.workspace.pk}/records/').json()['records'], [])
        self.assertEqual(page['Cache-Control'], 'no-store, private')
        self.assertIn("frame-ancestors 'none'", page['Content-Security-Policy'])
        bob_workspace = PatientWorkspace.objects.get(subject_patient__person=self.bob.person)
        forbidden = self.client.get(f'/workspaces/{bob_workspace.pk}/')
        nonexistent = self.client.get(f'/workspaces/{uuid.uuid4()}/')
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(nonexistent.status_code, 404)
        self.assertNotContains(forbidden, 'Bob', status_code=404)
        self.assertTrue(AuditEvent.objects.filter(actor_user=self.alice, action='workspace.open', decision='deny').exists())

    def test_unknown_action_and_role_flags_do_not_grant_access(self):
        self.assertFalse(can_access_workspace(self.alice, self.workspace.pk, 'manage_appointments'))
        self.assertFalse(can_access_workspace(self.bob, self.workspace.pk))
        self.bob.is_staff = True
        self.bob.is_superuser = True
        self.assertFalse(can_access_workspace(self.bob, self.workspace.pk))

    def test_caregiver_membership_is_not_authority(self):
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.bob, relationship_type='caregiver',
            authority_basis='relationship_only',
        )
        self.assertFalse(can_access_workspace(self.bob, self.workspace.pk))

    def test_membership_suspension_and_revocation_apply_next_request(self):
        self.sign_in()
        for change in ({'status': 'suspended'}, {'status': 'revoked'}, {'status': 'active', 'revoked_at': timezone.now()}):
            WorkspaceMembership.objects.filter(pk=self.membership.pk).update(**change)
            self.assertEqual(self.client.get(f'/workspaces/{self.workspace.pk}/').status_code, 404)
        self.assertEqual(self.client.get('/workspaces/').status_code, 200)

    def test_capability_and_parent_validity_intersection(self):
        now = timezone.now()
        self.assertTrue(can_access_workspace(self.alice, self.workspace.pk, at=now))
        self.assertFalse(can_access_workspace(self.alice, self.workspace.pk, at=self.membership.valid_from - timedelta(seconds=1)))
        AccessCapability.objects.filter(pk=self.capability.pk).update(valid_until=now + timedelta(seconds=5))
        self.assertFalse(can_access_workspace(self.alice, self.workspace.pk, at=now + timedelta(seconds=5)))
        # A shortened parent restricts an existing longer capability immediately.
        WorkspaceMembership.objects.filter(pk=self.membership.pk).update(valid_until=now + timedelta(seconds=2))
        self.assertFalse(can_access_workspace(self.alice, self.workspace.pk, at=now + timedelta(seconds=3)))

    def test_disabled_subject_and_workspace_deny(self):
        PatientProfile.objects.filter(pk=self.workspace.subject_patient_id).update(status='disabled')
        self.assertFalse(can_access_workspace(self.alice, self.workspace.pk))
        PatientProfile.objects.filter(pk=self.workspace.subject_patient_id).update(status='active')
        PatientWorkspace.objects.filter(pk=self.workspace.pk).update(status='disabled')
        self.assertFalse(can_access_workspace(self.alice, self.workspace.pk))

    def test_disabled_account_ends_existing_session_and_is_not_restored(self):
        self.sign_in()
        User.objects.filter(pk=self.alice.pk).update(is_active=False)
        self.assertEqual(self.client.get(f'/workspaces/{self.workspace.pk}/').status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            resolve_verified_identity('https://test.example/issuer', 'alice', 'Alice')

    def test_expired_session_redirects_without_workspace_data(self):
        self.sign_in()
        session = self.client.session
        session['oidc_expires_at'] = int(time.time()) - 1
        session.save()
        self.assertEqual(self.client.get(f'/workspaces/{self.workspace.pk}/').status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_anonymous_and_local_password_login_are_denied(self):
        self.assertEqual(self.client.get(f'/workspaces/{self.workspace.pk}/').status_code, 302)
        self.assertIsNone(authenticate(username=str(self.alice.pk), password='anything'))
        self.assertEqual(self.client.get('/auth/login/').status_code, 405)
        self.assertEqual(self.client.get('/auth/logout/').status_code, 405)

    def test_csrf_required_for_signin_and_signout(self):
        browser = Client(enforce_csrf_checks=True)
        self.assertEqual(browser.post('/auth/login/').status_code, 403)
        self.assertEqual(browser.post('/auth/logout/').status_code, 403)

    def test_local_signin_form_preserves_origin_and_rejects_untrusted_origins(self):
        browser = Client(enforce_csrf_checks=True)
        page = browser.get('/', HTTP_HOST='localhost')
        self.assertEqual(page['Referrer-Policy'], 'same-origin')
        self.assertIn("form-action 'self' http://localhost:8081;", page['Content-Security-Policy'])
        token = browser.cookies['csrftoken'].value
        for origin in ('null', 'https://untrusted.example'):
            self.assertEqual(browser.post(
                '/auth/login/', {'csrfmiddlewaretoken': token},
                HTTP_HOST='localhost', HTTP_ORIGIN=origin,
            ).status_code, 403)
        result = browser.post(
            '/auth/login/', {'csrfmiddlewaretoken': token},
            HTTP_HOST='localhost', HTTP_ORIGIN='http://localhost:8000',
        )
        self.assertEqual(result.status_code, 302)
        self.assertIn('/protocol/openid-connect/auth?', result['Location'])

    def test_logout_invalidates_local_session_before_provider_response(self):
        self.sign_in()
        response = self.client.post('/auth/logout/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/protocol/openid-connect/logout?', response['Location'])
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(f'/workspaces/{self.workspace.pk}/').status_code, 302)

    def test_partial_date_null_shape_enforced(self):
        Person.objects.create(display_name='Year only', birth_year=2024, birth_date_precision='year')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Person.objects.create(display_name='Invalid', birth_year=2024, birth_day=1, birth_date_precision='year')

    def test_unknown_capability_catalogue_row_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CapabilityRule.objects.create(authority_kind='share_grant', capability_key='upload_source', scope_kind='workspace')


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL-specific database guards')
class PostgreSQLGuardTests(IdentityFixture, TestCase):
    # These tests require PostgreSQL, rather than merely model validation.
    def test_cross_workspace_capability_rejected_by_database(self):
        other = PatientWorkspace.objects.get(subject_patient__person=self.bob.person)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessCapability.objects.create(
                workspace=other, scope_workspace=other, membership=self.membership,
                rule=self.capability.rule, valid_from=self.membership.valid_from,
            )

    def test_false_self_membership_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkspaceMembership.objects.create(
                workspace=self.workspace, user=self.bob, relationship_type='self', authority_basis='oidc_new_subject',
            )

    def test_guardian_requires_recorded_basis(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkspaceMembership.objects.create(
                workspace=self.workspace, user=self.bob, relationship_type='guardian', authority_basis='verified_guardianship',
            )

    def test_calendar_leap_year_and_invalid_month_day(self):
        Person.objects.create(display_name='Leap', birth_year=2024, birth_month=2, birth_day=29, birth_date_precision='day')
        Person.objects.create(display_name='Century leap', birth_year=2000, birth_month=2, birth_day=29, birth_date_precision='day')
        for year, month, day in ((2023, 2, 29), (1900, 2, 29), (2024, 4, 31)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Person.objects.create(display_name='Invalid', birth_year=year, birth_month=month, birth_day=day, birth_date_precision='day')

    def test_identity_subject_and_membership_bindings_are_immutable(self):
        changes = [
            (User.objects.filter(pk=self.alice.pk), {'person': self.bob.person}),
            (PatientWorkspace.objects.filter(pk=self.workspace.pk), {'subject_patient': self.bob.person.patientprofile}),
            (OIDCIdentity.objects.filter(user=self.alice), {'subject': 'rebound'}),
            (WorkspaceMembership.objects.filter(pk=self.membership.pk), {'user': self.bob}),
        ]
        for rows, update in changes:
            with self.assertRaises(IntegrityError), transaction.atomic():
                rows.update(**update)

    def test_audit_and_rule_rows_cannot_be_overwritten(self):
        event = AuditEvent.objects.filter(actor_user=self.alice).first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).update(decision='deny')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CapabilityRule.objects.filter(pk=self.capability.rule_id).update(scope_kind='workspace')

    def test_capability_cannot_outlive_parent_when_issued(self):
        WorkspaceMembership.objects.filter(pk=self.membership.pk).update(valid_until=timezone.now() + timedelta(seconds=5))
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessCapability.objects.filter(pk=self.capability.pk).update(valid_until=timezone.now() + timedelta(seconds=10))
        WorkspaceMembership.objects.filter(pk=self.membership.pk).update(status='revoked')
        # Revocation remains possible even when the parent is already revoked.
        AccessCapability.objects.filter(pk=self.capability.pk).update(revoked_at=timezone.now())


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL-specific role permissions')
class PostgreSQLRoleTests(IdentityFixture, TestCase):
    def setUp(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='continuity_app'")
            if cursor.fetchone() is None:
                cursor.execute('CREATE ROLE continuity_app NOSUPERUSER NOCREATEDB NOCREATEROLE')
        configure_runtime_permissions(connection)

    def test_runtime_role_can_onboard_and_authorize_without_owning_schema(self):
        with connection.cursor() as cursor:
            cursor.execute('SET LOCAL ROLE continuity_app')
            cursor.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user')
            self.assertFalse(cursor.fetchone()[0])
        user = resolve_verified_identity('https://test.example/issuer', 'runtime-person', 'Runtime person')
        workspace = PatientWorkspace.objects.get(subject_patient__person=user.person)
        self.assertTrue(can_access_workspace(user, workspace.pk))

    def test_runtime_cannot_overwrite_audit_or_modify_catalogue(self):
        from django.db import DatabaseError
        for sql in ('UPDATE audit_events SET decision=decision', 'DELETE FROM capability_rules', 'CREATE TABLE forbidden_schema_change(id integer)'):
            with self.subTest(sql=sql):
                with self.assertRaises(DatabaseError) as caught, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute('SET LOCAL ROLE continuity_app')
                        cursor.execute(sql)
                self.assertEqual(caught.exception.__cause__.sqlstate, '42501')
