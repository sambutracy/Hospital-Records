"""Immutable originals and provenance; only heads and in-progress jobs are mutable."""
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from identity.models import UUIDModel, PatientWorkspace, WorkspaceMembership
from .facilities import MAPS_URL_PATTERN


class WorkspaceModel(UUIDModel):
    workspace = models.ForeignKey(PatientWorkspace, on_delete=models.PROTECT)
    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=['workspace', 'id'], name='%(class)s_workspace_id')]


class FacilitySearchCache(models.Model):
    key = models.CharField(max_length=64,primary_key=True)
    results = models.JSONField()
    expires_at = models.DateTimeField()
    class Meta:
        db_table='facility_search_cache'


class FacilitySearchGate(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True,default=1)
    next_allowed_at = models.DateTimeField()
    class Meta:
        db_table='facility_search_gate'


class SourceRecord(WorkspaceModel):
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    current_version = models.ForeignKey('SourceVersion', null=True, on_delete=models.PROTECT, related_name='+')
    class Meta(WorkspaceModel.Meta):
        db_table = 'source_records'


class SourceVersion(WorkspaceModel):
    record = models.ForeignKey(SourceRecord, on_delete=models.PROTECT, related_name='versions')
    version_number = models.PositiveIntegerField()
    supersedes = models.ForeignKey('self', null=True, on_delete=models.PROTECT, related_name='+')
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    private_object_key = models.CharField(max_length=128, unique=True)
    sha256 = models.CharField(max_length=64)
    media_type = models.CharField(max_length=32)
    content_kind = models.CharField(max_length=16, default='document')
    byte_size = models.PositiveIntegerField()
    original_filename = models.CharField(max_length=180)
    class Meta(WorkspaceModel.Meta):
        db_table = 'source_versions'
        constraints = WorkspaceModel.Meta.constraints + [
            models.UniqueConstraint(fields=['record', 'version_number'], name='source_version_number'),
            models.UniqueConstraint(fields=['workspace', 'sha256'], name='workspace_source_checksum'),
            models.CheckConstraint(condition=Q(version_number__gt=0, byte_size__gt=0, byte_size__lte=10485760), name='source_size_version'),
            models.CheckConstraint(condition=Q(media_type__in=['application/pdf', 'image/jpeg', 'image/png', 'application/dicom']), name='source_media_type'),
            models.CheckConstraint(condition=Q(content_kind__in=['document', 'medical_image']) & (~Q(media_type='application/dicom') | Q(content_kind='medical_image')), name='source_content_kind'),
            models.CheckConstraint(condition=Q(sha256__regex=r'^[0-9a-f]{64}$'), name='source_checksum_shape'),
        ]


class IngestionJob(WorkspaceModel):
    source_version = models.ForeignKey(SourceVersion, on_delete=models.PROTECT, related_name='jobs')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    attempt_number = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=24, default='queued')
    safe_error_code = models.CharField(max_length=40, blank=True)
    lease_token = models.UUIDField(null=True)
    lease_expires_at = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    class Meta(WorkspaceModel.Meta):
        db_table = 'ingestion_jobs'
        constraints = WorkspaceModel.Meta.constraints + [
            models.UniqueConstraint(fields=['source_version', 'attempt_number'], name='ingestion_attempt'),
            models.UniqueConstraint(fields=['source_version'], condition=Q(state__in=['queued', 'processing', 'waiting_model']), name='one_active_ingestion'),
            models.CheckConstraint(condition=Q(attempt_number__gt=0, state__in=['queued', 'processing', 'waiting_model', 'needs_ocr', 'failed', 'review_ready', 'manual_review']), name='ingestion_state'),
        ]
        indexes = [models.Index(fields=['state', 'created_at'], name='ingestion_queue')]


class TextExtraction(WorkspaceModel):
    source_version = models.OneToOneField(SourceVersion, on_delete=models.PROTECT, related_name='extraction')
    pages = models.JSONField()
    extractor_version = models.CharField(max_length=64)
    text_sha256 = models.CharField(max_length=64)
    class Meta(WorkspaceModel.Meta):
        db_table = 'text_extractions'


class ImageInspection(WorkspaceModel):
    """Source-derived technical facts and an optional non-diagnostic raster preview."""
    source_version = models.OneToOneField(SourceVersion, on_delete=models.PROTECT, related_name='image_inspection')
    inspector_version = models.CharField(max_length=64)
    details = models.JSONField()
    preview_png = models.BinaryField(null=True, editable=False)
    preview_sha256 = models.CharField(max_length=64, null=True)
    class Meta(WorkspaceModel.Meta):
        db_table = 'image_inspections'
        constraints = WorkspaceModel.Meta.constraints + [
            models.CheckConstraint(condition=Q(preview_png__isnull=True, preview_sha256__isnull=True) | Q(preview_png__isnull=False, preview_sha256__regex=r'^[0-9a-f]{64}$', preview_sha256__isnull=False), name='image_preview_integrity'),
        ]


class GenerationRun(WorkspaceModel):
    job = models.OneToOneField(IngestionJob, on_delete=models.PROTECT, related_name='generation')
    source_version = models.ForeignKey(SourceVersion, on_delete=models.PROTECT)
    model_name = models.CharField(max_length=160)
    prompt_version = models.CharField(max_length=64)
    configuration = models.JSONField()
    state = models.CharField(max_length=16, default='processing')
    finished_at = models.DateTimeField(null=True)
    latency_seconds = models.FloatField(null=True)
    usage = models.JSONField(default=dict)
    class Meta(WorkspaceModel.Meta):
        db_table = 'generation_runs'
        constraints = WorkspaceModel.Meta.constraints + [models.CheckConstraint(condition=Q(state__in=['processing', 'completed', 'failed']), name='generation_state')]


class DerivedArtifact(WorkspaceModel):
    source_version = models.ForeignKey(SourceVersion, on_delete=models.PROTECT)
    extraction = models.ForeignKey(TextExtraction, on_delete=models.PROTECT)
    generation = models.OneToOneField(GenerationRun, on_delete=models.PROTECT, related_name='artifact')
    payload = models.JSONField()
    class Meta(WorkspaceModel.Meta):
        db_table = 'derived_artifacts'


def date_shape():
    return (Q(date_precision='unknown', value_year__isnull=True, value_month__isnull=True, value_day__isnull=True)
        | Q(date_precision='year', value_year__isnull=False, value_year__gte=1, value_year__lte=9999, value_month__isnull=True, value_day__isnull=True)
        | Q(date_precision='month', value_year__isnull=False, value_year__gte=1, value_year__lte=9999, value_month__isnull=False, value_month__gte=1, value_month__lte=12, value_day__isnull=True)
        | Q(date_precision='day', value_year__isnull=False, value_year__gte=1, value_year__lte=9999, value_month__isnull=False, value_month__gte=1, value_month__lte=12, value_day__isnull=False, value_day__gte=1, value_day__lte=31))


class MetadataAssertion(WorkspaceModel):
    source_version = models.ForeignKey(SourceVersion, on_delete=models.PROTECT, related_name='assertions')
    field_name = models.CharField(max_length=32)
    value_type = models.CharField(max_length=24)
    value_text = models.CharField(max_length=180, null=True)
    facility_maps_url = models.CharField(max_length=2048, null=True)
    facility_location = models.JSONField(null=True)
    value_year = models.SmallIntegerField(null=True)
    value_month = models.SmallIntegerField(null=True)
    value_day = models.SmallIntegerField(null=True)
    date_precision = models.CharField(max_length=8, null=True)
    origin = models.CharField(max_length=16)
    review_state = models.CharField(max_length=16)
    asserted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    evidence_artifact = models.ForeignKey(DerivedArtifact, null=True, on_delete=models.PROTECT)
    locator = models.JSONField(default=dict)
    supersedes = models.ForeignKey('self', null=True, on_delete=models.PROTECT, related_name='+')
    class Meta(WorkspaceModel.Meta):
        db_table = 'metadata_assertions'
        constraints = WorkspaceModel.Meta.constraints + [
            models.UniqueConstraint(fields=['supersedes'], name='assertion_single_successor'),
            models.CheckConstraint(condition=Q(field_name__in=['document_type', 'document_date', 'facility_name']), name='metadata_field'),
            models.CheckConstraint(condition=Q(facility_maps_url__isnull=True) | Q(field_name='facility_name',origin='patient',value_type='text',facility_maps_url__regex=MAPS_URL_PATTERN),name='facility_maps_patient_only'),
            models.CheckConstraint(condition=Q(facility_location__isnull=True) | Q(field_name='facility_name',origin='patient',facility_maps_url__isnull=False),name='facility_selection_patient_only'),
            models.CheckConstraint(condition=(Q(origin='ai', review_state='proposed', asserted_by__isnull=True, evidence_artifact__isnull=False) | Q(origin='patient', review_state='confirmed', asserted_by__isnull=False)), name='metadata_origin_review'),
            models.CheckConstraint(condition=(
                Q(field_name='document_date', value_type='date_components', value_text__isnull=True) & date_shape()
                | (Q(field_name__in=['document_type', 'facility_name'], value_type='text', value_text__isnull=False, date_precision__isnull=True, value_year__isnull=True, value_month__isnull=True, value_day__isnull=True))
                | Q(field_name='facility_name', value_type='unknown', value_text__isnull=True, date_precision__isnull=True, value_year__isnull=True, value_month__isnull=True, value_day__isnull=True)
            ), name='metadata_typed_value'),
        ]


class MetadataHead(WorkspaceModel):
    source_version = models.OneToOneField(SourceVersion, on_delete=models.PROTECT, related_name='metadata_head')
    revision = models.PositiveIntegerField(default=0)
    document_type = models.ForeignKey(MetadataAssertion, null=True, on_delete=models.PROTECT, related_name='+')
    document_date = models.ForeignKey(MetadataAssertion, null=True, on_delete=models.PROTECT, related_name='+')
    facility_name = models.ForeignKey(MetadataAssertion, null=True, on_delete=models.PROTECT, related_name='+')
    class Meta(WorkspaceModel.Meta):
        db_table = 'metadata_heads'


class ConsultationPacket(WorkspaceModel):
    purpose = models.CharField(max_length=180)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    class Meta(WorkspaceModel.Meta):
        db_table = 'consultation_packets'


class PacketRevision(WorkspaceModel):
    packet = models.ForeignKey(ConsultationPacket, on_delete=models.PROTECT, related_name='revisions')
    revision_number = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=16, default='draft')
    approved_by = models.ForeignKey(WorkspaceMembership, null=True, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(null=True)
    class Meta(WorkspaceModel.Meta):
        db_table = 'packet_revisions'
        constraints = WorkspaceModel.Meta.constraints + [
            models.UniqueConstraint(fields=['packet', 'revision_number'], name='packet_revision_number'),
            models.CheckConstraint(condition=Q(state='draft', approved_by__isnull=True, approved_at__isnull=True) | Q(state='approved', approved_by__isnull=False, approved_at__isnull=False), name='packet_approval'),
        ]


class PacketSourceItem(WorkspaceModel):
    revision = models.ForeignKey(PacketRevision, on_delete=models.PROTECT, related_name='items')
    source_version = models.ForeignKey(SourceVersion, on_delete=models.PROTECT)
    document_type = models.ForeignKey(MetadataAssertion, null=True, on_delete=models.PROTECT, related_name='+')
    document_date = models.ForeignKey(MetadataAssertion, null=True, on_delete=models.PROTECT, related_name='+')
    facility_name = models.ForeignKey(MetadataAssertion, null=True, on_delete=models.PROTECT, related_name='+')
    class Meta(WorkspaceModel.Meta):
        db_table = 'packet_source_items'
        constraints = WorkspaceModel.Meta.constraints + [models.UniqueConstraint(fields=['revision', 'source_version'], name='packet_unique_source')]


class AssistantTask(WorkspaceModel):
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=24)
    parameters = models.JSONField()
    coverage = models.JSONField(default=dict)
    packet_revision = models.ForeignKey(PacketRevision, null=True, on_delete=models.PROTECT)
    state = models.CharField(max_length=16, default='queued')
    safe_error_code = models.CharField(max_length=40, blank=True)
    lease_token = models.UUIDField(null=True)
    lease_expires_at = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    model_name = models.CharField(max_length=160, blank=True)
    prompt_version = models.CharField(max_length=64, blank=True)
    configuration = models.JSONField(default=dict)
    result = models.JSONField(null=True)
    latency_seconds = models.FloatField(null=True)
    usage = models.JSONField(default=dict)
    class Meta(WorkspaceModel.Meta):
        db_table = 'assistant_tasks'
        constraints = WorkspaceModel.Meta.constraints + [
            models.CheckConstraint(condition=Q(kind__in=['search','packet_overview','explain_term']), name='assistant_kind'),
            models.CheckConstraint(condition=Q(state__in=['queued','processing','waiting_model','completed','failed']), name='assistant_state'),
            models.CheckConstraint(condition=Q(kind='packet_overview',packet_revision__isnull=False) | (~Q(kind='packet_overview') & Q(packet_revision__isnull=True)), name='assistant_packet_scope'),
            models.CheckConstraint(condition=Q(state='completed',result__isnull=False) | (~Q(state='completed') & Q(result__isnull=True)), name='assistant_result_state'),
            models.UniqueConstraint(fields=['workspace','requested_by','kind'], condition=Q(state__in=['queued','processing','waiting_model']), name='one_active_assistant_kind'),
        ]
        indexes = [models.Index(fields=['state','created_at'], name='assistant_queue')]


class AssistantSource(WorkspaceModel):
    task = models.ForeignKey(AssistantTask, on_delete=models.PROTECT, related_name='sources')
    source_version = models.ForeignKey(SourceVersion, on_delete=models.PROTECT)
    extraction = models.ForeignKey(TextExtraction, null=True, on_delete=models.PROTECT)
    source_label = models.CharField(max_length=16)
    metadata_revision = models.PositiveIntegerField()
    chunks = models.JSONField()
    snapshot_sha256 = models.CharField(max_length=64)
    class Meta(WorkspaceModel.Meta):
        db_table = 'assistant_sources'
        constraints = WorkspaceModel.Meta.constraints + [
            models.UniqueConstraint(fields=['task','source_version'], name='assistant_source_once'),
            models.UniqueConstraint(fields=['task','source_label'], name='assistant_label_once'),
            models.CheckConstraint(condition=Q(snapshot_sha256__regex=r'^[0-9a-f]{64}$'), name='assistant_snapshot_shape'),
        ]


class CareEpisode(WorkspaceModel):
    """Patient-created grouping; no inferred diagnosis or appointment lifecycle."""
    title = models.CharField(max_length=180)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    class Meta(WorkspaceModel.Meta):
        db_table = 'care_episodes'


class EpisodeSource(WorkspaceModel):
    episode = models.ForeignKey(CareEpisode, on_delete=models.PROTECT, related_name='sources')
    source_version = models.ForeignKey(SourceVersion, on_delete=models.PROTECT)
    linked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    class Meta(WorkspaceModel.Meta):
        db_table = 'episode_sources'
        constraints = WorkspaceModel.Meta.constraints + [
            models.UniqueConstraint(fields=['episode', 'source_version'], name='episode_source_once')]


class PatientGrant(WorkspaceModel):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    authorizing_membership = models.ForeignKey(WorkspaceMembership, on_delete=models.PROTECT)
    purpose = models.CharField(max_length=180)
    authority_basis = models.CharField(max_length=40, default='patient_explicit_approval')
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)
    class Meta(WorkspaceModel.Meta):
        abstract = True
        constraints = WorkspaceModel.Meta.constraints + [
            models.CheckConstraint(condition=Q(expires_at__gt=F('starts_at')), name='%(class)s_interval'),
            models.CheckConstraint(condition=Q(authority_basis='patient_explicit_approval'), name='%(class)s_basis')]


class ShareGrant(PatientGrant):
    """Immutable approved packet is the exact read scope, never a write parent."""
    packet_revision = models.ForeignKey(PacketRevision, on_delete=models.PROTECT)
    class Meta(PatientGrant.Meta):
        abstract = False
        db_table = 'share_grants'
        indexes = [models.Index(fields=['recipient', 'expires_at'], name='share_recipient_expiry')]


class ProviderContributionAuthority(PatientGrant):
    episode = models.ForeignKey(CareEpisode, on_delete=models.PROTECT)
    class Meta(PatientGrant.Meta):
        abstract = False
        db_table = 'provider_contribution_authorities'
        indexes = [models.Index(fields=['recipient', 'expires_at'], name='contribution_recipient_expiry')]


class ClinicalContribution(WorkspaceModel):
    """Private immutable submission bytes; not an accepted source until reviewed."""
    authority = models.ForeignKey(ProviderContributionAuthority, on_delete=models.PROTECT, related_name='submissions')
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    private_object_key = models.CharField(max_length=128, unique=True)
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveIntegerField()
    media_type = models.CharField(max_length=32)
    content_kind = models.CharField(max_length=16)
    original_filename = models.CharField(max_length=180)
    state = models.CharField(max_length=16, default='pending')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+')
    reviewed_at = models.DateTimeField(null=True)
    accepted_source = models.OneToOneField(SourceVersion, null=True, on_delete=models.PROTECT)
    class Meta(WorkspaceModel.Meta):
        db_table = 'clinical_contributions'
        constraints = WorkspaceModel.Meta.constraints + [
            models.UniqueConstraint(fields=['authority', 'sha256'], name='contribution_duplicate'),
            models.CheckConstraint(condition=Q(sha256__regex=r'^[0-9a-f]{64}$'), name='contribution_checksum'),
            models.CheckConstraint(condition=Q(byte_size__gt=0, byte_size__lte=10485760), name='contribution_size'),
            models.CheckConstraint(condition=Q(media_type__in=['application/pdf', 'image/jpeg', 'image/png', 'application/dicom']), name='contribution_media'),
            models.CheckConstraint(condition=Q(content_kind__in=['document', 'medical_image']) & (~Q(media_type='application/dicom') | Q(content_kind='medical_image')), name='contribution_kind'),
            models.CheckConstraint(condition=(
                Q(state='pending', reviewed_by__isnull=True, reviewed_at__isnull=True, accepted_source__isnull=True)
                | Q(state='accepted', reviewed_by__isnull=False, reviewed_at__isnull=False, accepted_source__isnull=False)
                | Q(state='rejected', reviewed_by__isnull=False, reviewed_at__isnull=False, accepted_source__isnull=True)
            ), name='contribution_review_state')]


class MedicationEntry(WorkspaceModel):
    """Patient-reported medication at a visit; no inferred prescription or dose."""
    medicine_name = models.CharField(max_length=160)
    dose = models.CharField(max_length=120, blank=True)
    frequency = models.CharField(max_length=120, blank=True)
    route = models.CharField(max_length=64, blank=True)
    instructions = models.CharField(max_length=500, blank=True)
    use_status = models.CharField(max_length=24, default='unknown')
    date_precision = models.CharField(max_length=8, default='unknown')
    value_year = models.SmallIntegerField(null=True)
    value_month = models.SmallIntegerField(null=True)
    value_day = models.SmallIntegerField(null=True)
    episode = models.ForeignKey(CareEpisode, null=True, on_delete=models.PROTECT)
    source_version = models.ForeignKey(SourceVersion, null=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default='active')
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    class Meta(WorkspaceModel.Meta):
        db_table = 'medication_entries'
        constraints = WorkspaceModel.Meta.constraints + [
            models.CheckConstraint(condition=Q(use_status__in=['reported_taken','reported_prescribed','not_taken','unknown']), name='medication_use_status'),
            models.CheckConstraint(condition=date_shape(), name='medication_date_shape'),
            models.CheckConstraint(condition=Q(status__in=['active','archived']), name='medication_status'),
            models.CheckConstraint(condition=Q(revision__gt=0) & ~Q(medicine_name=''), name='medication_revision_name')]
