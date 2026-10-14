from functools import wraps
from io import BytesIO
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from identity.models import AuditEvent
from . import continuity, services
from .metadata import FIELDS, assertion_value
from .models import (CareEpisode, ClinicalContribution, ProviderContributionAuthority,
                     ShareGrant, SourceRecord, SourceVersion)
from .storage import read_original
from .views import api, body


def checked(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except Http404:
            # Outside service transactions: denied attempts survive a rollback.
            AuditEvent.objects.create(actor_user=request.user, action='continuity.' + view.__name__,
                decision='deny', target_type='continuity_request')
            raise
    return api(wrapped)


def exact(value, fields):
    if set(value) != set(fields):
        raise ValueError('Unexpected fields.')
    return value


def grant_payload(grant, kind):
    return {'id': grant.pk, 'kind': kind, 'recipient_id': grant.recipient_id,
        'recipient_name': grant.recipient.person.display_name, 'purpose': grant.purpose,
        'starts_at': grant.starts_at, 'expires_at': grant.expires_at, 'revoked_at': grant.revoked_at,
        'state': 'revoked' if grant.revoked_at else 'expired' if grant.expires_at <= timezone.now() else 'active',
        'target_id': grant.packet_revision_id if kind == 'read' else grant.episode_id,
        'professional_identity': 'invited account; professional identity not verified'}


def contribution_payload(item):
    return {'id': item.pk, 'authority_id': item.authority_id, 'episode_id': item.authority.episode_id,
        'submitted_by_id': item.submitted_by_id, 'submitted_by_name': item.submitted_by.person.display_name,
        'original_filename': item.original_filename, 'sha256': item.sha256, 'byte_size': item.byte_size,
        'media_type': item.media_type, 'content_kind': item.content_kind, 'state': item.state,
        'created_at': item.created_at, 'reviewed_at': item.reviewed_at, 'accepted_source_id': item.accepted_source_id,
        'attribution': 'submitted by invited account; professional identity not verified'}


@ensure_csrf_cookie
@require_GET
@checked
def account(request):
    return JsonResponse({'id': request.user.pk, 'name': request.user.person.display_name})


@require_GET
@login_required
@ensure_csrf_cookie
def received_page(request):
    return render(request, 'received_access.html')


@require_http_methods(['GET', 'POST'])
@checked
def episodes(request, workspace_id):
    if request.method == 'POST':
        values = exact(body(request), ['title'])
        item = continuity.create_episode(request.user, workspace_id, values['title'])
        return JsonResponse({'id': item.pk, 'title': item.title}, status=201)
    services.authorize(request.user, workspace_id)
    return JsonResponse({'episodes': [{'id': e.pk, 'title': e.title,
        'source_version_ids': list(e.sources.values_list('source_version_id', flat=True))}
        for e in CareEpisode.objects.filter(workspace_id=workspace_id).order_by('-created_at')[:50]]})


@require_POST
@checked
def episode_sources(request, workspace_id, episode_id):
    values = exact(body(request), ['source_version_ids'])
    item = continuity.link_sources(request.user, workspace_id, episode_id, values['source_version_ids'])
    return JsonResponse({'id': item.pk, 'source_version_ids': list(item.sources.values_list('source_version_id', flat=True))})


@require_POST
@checked
def resolve_recipient(request, workspace_id):
    services.authorize(request.user, workspace_id, 'create_share')
    services.authorize(request.user, workspace_id)
    values = exact(body(request), ['recipient_id'])
    target = continuity.recipient(values['recipient_id'], request.user)
    return JsonResponse({'id': target.pk, 'name': target.person.display_name,
        'professional_identity': 'Account name only; professional identity not verified'})


@require_http_methods(['GET', 'POST'])
@checked
def grants(request, workspace_id):
    if request.method == 'POST':
        values = exact(body(request), ['kind', 'target_id', 'recipient_id', 'purpose', 'expires_in_minutes'])
        if values['kind'] not in ('read', 'contribute'):
            raise ValueError('Unknown grant kind.')
        item = continuity.create_grant(request.user, workspace_id, values['kind'], values['target_id'],
            values['recipient_id'], values['purpose'], values['expires_in_minutes'])
        return JsonResponse(grant_payload(item, values['kind']), status=201)
    services.authorize(request.user, workspace_id)
    return JsonResponse({'grants': [grant_payload(g, kind)
        for model, kind in ((ShareGrant, 'read'), (ProviderContributionAuthority, 'contribute'))
        for g in model.objects.filter(workspace_id=workspace_id).select_related('recipient__person').order_by('-created_at')[:50]]})


@require_POST
@checked
def revoke_grant(request, workspace_id, kind, grant_id):
    if kind not in ('read', 'contribute'):
        raise Http404
    exact(body(request), [])
    item = continuity.revoke(request.user, workspace_id, grant_id, kind)
    return JsonResponse(grant_payload(item, kind))


@require_GET
@checked
def received(request):
    visible = []
    for model, kind in ((ShareGrant, 'read'), (ProviderContributionAuthority, 'contribute')):
        for item in model.objects.filter(recipient=request.user, revoked_at__isnull=True,
                starts_at__lte=timezone.now(), expires_at__gt=timezone.now()).order_by('-created_at')[:50]:
            try:
                grant = continuity.live_grant(request.user, item.pk, kind)
            except Http404:
                continue
            payload = grant_payload(grant, kind)
            payload['patient_name'] = grant.workspace.subject_patient.person.display_name
            if kind == 'contribute':
                payload['episode_title'] = grant.episode.title
                payload['submissions'] = [contribution_payload(s) for s in grant.submissions.select_related(
                    'submitted_by__person', 'authority').order_by('-created_at')[:50]]
            visible.append(payload)
    return JsonResponse({'grants': visible})


@require_GET
@checked
def shared_packet(request, grant_id):
    with transaction.atomic():
        grant = continuity.live_grant(request.user, grant_id, 'read', lock=True)
        # Construct only the approved version/metadata snapshot, never the workspace payload.
        items = []
        for item in grant.packet_revision.items.select_related('source_version', *FIELDS).order_by('created_at', 'id'):
            version = item.source_version
            items.append({'source_version_id': version.pk, 'original_filename': version.original_filename,
                'sha256': version.sha256, 'media_type': version.media_type,
                'metadata': {field: assertion_value(getattr(item, field)) for field in FIELDS},
                'facility_maps_url': item.facility_name.facility_maps_url if item.facility_name else None,
                'download_url': f'/api/continuity/shares/{grant.pk}/versions/{version.pk}/original/'})
        services.audit(request.user, grant.workspace, 'share.packet_read', grant)
        return JsonResponse({'grant_id': grant.pk, 'purpose': grant.purpose, 'expires_at': grant.expires_at,
            'items': items, 'access': 'selected versions only; no AI drafts or write permission'})


@require_GET
@checked
def shared_original(request, grant_id, version_id):
    with transaction.atomic():
        grant = continuity.live_grant(request.user, grant_id, 'read', lock=True)
        item = grant.packet_revision.items.select_related('source_version').filter(source_version_id=version_id).first()
        if not item:
            raise Http404
        version = item.source_version
        data = read_original(version)
        services.audit(request.user, grant.workspace, 'share.source_download', version)
    return FileResponse(BytesIO(data), as_attachment=True, filename=version.original_filename, content_type=version.media_type)


@require_POST
@checked
def submit_contribution(request, grant_id):
    continuity.live_grant(request.user, grant_id, 'contribute')
    files = request.FILES
    if (getattr(request, 'upload_too_large', False) or set(files) != {'file'}
            or len(files.getlist('file')) != 1 or set(request.POST) - {'content_kind'}
            or len(request.POST.getlist('content_kind')) > 1):
        raise ValueError('Upload one supported original up to 10 MB.')
    item, created = continuity.contribute(request.user, grant_id, files['file'], request.POST.get('content_kind', 'document'))
    return JsonResponse(contribution_payload(item), status=201 if created else 200)


@require_GET
@checked
def inbox(request, workspace_id):
    services.authorize(request.user, workspace_id, 'review_contribution')
    services.authorize(request.user, workspace_id)
    return JsonResponse({'contributions': [contribution_payload(s) for s in
        ClinicalContribution.objects.filter(workspace_id=workspace_id).select_related(
            'submitted_by__person', 'authority').order_by('-created_at')[:50]]})


@require_GET
@checked
def contribution_original(request, workspace_id, contribution_id):
    workspace, _ = services.authorize(request.user, workspace_id, 'review_contribution')
    services.authorize(request.user, workspace_id)
    item = ClinicalContribution.objects.filter(workspace=workspace, pk=contribution_id).first()
    if not item:
        raise Http404
    data = read_original(item)
    services.audit(request.user, workspace, 'contribution.review_download', item)
    return FileResponse(BytesIO(data), as_attachment=True, filename=item.original_filename, content_type=item.media_type)


@require_POST
@checked
def review_contribution(request, workspace_id, contribution_id):
    values = exact(body(request), ['decision'])
    item = continuity.review_contribution(request.user, workspace_id, contribution_id, values['decision'])
    return JsonResponse(contribution_payload(item))
