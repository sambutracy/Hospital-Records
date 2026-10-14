from django.db import migrations

LINKS = {
    'episode_sources': {'episode': 'care_episodes', 'source_version': 'source_versions'},
    'share_grants': {'authorizing_membership': 'workspace_memberships', 'packet_revision': 'packet_revisions'},
    'provider_contribution_authorities': {'authorizing_membership': 'workspace_memberships', 'episode': 'care_episodes'},
    'clinical_contributions': {'authority': 'provider_contribution_authorities', 'accepted_source': 'source_versions'},
}
GRANT_FIELDS = ('workspace_id', 'recipient_id', 'authorizing_membership_id', 'purpose',
                'authority_basis', 'starts_at', 'expires_at', 'created_at', 'id')
BOUND = {
    'share_grants': GRANT_FIELDS + ('packet_revision_id',),
    'provider_contribution_authorities': GRANT_FIELDS + ('episode_id',),
    'clinical_contributions': ('workspace_id', 'authority_id', 'submitted_by_id', 'private_object_key',
        'sha256', 'byte_size', 'media_type', 'content_kind', 'original_filename', 'created_at', 'id'),
}

SQL = """
CREATE FUNCTION continuity_grant_history() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m workspace_memberships%ROWTYPE; a provider_contribution_authorities%ROWTYPE; v source_versions%ROWTYPE;
BEGIN
 IF TG_TABLE_NAME IN ('share_grants','provider_contribution_authorities') THEN
  IF TG_OP='INSERT' THEN
   SELECT * INTO m FROM workspace_memberships WHERE id=NEW.authorizing_membership_id;
   IF m.relationship_type IS DISTINCT FROM 'self' OR m.workspace_id IS DISTINCT FROM NEW.workspace_id OR
      NEW.recipient_id=m.user_id OR NEW.revoked_at IS NOT NULL OR
      NEW.expires_at>NEW.starts_at+INTERVAL '7 days' THEN
    RAISE EXCEPTION 'Invalid explicit patient grant' USING ERRCODE='23514';
   END IF;
   IF TG_TABLE_NAME='share_grants' THEN
    IF NOT EXISTS (SELECT 1 FROM packet_revisions WHERE id=NEW.packet_revision_id AND state='approved') THEN
     RAISE EXCEPTION 'Share requires frozen approved packet' USING ERRCODE='23514';
    END IF;
   END IF;
  ELSE
   IF OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL THEN
    RAISE EXCEPTION 'Grant revocation is terminal' USING ERRCODE='23514';
   END IF;
  END IF;
 ELSIF TG_TABLE_NAME='clinical_contributions' THEN
  SELECT * INTO a FROM provider_contribution_authorities WHERE id=NEW.authority_id;
  IF a.recipient_id IS DISTINCT FROM NEW.submitted_by_id THEN
   RAISE EXCEPTION 'Contribution must belong to intended recipient' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' THEN
   IF NEW.state<>'pending' OR a.revoked_at IS NOT NULL OR
      NOT (a.starts_at<=statement_timestamp() AND statement_timestamp()<a.expires_at) THEN
    RAISE EXCEPTION 'Submission requires active independent authority' USING ERRCODE='23514';
   END IF;
  ELSE
   IF OLD.state<>'pending' OR NEW.state NOT IN ('accepted','rejected') OR NOT EXISTS (
     SELECT 1 FROM users u JOIN patient_workspaces w ON w.id=NEW.workspace_id
     JOIN patient_profiles p ON p.id=w.subject_patient_id WHERE u.id=NEW.reviewed_by_id AND u.person_id=p.person_id) THEN
    RAISE EXCEPTION 'Only patient reviews pending contribution' USING ERRCODE='23514';
   END IF;
   IF NEW.state='accepted' THEN
    SELECT * INTO v FROM source_versions WHERE id=NEW.accepted_source_id;
    IF v.workspace_id IS DISTINCT FROM NEW.workspace_id OR v.sha256 IS DISTINCT FROM NEW.sha256 OR
       v.private_object_key IS DISTINCT FROM NEW.private_object_key OR v.submitted_by_id IS DISTINCT FROM NEW.submitted_by_id OR
       v.byte_size IS DISTINCT FROM NEW.byte_size OR v.media_type IS DISTINCT FROM NEW.media_type OR
       v.content_kind IS DISTINCT FROM NEW.content_kind OR v.original_filename IS DISTINCT FROM NEW.original_filename THEN
     RAISE EXCEPTION 'Accepted source must preserve submission provenance' USING ERRCODE='23514';
    END IF;
   END IF;
  END IF;
 END IF;
 RETURN NEW;
END; $$;
"""


def install(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    for table, links in LINKS.items():
        for field, parent in links.items():
            editor.execute(f'ALTER TABLE {table} ADD CONSTRAINT {table}_{field}_workspace_fk FOREIGN KEY (workspace_id,{field}_id) REFERENCES {parent}(workspace_id,id) ON DELETE RESTRICT')
    editor.execute(SQL, params=None)
    for table in ('care_episodes', 'episode_sources'):
        editor.execute(f'CREATE TRIGGER continuity_append BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_append_only()')
    for table, fields in BOUND.items():
        editor.execute(f'CREATE TRIGGER continuity_no_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_append_only()')
        for field in fields:
            editor.execute(f"CREATE TRIGGER continuity_bind_{field} BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_immutable_binding('{field}')")
        editor.execute(f'CREATE TRIGGER continuity_history BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_grant_history()')


def remove(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    for table in ('care_episodes', 'episode_sources'):
        editor.execute(f'DROP TRIGGER continuity_append ON {table}')
    for table, fields in BOUND.items():
        editor.execute(f'DROP TRIGGER continuity_no_delete ON {table}')
        editor.execute(f'DROP TRIGGER continuity_history ON {table}')
        for field in fields:
            editor.execute(f'DROP TRIGGER continuity_bind_{field} ON {table}')
    for table, links in LINKS.items():
        for field in links:
            editor.execute(f'ALTER TABLE {table} DROP CONSTRAINT {table}_{field}_workspace_fk')
    editor.execute('DROP FUNCTION continuity_grant_history()')


class Migration(migrations.Migration):
    dependencies = [('records', '0009_careepisode_episodesource_and_more'),
                    ('identity', '0004_remove_capabilityrule_installed_capability_rule_and_more')]
    operations = [migrations.RunPython(install, remove)]
