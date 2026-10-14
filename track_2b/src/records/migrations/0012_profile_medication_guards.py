from django.db import migrations

TABLES=('patient_personal_details','care_circle_entries','medication_entries')
SQL="""
CREATE FUNCTION continuity_patient_notes() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM users u JOIN patient_workspaces w ON w.id=NEW.workspace_id
    JOIN patient_profiles p ON p.id=w.subject_patient_id WHERE u.id=NEW.updated_by_id AND u.person_id=p.person_id) THEN
  RAISE EXCEPTION 'Patient note editor must match subject' USING ERRCODE='23514';
 END IF;
 IF TG_OP='INSERT' AND NEW.revision<>1 THEN RAISE EXCEPTION 'First patient note revision is one' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' THEN
  IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.id IS DISTINCT FROM OLD.id OR
     NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.revision<>OLD.revision+1 THEN
   RAISE EXCEPTION 'Patient note binding or revision changed' USING ERRCODE='23514';
  END IF;
 END IF;
 IF TG_TABLE_NAME='medication_entries' THEN
  IF TG_OP='UPDATE' THEN
   IF NEW.created_by_id IS DISTINCT FROM OLD.created_by_id THEN
    RAISE EXCEPTION 'Medication creator is immutable' USING ERRCODE='23514';
   END IF;
  ELSIF NEW.created_by_id IS DISTINCT FROM NEW.updated_by_id THEN
   RAISE EXCEPTION 'Medication initial actor mismatch' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END; $$;
ALTER TABLE medication_entries ADD CONSTRAINT medication_calendar CHECK (
 date_precision IS DISTINCT FROM 'day' OR value_day <= CASE
 WHEN value_month IN (4,6,9,11) THEN 30
 WHEN value_month=2 THEN CASE WHEN value_year%400=0 OR (value_year%4=0 AND value_year%100<>0) THEN 29 ELSE 28 END
 ELSE 31 END);
"""


def install(apps,editor):
    if editor.connection.vendor!='postgresql':
        return
    editor.execute(SQL,params=None)
    for field,parent in (('episode','care_episodes'),('source_version','source_versions')):
        editor.execute(f'ALTER TABLE medication_entries ADD CONSTRAINT medication_{field}_workspace_fk FOREIGN KEY (workspace_id,{field}_id) REFERENCES {parent}(workspace_id,id) ON DELETE RESTRICT')
    for table in TABLES:
        editor.execute(f'CREATE TRIGGER patient_notes_revision BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_patient_notes()')
        editor.execute(f'CREATE TRIGGER patient_notes_no_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_append_only()')


def remove(apps,editor):
    if editor.connection.vendor!='postgresql':
        return
    for table in TABLES:
        editor.execute(f'DROP TRIGGER patient_notes_revision ON {table}; DROP TRIGGER patient_notes_no_delete ON {table}')
    editor.execute('ALTER TABLE medication_entries DROP CONSTRAINT medication_calendar; ALTER TABLE medication_entries DROP CONSTRAINT medication_episode_workspace_fk; ALTER TABLE medication_entries DROP CONSTRAINT medication_source_version_workspace_fk; DROP FUNCTION continuity_patient_notes()')


class Migration(migrations.Migration):
    dependencies=[('records','0011_medicationentry'),('identity','0005_carecircleentry_patientpersonaldetails_and_more')]
    operations=[migrations.RunPython(install,remove)]
