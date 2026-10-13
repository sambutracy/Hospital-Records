import uuid
from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone

ACTIONS = ('upload_source', 'review_metadata', 'prepare_packet')


def seed(apps, editor):
    Rule = apps.get_model('identity', 'CapabilityRule')
    Capability = apps.get_model('identity', 'AccessCapability')
    now = timezone.now()
    for action in ACTIONS:
        rule = Rule.objects.create(id=uuid.uuid5(uuid.NAMESPACE_URL, 'continuity/' + action),
                                   authority_kind='membership', capability_key=action, scope_kind='workspace')
        for read in Capability.objects.filter(rule__capability_key='read_workspace_records',
                revoked_at__isnull=True, membership__relationship_type='self',
                membership__status='active', membership__revoked_at__isnull=True,
                valid_from__lte=now, membership__valid_from__lte=now).select_related('membership'):
            if (read.valid_until and read.valid_until <= now) or (read.membership.valid_until and read.membership.valid_until <= now):
                continue
            untils = [v for v in (read.valid_until, read.membership.valid_until) if v]
            Capability.objects.create(workspace_id=read.workspace_id, membership_id=read.membership_id,
                scope_workspace_id=read.scope_workspace_id, rule=rule,
                valid_from=max(read.valid_from, read.membership.valid_from),
                valid_until=min(untils) if untils else None)


def unseed(apps, editor):
    Rule = apps.get_model('identity', 'CapabilityRule')
    apps.get_model('identity', 'AccessCapability').objects.filter(rule__capability_key__in=ACTIONS).delete()
    if editor.connection.vendor == 'postgresql':
        editor.execute('ALTER TABLE capability_rules DISABLE TRIGGER rules_immutable')
    Rule.objects.filter(capability_key__in=ACTIONS).delete()
    if editor.connection.vendor == 'postgresql':
        editor.execute('ALTER TABLE capability_rules ENABLE TRIGGER rules_immutable')


class Migration(migrations.Migration):
    dependencies = [('identity', '0002_postgresql_guards')]
    operations = [
        migrations.RemoveConstraint('capabilityrule', 'installed_capability_rule'),
        migrations.AddConstraint('capabilityrule', models.CheckConstraint(
            condition=Q(authority_kind='membership', capability_key__in=['read_workspace_records', *ACTIONS], scope_kind='workspace'),
            name='installed_capability_rule')),
        migrations.RunPython(seed, unseed),
    ]
