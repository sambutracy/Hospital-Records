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
            models.CheckConstraint(condition=Q(authority_kind='membership', capability_key__in=['read_workspace_records', 'upload_source', 'review_metadata', 'prepare_packet'], scope_kind='workspace'), name='installed_capability_rule'),
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
