"""Patient subject, actor identity and the first explicit capability slice."""
import uuid
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    class Meta:
        abstract = True


class Person(UUIDModel):
    display_name = models.CharField(max_length=160)
    status = models.CharField(max_length=16, default='active')
    birth_year = models.SmallIntegerField(null=True, blank=True)
    birth_month = models.SmallIntegerField(null=True, blank=True)
    birth_day = models.SmallIntegerField(null=True, blank=True)
    birth_date_precision = models.CharField(max_length=8, default='unknown')
    class Meta:
        db_table = 'persons'
        constraints = [
            models.CheckConstraint(condition=Q(status__in=['active', 'disabled']), name='person_status'),
            models.CheckConstraint(condition=(
                Q(birth_date_precision='unknown', birth_year__isnull=True, birth_month__isnull=True, birth_day__isnull=True)
                | (Q(birth_date_precision='year', birth_year__isnull=False, birth_year__gte=1, birth_year__lte=9999,
                     birth_month__isnull=True, birth_day__isnull=True))
                | (Q(birth_date_precision='month', birth_year__isnull=False, birth_year__gte=1, birth_year__lte=9999,
                     birth_month__isnull=False, birth_month__gte=1, birth_month__lte=12, birth_day__isnull=True))
                | (Q(birth_date_precision='day', birth_year__isnull=False, birth_year__gte=1, birth_year__lte=9999,
                     birth_month__isnull=False, birth_month__gte=1, birth_month__lte=12,
                     birth_day__isnull=False, birth_day__gte=1, birth_day__lte=31))
            ), name='person_birth_components'),
        ]


class UserManager(BaseUserManager):
    def create_user(self, person, **extra):
        user = self.model(person=person, **extra)
        user.set_unusable_password()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, UUIDModel):
    person = models.OneToOneField(Person, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)
    USERNAME_FIELD = 'id'
    objects = UserManager()
    class Meta:
        db_table = 'users'


class OIDCIdentity(UUIDModel):
    issuer = models.CharField(max_length=512)
    subject = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='oidc_identities')
    class Meta:
        db_table = 'oidc_identities'
        constraints = [
            models.UniqueConstraint(fields=['issuer', 'subject'], name='oidc_issuer_subject'),
            models.CheckConstraint(condition=~Q(issuer='') & ~Q(subject=''), name='oidc_nonempty_identity'),
        ]


class PatientProfile(UUIDModel):
    person = models.OneToOneField(Person, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default='active')
    class Meta:
        db_table = 'patient_profiles'
        constraints = [models.CheckConstraint(condition=Q(status__in=['active', 'disabled']), name='patient_status')]


class PatientWorkspace(UUIDModel):
    subject_patient = models.OneToOneField(PatientProfile, on_delete=models.PROTECT, related_name='workspace')
    status = models.CharField(max_length=16, default='active')
    class Meta:
        db_table = 'patient_workspaces'
        constraints = [models.CheckConstraint(condition=Q(status__in=['active', 'disabled']), name='workspace_status')]


class WorkspaceMembership(UUIDModel):
    workspace = models.ForeignKey(PatientWorkspace, on_delete=models.PROTECT, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='workspace_memberships')
    relationship_type = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default='active')
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    authority_basis = models.CharField(max_length=32)
    authority_reference = models.TextField(blank=True)
    class Meta:
        db_table = 'workspace_memberships'
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'id'], name='membership_workspace_id'),
            models.UniqueConstraint(fields=['workspace', 'user', 'relationship_type'], condition=Q(status='active'), name='membership_active_relationship'),
            models.CheckConstraint(condition=Q(status__in=['active', 'suspended', 'revoked']), name='membership_status'),
            models.CheckConstraint(condition=Q(valid_until__isnull=True) | Q(valid_until__gt=F('valid_from')), name='membership_interval'),
            models.CheckConstraint(condition=(
                Q(relationship_type='self', authority_basis='oidc_new_subject')
                | (Q(relationship_type='guardian', authority_basis='verified_guardianship') & ~Q(authority_reference=''))
                | Q(relationship_type__in=['caregiver', 'delegate'], authority_basis='relationship_only')
            ), name='membership_authority_basis'),
        ]
        indexes = [models.Index(fields=['workspace', 'user', 'status'], name='membership_actor_status')]


class CapabilityRule(UUIDModel):
    authority_kind = models.CharField(max_length=32)
    capability_key = models.CharField(max_length=64)
    scope_kind = models.CharField(max_length=16)
    class Meta:
        db_table = 'capability_rules'
        constraints = [
            models.UniqueConstraint(fields=['authority_kind', 'capability_key', 'scope_kind'], name='capability_combination'),
            models.CheckConstraint(condition=Q(authority_kind='membership', capability_key__in=['read_workspace_records', 'upload_source', 'review_metadata', 'prepare_packet', 'manage_episode_links', 'create_share', 'revoke_share', 'review_contribution', 'authorize_provider_contribution', 'manage_profile', 'manage_medications'], scope_kind='workspace'), name='installed_capability_rule'),
        ]


class AccessCapability(UUIDModel):
    workspace = models.ForeignKey(PatientWorkspace, on_delete=models.PROTECT)
    membership = models.ForeignKey(WorkspaceMembership, on_delete=models.PROTECT, related_name='capabilities')
    rule = models.ForeignKey(CapabilityRule, on_delete=models.PROTECT)
    scope_workspace = models.ForeignKey(PatientWorkspace, on_delete=models.PROTECT, related_name='+')
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        db_table = 'access_capabilities'
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'id'], name='capability_workspace_id'),
            models.UniqueConstraint(fields=['membership', 'rule', 'scope_workspace'], name='membership_scoped_capability'),
            models.CheckConstraint(condition=Q(workspace=F('scope_workspace')), name='capability_workspace_scope'),
            models.CheckConstraint(condition=Q(valid_until__isnull=True) | Q(valid_until__gt=F('valid_from')), name='capability_interval'),
        ]
        indexes = [models.Index(fields=['workspace', 'membership'], name='capability_workspace_member')]


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(PatientWorkspace, null=True, on_delete=models.PROTECT)
    actor_user = models.ForeignKey(User, null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=64)
    decision = models.CharField(max_length=8)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.UUIDField(null=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    class Meta:
        db_table = 'audit_events'
        constraints = [models.CheckConstraint(condition=Q(decision__in=['allow', 'deny']), name='audit_decision')]
        indexes = [
            models.Index(fields=['workspace', 'occurred_at'], name='audit_workspace_time'),
            models.Index(fields=['actor_user', 'occurred_at'], name='audit_actor_time'),
        ]


BLOOD_GROUPS = ('unknown', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')
CONTACT_RELATIONSHIPS = ('relative', 'parent', 'child', 'sibling', 'spouse_partner', 'friend',
                         'caregiver', 'guardian', 'clinician', 'other')
IDENTIFIER_TYPES = ('none', 'national_id', 'passport', 'hospital_id', 'other')


class PatientPersonalDetails(UUIDModel):
    workspace = models.OneToOneField(PatientWorkspace, on_delete=models.PROTECT, related_name='personal_details')
    full_name = models.CharField(max_length=160, blank=True)
    preferred_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=500, blank=True)
    gender = models.CharField(max_length=60, blank=True)
    identifier_type = models.CharField(max_length=16, default='none')
    identifier_number = models.CharField(max_length=80, blank=True)
    identifier_issuer = models.CharField(max_length=80, blank=True)
    blood_group = models.CharField(max_length=8, default='unknown')
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(default=timezone.now)
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT)
    class Meta:
        db_table = 'patient_personal_details'
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'id'], name='personal_details_workspace_id'),
            models.CheckConstraint(condition=Q(blood_group__in=BLOOD_GROUPS), name='personal_blood_group'),
            models.CheckConstraint(condition=Q(identifier_type__in=IDENTIFIER_TYPES), name='personal_identifier_type'),
            models.CheckConstraint(condition=Q(identifier_type='none',identifier_number='',identifier_issuer='') | (~Q(identifier_type='none') & ~Q(identifier_number='')), name='personal_identifier_value'),
            models.CheckConstraint(condition=Q(revision__gt=0), name='personal_revision')]


class CareCircleEntry(UUIDModel):
    workspace = models.ForeignKey(PatientWorkspace, on_delete=models.PROTECT, related_name='care_circle')
    full_name = models.CharField(max_length=160)
    relationship = models.CharField(max_length=32, default='relative')
    email = models.EmailField(max_length=254, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    is_next_of_kin = models.BooleanField(default=False)
    is_emergency_contact = models.BooleanField(default=False)
    recipient_user = models.ForeignKey(User, null=True, on_delete=models.PROTECT, related_name='+')
    status = models.CharField(max_length=16, default='active')
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(default=timezone.now)
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+')
    class Meta:
        db_table = 'care_circle_entries'
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'id'], name='circle_workspace_id'),
            models.UniqueConstraint(fields=['workspace', 'recipient_user'], condition=Q(status='active',recipient_user__isnull=False), name='circle_active_account_once'),
            models.CheckConstraint(condition=Q(relationship__in=CONTACT_RELATIONSHIPS), name='circle_relationship'),
            models.CheckConstraint(condition=Q(status__in=['active','archived']), name='circle_status'),
            models.CheckConstraint(condition=Q(revision__gt=0) & ~Q(full_name=''), name='circle_revision_name')]
