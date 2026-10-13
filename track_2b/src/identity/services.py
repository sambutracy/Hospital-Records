"""Trusted new-subject onboarding, called only after OIDC validation."""
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from .models import (
    AccessCapability, AuditEvent, CapabilityRule, OIDCIdentity,
    PatientProfile, PatientWorkspace, Person, User, WorkspaceMembership,
)


def _existing(issuer, subject):
    identity = OIDCIdentity.objects.select_related('user__person').filter(issuer=issuer, subject=subject).first()
    if identity and (not identity.user.is_active or identity.user.person.status != 'active'):
        raise PermissionDenied('Account is unavailable.')
    return identity.user if identity else None


def resolve_verified_identity(issuer, subject, display_name):
    """Never link by email or accept a client-selected existing person/workspace."""
    existing = _existing(issuer, subject)
    if existing:
        return existing
    try:
        with transaction.atomic():
            person = Person.objects.create(display_name=display_name[:160] or 'Patient')
            user = User.objects.create_user(person=person)
            OIDCIdentity.objects.create(issuer=issuer, subject=subject, user=user)
            patient = PatientProfile.objects.create(person=person)
            workspace = PatientWorkspace.objects.create(subject_patient=patient)
            membership = WorkspaceMembership.objects.create(
                workspace=workspace, user=user, relationship_type='self',
                authority_basis='oidc_new_subject',
            )
            from .authorization import SELF_ACTIONS
            for action in SELF_ACTIONS:
                rule = CapabilityRule.objects.get(
                    authority_kind='membership', capability_key=action, scope_kind='workspace',
                )
                AccessCapability.objects.create(
                    workspace=workspace, membership=membership, rule=rule,
                    scope_workspace=workspace, valid_from=membership.valid_from,
                )
            AuditEvent.objects.create(
                workspace=workspace, actor_user=user, action='onboarding.new_subject',
                decision='allow', target_type='patient_workspace', target_id=workspace.id,
            )
            return user
    except IntegrityError:
        # A racing callback may have inserted the same unique issuer/subject.
        # Everything in our losing transaction rolled back, including the person.
        existing = _existing(issuer, subject)
        if existing:
            return existing
        raise
