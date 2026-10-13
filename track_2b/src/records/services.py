import hashlib
import uuid
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from identity.authorization import effective_capabilities
from identity.models import AuditEvent, PatientWorkspace
from .metadata import FIELDS, assertion_kwargs, assertion_value, validate_values
from .models import (ConsultationPacket, DerivedArtifact, IngestionJob, MetadataAssertion,
                     MetadataHead, PacketRevision, PacketSourceItem, SourceRecord, SourceVersion)
from .storage import object_path, read_upload, write_original
from .facilities import read_selection, validate_maps_url

UNSET_LOCATION=object()


class Conflict(Exception):
    pass


def authorize(user, workspace_id, action='read_workspace_records', lock=False):
    if not user.is_authenticated:
        raise Http404
    workspaces = PatientWorkspace.objects
    if lock:
        workspaces = workspaces.select_for_update()
    workspace = workspaces.filter(pk=workspace_id).first()
    caps = effective_capabilities(user, action).filter(workspace_id=workspace_id)
    if lock:
        caps = caps.select_related('membership').select_for_update(of=('self','membership'))
    capability = caps.first()
    if not workspace or not capability:
        AuditEvent.objects.create(actor_user=user, action='records.'+action, decision='deny', target_type='patient_workspace', target_id=workspace_id)
        raise Http404
    return workspace, capability


def audit(user, workspace, action, target):
    AuditEvent.objects.create(actor_user=user, workspace=workspace, action=action, decision='allow',
                             target_type=target._meta.db_table, target_id=target.pk)


def ingest(user, workspace_id, upload, record_id=None, content_kind='document'):
    authorize(user, workspace_id, 'upload_source')
    if content_kind not in ('document', 'medical_image'):
        raise ValueError('Choose document or medical_image.')
    data, name, media = read_upload(upload)
    if media=='application/dicom':
        content_kind='medical_image'
    if content_kind=='medical_image' and media=='application/pdf':
        raise ValueError('Use document for a report PDF.')
    checksum = hashlib.sha256(data).hexdigest()
    written = None
    try:
        with transaction.atomic():
            workspace, _ = authorize(user, workspace_id, 'upload_source', lock=True)
            authorize(user, workspace_id, lock=True)
            record = SourceRecord.objects.filter(workspace=workspace, pk=record_id).first() if record_id else None
            if record_id and record is None:
                raise Http404
            existing = SourceVersion.objects.filter(workspace=workspace, sha256=checksum).first()
            if existing:
                if existing.content_kind!=content_kind:
                    raise Conflict('These original bytes already have a different record kind. Retain their original classification.')
                if record and existing.record_id != record.pk:
                    raise Conflict('These bytes already belong to another record in this workspace.')
                audit(user, workspace, 'source.duplicate', existing)
                return existing, False
            if record is None:
                record = SourceRecord.objects.create(workspace=workspace, submitted_by=user)
            previous = record.current_version
            version_id = uuid.uuid4()
            key = f'{workspace.pk}/{version_id}'
            write_original(key, data)
            written = key
            version = SourceVersion.objects.create(id=version_id, workspace=workspace, record=record,
                version_number=previous.version_number+1 if previous else 1, supersedes=previous,
                submitted_by=user, private_object_key=key, sha256=checksum, media_type=media,
                byte_size=len(data), original_filename=name, content_kind=content_kind)
            record.current_version = version
            record.save(update_fields=['current_version'])
            MetadataHead.objects.create(workspace=workspace, source_version=version)
            IngestionJob.objects.create(workspace=workspace, source_version=version, requested_by=user)
            audit(user, workspace, 'source.upload', version)
            return version, True
    except Exception:
        if written:
            try:
                object_path(written).unlink()
            except OSError:
                pass  # Private unreferenced object; never expose or delete referenced originals.
        raise


def review(user, workspace_id, record_id, values, expected_revision, source_version_id, proposal_id=None, facility_maps_url=UNSET_LOCATION, facility_selection=UNSET_LOCATION):
    validate_values(values)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer.')
    with transaction.atomic():
        workspace, _ = authorize(user, workspace_id, 'review_metadata', lock=True)
        authorize(user, workspace_id, lock=True)
        record = SourceRecord.objects.filter(workspace=workspace, pk=record_id).first()
        if not record:
            raise Http404
        if str(record.current_version_id) != str(source_version_id):
            raise Conflict('Source version changed. Reload before reviewing.')
        head = MetadataHead.objects.select_for_update().get(source_version_id=record.current_version_id)
        if head.revision != expected_revision:
            raise Conflict('Metadata changed. Reload before reviewing.')
        location=None
        if facility_selection is not UNSET_LOCATION:
            if facility_selection is None:
                facility_maps_url=None
            else:
                location=read_selection(facility_selection,user,workspace_id)
                if location['name']!=values['facility_name']:
                    raise ValueError('The chosen hospital and facility name must match.')
                facility_maps_url=location['maps_url']
        elif facility_maps_url is UNSET_LOCATION:
            # Older API clients retain an existing pin only while its facility stays the same.
            facility_maps_url=head.facility_name.facility_maps_url if head.facility_name and assertion_value(head.facility_name)==values['facility_name'] else None
        if facility_selection is UNSET_LOCATION and head.facility_name and assertion_value(head.facility_name)==values['facility_name'] and head.facility_name.facility_maps_url==facility_maps_url:
            location=head.facility_name.facility_location
        facility_maps_url=validate_maps_url(facility_maps_url)
        if facility_maps_url and not values['facility_name']:
            raise ValueError('A facility name is required for its pin.')
        proposal = None
        if proposal_id:
            proposal = DerivedArtifact.objects.filter(workspace=workspace, pk=proposal_id,
                source_version_id=record.current_version_id).first()
            if not proposal:
                raise Http404
        for field in FIELDS:
            old = getattr(head, field)
            evidence = proposal if proposal and proposal.payload[field] == values[field] else None
            assertion = MetadataAssertion.objects.create(workspace=workspace,
                source_version_id=record.current_version_id, field_name=field,
                origin='patient', review_state='confirmed', asserted_by=user, supersedes=old,
                evidence_artifact=evidence, locator=evidence.payload['evidence'][field] or {} if evidence else {},
                facility_maps_url=facility_maps_url if field=='facility_name' else None,
                facility_location=location if field=='facility_name' else None,
                **assertion_kwargs(field, values[field]))
            setattr(head, field, assertion)
        head.revision += 1
        head.save(update_fields=[*FIELDS, 'revision'])
        audit(user, workspace, 'metadata.review', head)
        return head


def retry_job(user, workspace_id, job_id):
    with transaction.atomic():
        workspace, _ = authorize(user, workspace_id, 'upload_source', lock=True)
        authorize(user, workspace_id, lock=True)
        job = IngestionJob.objects.select_for_update().filter(pk=job_id, workspace=workspace).first()
        if not job:
            raise Http404
        latest = IngestionJob.objects.filter(source_version=job.source_version).order_by('-attempt_number').first()
        if latest.pk != job.pk or job.state not in ('failed','waiting_model'):
            raise Conflict('Only the latest failed or waiting job can be retried.')
        if job.attempt_number >= 5:
            raise Conflict('The five-attempt limit has been reached.')
        if job.state=='waiting_model':
            job.state='failed'
            job.safe_error_code='explicit_retry'
            job.finished_at=timezone.now()
            job.save(update_fields=['state','safe_error_code','finished_at'])
        new = IngestionJob.objects.create(workspace=workspace, source_version=job.source_version,
            requested_by=user, attempt_number=job.attempt_number+1)
        audit(user, workspace, 'ingestion.retry', new)
        return new


def create_packet(user, workspace_id, purpose, version_ids):
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose)>180:
        raise ValueError('Provide a purpose up to 180 characters.')
    if not isinstance(version_ids, list) or not 1 <= len(version_ids) <= 30:
        raise ValueError('Select between one and 30 source versions.')
    try:
        ids = [uuid.UUID(str(value)) for value in version_ids]
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid source version IDs.') from None
    if len(set(ids)) != len(ids):
        raise ValueError('Source selection contains duplicates.')
    with transaction.atomic():
        workspace, cap = authorize(user, workspace_id, 'prepare_packet', lock=True)
        authorize(user, workspace_id, lock=True)
        versions = list(SourceVersion.objects.filter(workspace=workspace, id__in=ids))
        if len(versions) != len(ids):
            raise Http404
        packet = ConsultationPacket.objects.create(workspace=workspace, purpose=purpose.strip(), created_by=user)
        revision = PacketRevision.objects.create(workspace=workspace, packet=packet)
        for version in versions:
            head = MetadataHead.objects.get(source_version=version)
            PacketSourceItem.objects.create(workspace=workspace, revision=revision,
                source_version=version, **{field:getattr(head,field) for field in FIELDS})
        revision.state='approved'
        revision.approved_by=cap.membership
        revision.approved_at=timezone.now()
        revision.save(update_fields=['state','approved_by','approved_at'])
        audit(user, workspace, 'packet.approve', packet)
        return packet


def head_payload(head):
    return {'revision': head.revision,
            'facility_maps_url':head.facility_name.facility_maps_url if head.facility_name else None,
            'facility_location':head.facility_name.facility_location if head.facility_name else None,
            'values': {field:assertion_value(getattr(head,field)) for field in FIELDS},
            'assertion_ids': {field:getattr(head,field+'_id') for field in FIELDS},
            'verification': 'patient-confirmed, not clinician-verified'}
