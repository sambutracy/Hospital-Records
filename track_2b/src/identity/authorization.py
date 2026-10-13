"""Deny by default. First release supports only the established self path."""
from django.db.models import F, Q
from django.utils import timezone
from .models import AccessCapability, PatientWorkspace

SELF_ACTIONS = ('read_workspace_records', 'upload_source', 'review_metadata', 'prepare_packet')


def effective_capabilities(user, action='read_workspace_records', at=None):
    if not user.is_authenticated or action not in SELF_ACTIONS:
        return AccessCapability.objects.none()
    at = at or timezone.now()
    return AccessCapability.objects.filter(
        membership__user_id=user.pk,
        membership__user__is_active=True,
        membership__user__person__status='active',
        membership__status='active', membership__revoked_at__isnull=True,
        membership__relationship_type='self', membership__authority_basis='oidc_new_subject',
        membership__valid_from__lte=at,
        membership__workspace_id=F('workspace_id'),
        membership__user__person_id=F('workspace__subject_patient__person_id'),
        rule__authority_kind='membership', rule__capability_key=action, rule__scope_kind='workspace',
        workspace_id=F('scope_workspace_id'), workspace__status='active',
        workspace__subject_patient__status='active', workspace__subject_patient__person__status='active',
        valid_from__lte=at, revoked_at__isnull=True,
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=at)).filter(
        Q(membership__valid_until__isnull=True) | Q(membership__valid_until__gt=at),
    )


def authorized_workspaces(user):
    return PatientWorkspace.objects.filter(pk__in=effective_capabilities(user).values('workspace_id')).select_related('subject_patient__person')


def can_access_workspace(user, workspace_id, action='read_workspace_records', at=None):
    return effective_capabilities(user, action, at).filter(workspace_id=workspace_id).exists()
