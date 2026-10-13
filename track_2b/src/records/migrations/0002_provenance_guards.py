from django.db import migrations

PARENTS = {
    'source_versions': {'record': 'source_records', 'supersedes': 'source_versions'},
    'source_records': {'current_version': 'source_versions'},
    'ingestion_jobs': {'source_version': 'source_versions'},
    'text_extractions': {'source_version': 'source_versions'},
    'generation_runs': {'job': 'ingestion_jobs', 'source_version': 'source_versions'},
    'derived_artifacts': {'source_version': 'source_versions', 'extraction': 'text_extractions', 'generation': 'generation_runs'},
    'metadata_assertions': {'source_version': 'source_versions', 'evidence_artifact': 'derived_artifacts', 'supersedes': 'metadata_assertions'},
    'metadata_heads': {'source_version': 'source_versions', 'document_type': 'metadata_assertions', 'document_date': 'metadata_assertions', 'facility_name': 'metadata_assertions'},
    'packet_revisions': {'packet': 'consultation_packets', 'approved_by': 'workspace_memberships'},
    'packet_source_items': {'revision': 'packet_revisions', 'source_version': 'source_versions', 'document_type': 'metadata_assertions', 'document_date': 'metadata_assertions', 'facility_name': 'metadata_assertions'},
}
IMMUTABLE = ('source_versions', 'text_extractions', 'derived_artifacts', 'metadata_assertions', 'consultation_packets')
BOUND = {
    'source_records': ('workspace_id', 'submitted_by_id', 'created_at'),
    'ingestion_jobs': ('workspace_id', 'source_version_id', 'requested_by_id', 'attempt_number'),
    'metadata_heads': ('workspace_id', 'source_version_id'),
    'generation_runs': ('workspace_id', 'source_version_id', 'job_id', 'model_name', 'prompt_version', 'configuration'),
    'packet_revisions': ('workspace_id', 'packet_id', 'revision_number'),
}

SQL = """
ALTER TABLE metadata_assertions ADD CONSTRAINT assertion_real_calendar CHECK (
 date_precision IS DISTINCT FROM 'day' OR value_day <= CASE
 WHEN value_month IN (4,6,9,11) THEN 30
 WHEN value_month=2 THEN CASE WHEN value_year%400=0 OR (value_year%4=0 AND value_year%100<>0) THEN 29 ELSE 28 END
 ELSE 31 END);

CREATE FUNCTION continuity_record_relations() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked_record uuid; linked_version uuid; linked_field text; linked_state text; linked_number integer; parent_state text; field text; pointer uuid;
BEGIN
 IF TG_TABLE_NAME='source_versions' THEN
  IF NEW.version_number=1 AND NEW.supersedes_id IS NOT NULL THEN RAISE EXCEPTION 'First version has no predecessor' USING ERRCODE='23514'; END IF;
  IF NEW.version_number>1 THEN
   SELECT record_id, version_number INTO linked_record,linked_number FROM source_versions WHERE id=NEW.supersedes_id;
   IF NOT FOUND OR linked_record<>NEW.record_id OR linked_number<>NEW.version_number-1 THEN RAISE EXCEPTION 'Invalid source lineage' USING ERRCODE='23514'; END IF;
  END IF;
 ELSIF TG_TABLE_NAME='source_records' THEN
  IF NEW.current_version_id IS NOT NULL THEN
  SELECT record_id,supersedes_id,version_number INTO linked_record,linked_version,linked_number FROM source_versions WHERE id=NEW.current_version_id;
  IF linked_record IS DISTINCT FROM NEW.id THEN RAISE EXCEPTION 'Invalid source head' USING ERRCODE='23514'; END IF;
  IF TG_OP='UPDATE' AND NEW.current_version_id IS DISTINCT FROM OLD.current_version_id THEN
   IF (OLD.current_version_id IS NULL AND linked_number<>1) OR
      (OLD.current_version_id IS NOT NULL AND linked_version IS DISTINCT FROM OLD.current_version_id) THEN
    RAISE EXCEPTION 'Source head must advance through lineage' USING ERRCODE='23514';
   END IF;
  END IF;
  END IF;
 ELSIF TG_TABLE_NAME='generation_runs' THEN
  SELECT source_version_id INTO linked_version FROM ingestion_jobs WHERE id=NEW.job_id;
  IF linked_version IS DISTINCT FROM NEW.source_version_id THEN RAISE EXCEPTION 'Generation source mismatch' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='derived_artifacts' THEN
  SELECT source_version_id INTO linked_version FROM text_extractions WHERE id=NEW.extraction_id;
  IF linked_version IS DISTINCT FROM NEW.source_version_id THEN RAISE EXCEPTION 'Extraction source mismatch' USING ERRCODE='23514'; END IF;
  SELECT source_version_id INTO linked_version FROM generation_runs WHERE id=NEW.generation_id;
  IF linked_version IS DISTINCT FROM NEW.source_version_id THEN RAISE EXCEPTION 'Generation source mismatch' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='metadata_assertions' THEN
  IF NEW.supersedes_id IS NOT NULL THEN
   SELECT source_version_id,field_name INTO linked_version,linked_field FROM metadata_assertions WHERE id=NEW.supersedes_id;
   IF linked_version IS DISTINCT FROM NEW.source_version_id OR linked_field IS DISTINCT FROM NEW.field_name THEN RAISE EXCEPTION 'Assertion lineage mismatch' USING ERRCODE='23514'; END IF;
  END IF;
  IF NEW.evidence_artifact_id IS NOT NULL THEN
   SELECT source_version_id INTO linked_version FROM derived_artifacts WHERE id=NEW.evidence_artifact_id;
   IF linked_version IS DISTINCT FROM NEW.source_version_id THEN RAISE EXCEPTION 'Evidence source mismatch' USING ERRCODE='23514'; END IF;
  END IF;
 ELSIF TG_TABLE_NAME IN ('metadata_heads','packet_source_items') THEN
  IF TG_TABLE_NAME='metadata_heads' THEN
   IF TG_OP='UPDATE' AND NEW.revision<>OLD.revision+1 THEN
    RAISE EXCEPTION 'Metadata revision must advance once' USING ERRCODE='23514';
   END IF;
  END IF;
  FOREACH field IN ARRAY ARRAY['document_type','document_date','facility_name'] LOOP
   pointer := (to_jsonb(NEW)->>(field||'_id'))::uuid;
   IF pointer IS NOT NULL THEN
    SELECT source_version_id,field_name,review_state INTO linked_version,linked_field,linked_state FROM metadata_assertions WHERE id=pointer;
    IF linked_version IS DISTINCT FROM NEW.source_version_id OR linked_field IS DISTINCT FROM field OR linked_state<>'confirmed' THEN RAISE EXCEPTION 'Confirmed metadata source mismatch' USING ERRCODE='23514'; END IF;
   END IF;
  END LOOP;
 END IF;
 IF TG_TABLE_NAME='packet_source_items' THEN
  SELECT state INTO parent_state FROM packet_revisions WHERE id=NEW.revision_id FOR UPDATE;
  IF parent_state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Approved packet is frozen' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='packet_revisions' THEN
  IF NEW.state='approved' THEN
   IF NOT EXISTS (SELECT 1 FROM packet_source_items WHERE revision_id=NEW.id) THEN RAISE EXCEPTION 'Packet must contain a source' USING ERRCODE='23514'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END; $$;

CREATE FUNCTION continuity_terminal_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (TG_TABLE_NAME='ingestion_jobs' AND OLD.state IN ('failed','needs_ocr','review_ready')) OR
    (TG_TABLE_NAME='generation_runs' AND OLD.state IN ('completed','failed')) OR
    (TG_TABLE_NAME='packet_revisions' AND OLD.state='approved') THEN
   RAISE EXCEPTION 'Terminal history is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
"""


def install(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    for table, links in PARENTS.items():
        for name, parent in links.items():
            editor.execute(f'ALTER TABLE {table} ADD CONSTRAINT {table}_{name}_workspace_fk FOREIGN KEY (workspace_id,{name}_id) REFERENCES {parent}(workspace_id,id) ON DELETE RESTRICT')
    editor.execute(SQL, params=None)
    for table in PARENTS:
        if table not in ('ingestion_jobs', 'text_extractions'):
            editor.execute(f'CREATE TRIGGER records_relations BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_record_relations()')
    for table in IMMUTABLE:
        editor.execute(f'CREATE TRIGGER records_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_append_only()')
    for table, fields in BOUND.items():
        editor.execute(f'CREATE TRIGGER records_no_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_append_only()')
        for field in fields:
            editor.execute(f"CREATE TRIGGER records_bind_{field} BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_immutable_binding('{field}')")
    for table in ('ingestion_jobs','generation_runs','packet_revisions'):
        editor.execute(f'CREATE TRIGGER records_terminal BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_terminal_history()')
    editor.execute('CREATE TRIGGER packet_items_no_mutation BEFORE UPDATE OR DELETE ON packet_source_items FOR EACH ROW EXECUTE FUNCTION continuity_append_only()')


def remove(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    editor.execute('DROP TRIGGER packet_items_no_mutation ON packet_source_items')
    for table in ('ingestion_jobs','generation_runs','packet_revisions'):
        editor.execute(f'DROP TRIGGER records_terminal ON {table}')
    for table, fields in BOUND.items():
        editor.execute(f'DROP TRIGGER records_no_delete ON {table}')
        for field in fields:
            editor.execute(f'DROP TRIGGER records_bind_{field} ON {table}')
    for table in IMMUTABLE:
        editor.execute(f'DROP TRIGGER records_append_only ON {table}')
    for table in PARENTS:
        if table not in ('ingestion_jobs','text_extractions'):
            editor.execute(f'DROP TRIGGER records_relations ON {table}')
        for name in PARENTS[table]:
            editor.execute(f'ALTER TABLE {table} DROP CONSTRAINT {table}_{name}_workspace_fk')
    editor.execute('DROP FUNCTION continuity_terminal_history(); DROP FUNCTION continuity_record_relations(); ALTER TABLE metadata_assertions DROP CONSTRAINT assertion_real_calendar;')


class Migration(migrations.Migration):
    dependencies = [('records','0001_initial'), ('identity','0003_self_record_actions')]
    operations = [migrations.RunPython(install, remove)]
