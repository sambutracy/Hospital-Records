"""Patient-reported concerns and care participation, independent of access grants."""
from calendar import monthrange
from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from identity.profile_services import text, revision
from . import services
from .metadata import validate_values
from .models import PatientHealthConcern, ReportedPractitioner, CareTeamAssignment, CareHistory

KINDS = {
    'concerns': ('concern', PatientHealthConcern, {'title':180, 'description':1000, 'kind':24, 'certainty':32, 'onset':None}),
    'practitioners': ('practitioner', ReportedPractitioner, {'name':160, 'specialty':120, 'facility':180, 'notes':500}),
    'assignments': ('assignment', CareTeamAssignment, {'practitioner_id':None, 'concern_id':None, 'role':120,
        'participation':16, 'start_date':None, 'end_date':None, 'notes':500}),
}


def authorize(user, workspace_id, lock=False):
    # Existing patient-profile authority covers private, patient-reported relationships.
    workspace, _ = services.authorize(user, workspace_id, 'manage_profile', lock=lock)
    services.authorize(user, workspace_id, lock=lock)
    return workspace


def care_date(value):
    validate_values({'document_type':'other', 'document_date':value, 'facility_name':None})
    return value.copy()


def date_bounds(parts):
    if parts['precision'] == 'unknown':
        return None
    year = parts['year']; month = parts['month']; day = parts['day']
    return (date(year, month or 1, day or 1),
        date(year, month or 12, day or monthrange(year, month or 12)[1]))


def payload(item, kind):
    return {'id':item.pk, 'revision':item.revision, 'status':item.status, 'updated_at':item.updated_at,
        'values':{field:getattr(item, field) for field in KINDS[kind][2]},
        'provenance':'patient_reported', 'access_effect':'none'}


def save(user, workspace_id, kind, values, expected_revision, item_id=None):
    revision(expected_revision)
    _, model, fields = KINDS[kind]
    if not isinstance(values, dict) or set(values) != set(fields):
        raise ValueError('Unexpected care fields.')
    cleaned = {key:text(values[key], limit, key in ('title', 'name', 'role'))
        for key, limit in fields.items() if limit is not None}
    if kind == 'concerns':
        if cleaned['kind'] not in ('issue','investigation','injury','condition','episode') or cleaned['certainty'] not in ('unconfirmed','patient_reported_diagnosis'):
            raise ValueError('Choose a supported concern type and certainty.')
        cleaned['onset'] = care_date(values['onset'])
    if kind == 'assignments':
        if cleaned['participation'] not in ('current','historical'):
            raise ValueError('Choose current or historical participation.')
        cleaned['start_date'] = care_date(values['start_date'])
        cleaned['end_date'] = care_date(values['end_date'])
        start, end = date_bounds(cleaned['start_date']), date_bounds(cleaned['end_date'])
        if start and end and start[0] > end[1]:
            raise ValueError('The end date cannot be before the start date.')
    with transaction.atomic():
        workspace = authorize(user, workspace_id, lock=True)
        item = model.objects.select_for_update().filter(pk=item_id, workspace=workspace).first() if item_id else None
        if item_id and item is None:
            raise Http404
        if expected_revision != (item.revision if item else 0):
            raise services.Conflict('Care entry changed. Reload before saving.')
        if item and item.status != 'active':
            raise services.Conflict('Restore the entry before editing.')
        if kind == 'assignments':
            for key, parent in (('practitioner_id', ReportedPractitioner), ('concern_id', PatientHealthConcern)):
                selected = values[key]
                if selected is None and key == 'concern_id':
                    cleaned[key] = None
                    continue
                if not isinstance(selected, str):
                    raise ValueError('Select a saved care entry.')
                try:
                    linked = parent.objects.filter(pk=selected, workspace=workspace, status='active').first()
                except (ValueError, ValidationError):
                    raise ValueError('Invalid care entry ID.') from None
                if linked is None:
                    raise Http404
                cleaned[key] = linked.pk
            if CareTeamAssignment.objects.filter(workspace=workspace, status='active',
                practitioner_id=cleaned['practitioner_id'], concern_id=cleaned['concern_id']).exclude(pk=item.pk if item else None).exists():
                raise services.Conflict('This doctor already has an active relationship for this concern.')
        if item is None:
            if model.objects.filter(workspace=workspace).count() >= 200:
                raise services.Conflict('The 200-entry limit has been reached.')
            item = model.objects.create(workspace=workspace, updated_by=user, **cleaned)
        else:
            for key, value in cleaned.items():
                setattr(item, key, value)
            item.revision += 1; item.updated_at = timezone.now(); item.updated_by = user
            item.save(update_fields=[*cleaned, 'revision', 'updated_at', 'updated_by'])
        services.audit(user, workspace, 'care.' + KINDS[kind][0] + '.save', item)
        return item


def change_status(user, workspace_id, kind, item_id, status, expected_revision):
    revision(expected_revision)
    if status not in ('active', 'archived'):
        raise ValueError('Choose active or archived.')
    with transaction.atomic():
        workspace = authorize(user, workspace_id, lock=True)
        item = KINDS[kind][1].objects.select_for_update().filter(pk=item_id, workspace=workspace).first()
        if item is None:
            raise Http404
        if item.revision != expected_revision:
            raise services.Conflict('Care entry changed. Reload before saving.')
        if item.status != status:
            if kind == 'assignments' and status == 'active':
                if item.practitioner.status != 'active' or (item.concern_id and item.concern.status != 'active'):
                    raise services.Conflict('Restore the linked doctor and concern first.')
                if CareTeamAssignment.objects.filter(workspace=workspace, status='active', practitioner=item.practitioner,
                    concern=item.concern).exclude(pk=item.pk).exists():
                    raise services.Conflict('An active relationship already exists.')
            item.status = status; item.revision += 1; item.updated_at = timezone.now(); item.updated_by = user
            item.save(update_fields=['status', 'revision', 'updated_at', 'updated_by'])
            services.audit(user, workspace, 'care.' + KINDS[kind][0] + '.' + status, item)
        return item


def history(workspace_id, kind, item_id):
    return [{'revision':h.revision, 'created_at':h.created_at, 'snapshot':h.snapshot}
        for h in CareHistory.objects.filter(workspace_id=workspace_id,
            target_kind=KINDS[kind][0], target_id=item_id).order_by('-revision')]
