"""Cross-row identity/workspace guards and the installed capability catalogue."""
import uuid
from django.db import migrations

RULE_ID = uuid.UUID('336798aa-6464-4f83-a03e-78a7c1a89bfa')


def seed_rule(apps, schema_editor):
    apps.get_model('identity', 'CapabilityRule').objects.create(
        id=RULE_ID, authority_kind='membership',
        capability_key='read_workspace_records', scope_kind='workspace',
    )


def remove_rule(apps, schema_editor):
    apps.get_model('identity', 'CapabilityRule').objects.filter(id=RULE_ID).delete()


FORWARD = """
ALTER TABLE persons ADD CONSTRAINT person_birth_calendar CHECK (
    birth_date_precision <> 'day' OR birth_day <= CASE
        WHEN birth_month IN (4,6,9,11) THEN 30
        WHEN birth_month = 2 THEN CASE
            WHEN birth_year % 400 = 0 OR (birth_year % 4 = 0 AND birth_year % 100 <> 0)
            THEN 29 ELSE 28 END
        ELSE 31 END
);
ALTER TABLE access_capabilities ADD CONSTRAINT capability_member_workspace_fk
    FOREIGN KEY (workspace_id, membership_id)
    REFERENCES workspace_memberships(workspace_id, id) ON DELETE RESTRICT;

CREATE FUNCTION continuity_immutable_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (to_jsonb(NEW) -> TG_ARGV[0]) IS DISTINCT FROM (to_jsonb(OLD) -> TG_ARGV[0]) THEN
        RAISE EXCEPTION 'Identity binding is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER user_person_binding BEFORE UPDATE ON users FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('person_id');
CREATE TRIGGER patient_person_binding BEFORE UPDATE ON patient_profiles FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('person_id');
CREATE TRIGGER workspace_subject_binding BEFORE UPDATE ON patient_workspaces FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('subject_patient_id');
CREATE TRIGGER oidc_user_binding BEFORE UPDATE ON oidc_identities FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('user_id');
CREATE TRIGGER oidc_issuer_binding BEFORE UPDATE ON oidc_identities FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('issuer');
CREATE TRIGGER oidc_subject_binding BEFORE UPDATE ON oidc_identities FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('subject');
CREATE TRIGGER membership_user_binding BEFORE UPDATE ON workspace_memberships FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('user_id');
CREATE TRIGGER membership_workspace_binding BEFORE UPDATE ON workspace_memberships FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('workspace_id');
CREATE TRIGGER membership_relationship_binding BEFORE UPDATE ON workspace_memberships FOR EACH ROW
    EXECUTE FUNCTION continuity_immutable_binding('relationship_type');

CREATE FUNCTION continuity_self_membership() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.relationship_type = 'self' AND NOT EXISTS (
        SELECT 1 FROM users u JOIN patient_workspaces w ON w.id = NEW.workspace_id
        JOIN patient_profiles p ON p.id = w.subject_patient_id
        WHERE u.id = NEW.user_id AND u.person_id = p.person_id
    ) THEN
        RAISE EXCEPTION 'Self membership must match patient subject' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER membership_self_subject BEFORE INSERT OR UPDATE ON workspace_memberships
    FOR EACH ROW EXECUTE FUNCTION continuity_self_membership();

CREATE FUNCTION continuity_capability_bounds() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent workspace_memberships%ROWTYPE;
BEGIN
    SELECT * INTO parent FROM workspace_memberships WHERE id=NEW.membership_id FOR SHARE;
    IF NOT FOUND OR parent.workspace_id <> NEW.workspace_id OR
        parent.relationship_type NOT IN ('self', 'guardian') OR
        parent.status <> 'active' OR parent.revoked_at IS NOT NULL OR
        NEW.valid_from < parent.valid_from OR
        (parent.valid_until IS NOT NULL AND
            (NEW.valid_until IS NULL OR NEW.valid_until > parent.valid_until)) THEN
        RAISE EXCEPTION 'Capability must fit established membership authority' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER capability_authority_bounds BEFORE INSERT OR UPDATE OF
    membership_id, workspace_id, scope_workspace_id, rule_id, valid_from, valid_until ON access_capabilities
    FOR EACH ROW EXECUTE FUNCTION continuity_capability_bounds();

CREATE FUNCTION continuity_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Append-only table cannot be updated or deleted' USING ERRCODE = '23514';
END;
$$;
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
CREATE TRIGGER rules_immutable BEFORE UPDATE OR DELETE ON capability_rules
    FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
"""

REVERSE = """
DROP TRIGGER rules_immutable ON capability_rules;
DROP TRIGGER audit_append_only ON audit_events;
DROP FUNCTION continuity_append_only();
DROP TRIGGER capability_authority_bounds ON access_capabilities;
DROP FUNCTION continuity_capability_bounds();
DROP TRIGGER membership_self_subject ON workspace_memberships;
DROP FUNCTION continuity_self_membership();
DROP TRIGGER oidc_subject_binding ON oidc_identities;
DROP TRIGGER oidc_issuer_binding ON oidc_identities;
DROP TRIGGER oidc_user_binding ON oidc_identities;
DROP TRIGGER IF EXISTS membership_relationship_binding ON workspace_memberships;
DROP TRIGGER IF EXISTS membership_workspace_binding ON workspace_memberships;
DROP TRIGGER IF EXISTS membership_user_binding ON workspace_memberships;
DROP TRIGGER workspace_subject_binding ON patient_workspaces;
DROP TRIGGER patient_person_binding ON patient_profiles;
DROP TRIGGER user_person_binding ON users;
DROP FUNCTION continuity_immutable_binding();
ALTER TABLE access_capabilities DROP CONSTRAINT capability_member_workspace_fk;
ALTER TABLE persons DROP CONSTRAINT person_birth_calendar;
"""


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(FORWARD, params=None)


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(REVERSE, params=None)


class Migration(migrations.Migration):
    dependencies = [('identity', '0001_initial')]
    operations = [
        migrations.RunPython(seed_rule, remove_rule),
        migrations.RunPython(install_guards, remove_guards),
    ]
