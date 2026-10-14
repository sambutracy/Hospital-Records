"""Exact-version read grants and independent, episode-scoped contributions."""
import hashlib
import uuid
from datetime import timedelta
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from identity.authorization import effective_capabilities
from identity.models import PatientWorkspace, User, WorkspaceMembership
from . import services
from .models import (CareEpisode, ClinicalContribution, EpisodeSource, IngestionJob,
                     MetadataHead, PacketRevision, ProviderContributionAuthority,
                     ShareGrant, SourceRecord, SourceVersion)
from .storage import object_path, read_original, read_upload, write_original


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 180:
        raise ValueError('Provide a title or purpose up to 180 characters.')
    return value.strip()


def recipient(user_id, authorizer):
    try:
        target = User.objects.select_related('person').filter(pk=uuid.UUID(str(user_id)),
            is_active=True, person__status='active').first()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Use the recipient’s Comfort account ID.') from None
    if not target or target.pk == authorizer.pk:
        raise Http404
    return target


def grant_window(minutes):
    if type(minutes) is not int or not 1 <= minutes <= 10080:
        raise ValueError('Choose an expiry between one minute and seven days.')
    now = timezone.now()
    return now, now + timedelta(minutes=minutes)


def create_episode(user, workspace_id, title):
    title = text(title)
    with transaction.atomic():
        workspace, _ = services.authorize(user, workspace_id, 'manage_episode_links', lock=True)
        services.authorize(user, workspace_id, lock=True)
        episode = CareEpisode.objects.create(workspace=workspace, title=title, created_by=user)
        services.audit(user, workspace, 'episode.create', episode)
        return episode


def link_sources(user, workspace_id, episode_id, version_ids):
    if not isinstance(version_ids, list) or not 1 <= len(version_ids) <= 30:
        raise ValueError('Select one to 30 original versions.')
    ids = [uuid.UUID(str(value)) for value in version_ids]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate source selection.')
    with transaction.atomic():
        workspace, _ = services.authorize(user, workspace_id, 'manage_episode_links', lock=True)
        services.authorize(user, workspace_id, lock=True)
        episode = CareEpisode.objects.filter(pk=episode_id, workspace=workspace).first()
        versions = list(SourceVersion.objects.filter(workspace=workspace, pk__in=ids))
        if not episode or len(versions) != len(ids):
            raise Http404
        for version in versions:
            EpisodeSource.objects.get_or_create(workspace=workspace, episode=episode,
                source_version=version, defaults={'linked_by': user})
        services.audit(user, workspace, 'episode.link_sources', episode)
        return episode


def create_grant(user, workspace_id, kind, target_id, recipient_id, purpose, minutes):
    if kind not in ('read', 'contribute'):
        raise ValueError('Unknown grant kind.')
    target_id = uuid.UUID(str(target_id))
    purpose = text(purpose)
    starts, expires = grant_window(minutes)
    action = 'create_share' if kind == 'read' else 'authorize_provider_contribution'
    with transaction.atomic():
        workspace, cap = services.authorize(user, workspace_id, action, lock=True)
        services.authorize(user, workspace_id, lock=True)
        target = recipient(recipient_id, user)
        common = dict(workspace=workspace, recipient=target, authorizing_membership=cap.membership,
                      purpose=purpose, starts_at=starts, expires_at=expires)
        if kind == 'read':
            revision = PacketRevision.objects.filter(pk=target_id, workspace=workspace, state='approved').first()
            if not revision or not revision.items.exists():
                raise Http404
            grant = ShareGrant.objects.create(packet_revision=revision, **common)
        elif kind == 'contribute':
            episode = CareEpisode.objects.filter(pk=target_id, workspace=workspace).first()
            if not episode:
                raise Http404
            grant = ProviderContributionAuthority.objects.create(episode=episode, **common)
        else:
            raise ValueError('Unknown grant kind.')
        services.audit(user, workspace, 'grant.' + kind + '.approve', grant)
        return grant


def live_grant(user, grant_id, kind, lock=False):
    model = ShareGrant if kind == 'read' else ProviderContributionAuthority
    query = model.objects.select_related('authorizing_membership__user__person', 'workspace')
    grant = query.filter(pk=grant_id, recipient=user).first()
    if grant and lock:
        PatientWorkspace.objects.select_for_update().get(pk=grant.workspace_id)
        WorkspaceMembership.objects.select_for_update().get(pk=grant.authorizing_membership_id)
        grant = query.select_for_update(of=('self',)).get(pk=grant.pk)
    now = timezone.now()
    action = 'create_share' if kind == 'read' else 'authorize_provider_contribution'
    if (not grant or not User.objects.filter(pk=user.pk,is_active=True,person__status='active').exists()
            or grant.revoked_at or not grant.starts_at <= now < grant.expires_at):
        raise Http404
    owner = grant.authorizing_membership.user
    if not effective_capabilities(owner, action, now).filter(
            membership_id=grant.authorizing_membership_id, workspace_id=grant.workspace_id).exists():
        raise Http404
    if not effective_capabilities(owner, 'read_workspace_records', now).filter(
            membership_id=grant.authorizing_membership_id, workspace_id=grant.workspace_id).exists():
        raise Http404
    return grant


def revoke(user, workspace_id, grant_id, kind):
    model = ShareGrant if kind == 'read' else ProviderContributionAuthority
    action = 'revoke_share' if kind == 'read' else 'authorize_provider_contribution'
    with transaction.atomic():
        workspace, _ = services.authorize(user, workspace_id, action, lock=True)
        grant = model.objects.select_for_update().filter(pk=grant_id, workspace=workspace).first()
        if not grant:
            raise Http404
        if grant.revoked_at is None:
            grant.revoked_at = timezone.now()
            grant.save(update_fields=['revoked_at'])
            services.audit(user, workspace, 'grant.' + kind + '.revoke', grant)
        return grant


def contribute(user, grant_id, upload, content_kind='document'):
    live_grant(user, grant_id, 'contribute')
    if content_kind not in ('document', 'medical_image'):
        raise ValueError('Choose a valid record kind.')
    data, name, media = read_upload(upload)
    if media == 'application/dicom':
        content_kind = 'medical_image'
    if media == 'application/pdf' and content_kind != 'document':
        raise ValueError('Use document for a report PDF.')
    checksum = hashlib.sha256(data).hexdigest()
    written = None
    try:
        with transaction.atomic():
            grant = live_grant(user, grant_id, 'contribute', lock=True)
            existing = ClinicalContribution.objects.filter(authority=grant, sha256=checksum).first()
            if existing:
                if existing.content_kind != content_kind:
                    raise services.Conflict('These bytes already have a different record kind.')
                return existing, False
            key = f'{grant.workspace_id}/{uuid.uuid4()}'
            write_original(key, data)
            written = key
            submission = ClinicalContribution.objects.create(workspace=grant.workspace, authority=grant,
                submitted_by=user, private_object_key=key, sha256=checksum, byte_size=len(data),
                media_type=media, content_kind=content_kind, original_filename=name)
            services.audit(user, grant.workspace, 'contribution.submit', submission)
            return submission, True
    except Exception:
        if written:
            try:
                object_path(written).unlink()
            except OSError:
                pass
        raise


def review_contribution(user, workspace_id, contribution_id, decision):
    if decision not in ('accept', 'reject'):
        raise ValueError('Choose accept or reject.')
    with transaction.atomic():
        workspace, _ = services.authorize(user, workspace_id, 'review_contribution', lock=True)
        services.authorize(user, workspace_id, lock=True)
        item = ClinicalContribution.objects.select_for_update().select_related('authority').filter(
            pk=contribution_id, workspace=workspace).first()
        if not item:
            raise Http404
        if item.state != 'pending':
            raise services.Conflict('This submission has already been reviewed.')
        if decision == 'accept':
            services.authorize(user, workspace_id, 'upload_source', lock=True)
            # Submission was authorized when received. Later grant expiry/revocation does
            # not delete its evidence or prevent independent patient review.
            read_original(item)
            if SourceVersion.objects.filter(workspace=workspace, sha256=item.sha256).exists():
                raise services.Conflict('These bytes already exist in your accepted records. Reject the duplicate submission.')
            record = SourceRecord.objects.create(workspace=workspace, submitted_by=item.submitted_by)
            version = SourceVersion.objects.create(workspace=workspace, record=record, version_number=1,
                submitted_by=item.submitted_by, private_object_key=item.private_object_key,
                sha256=item.sha256, byte_size=item.byte_size, media_type=item.media_type,
                content_kind=item.content_kind, original_filename=item.original_filename)
            record.current_version = version
            record.save(update_fields=['current_version'])
            MetadataHead.objects.create(workspace=workspace, source_version=version)
            IngestionJob.objects.create(workspace=workspace, source_version=version, requested_by=user)
            EpisodeSource.objects.create(workspace=workspace, episode=item.authority.episode,
                source_version=version, linked_by=user)
            item.accepted_source = version
        item.state = 'accepted' if decision == 'accept' else 'rejected'
        item.reviewed_by = user
        item.reviewed_at = timezone.now()
        item.save(update_fields=['state', 'reviewed_by', 'reviewed_at', 'accepted_source'])
        services.audit(user, workspace, 'contribution.' + decision, item)
        return item
