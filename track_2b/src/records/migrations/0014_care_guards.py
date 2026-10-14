from django.db import migrations

TABLES = {'patient_health_concerns':'concern', 'reported_practitioners':'practitioner', 'care_team_assignments':'assignment'}
SQL = """
CREATE FUNCTION continuity_care_date(parts jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE precision text; y integer; m integer; d integer;
BEGIN
 IF jsonb_typeof(parts) IS DISTINCT FROM 'object' OR NOT (parts ?& ARRAY['precision','year','month','day']) OR
    (SELECT count(*) FROM jsonb_object_keys(parts))<>4 THEN RETURN false; END IF;
 precision=parts->>'precision';
 IF precision='unknown' THEN RETURN parts->'year'='null'::jsonb AND parts->'month'='null'::jsonb AND parts->'day'='null'::jsonb; END IF;
 IF precision NOT IN ('year','month','day') OR precision IS NULL THEN RETURN false; END IF;
 IF jsonb_typeof(parts->'year') IS DISTINCT FROM 'number' OR (parts->>'year') !~ '^[0-9]+$' THEN RETURN false; END IF;
 y=(parts->>'year')::integer;
 IF y<1 OR y>9999 THEN RETURN false; END IF;
 IF precision='year' THEN RETURN parts->'month'='null'::jsonb AND parts->'day'='null'::jsonb; END IF;
 IF jsonb_typeof(parts->'month') IS DISTINCT FROM 'number' OR (parts->>'month') !~ '^[0-9]+$' THEN RETURN false; END IF;
 m=(parts->>'month')::integer;
 IF m<1 OR m>12 THEN RETURN false; END IF;
 IF precision='month' THEN RETURN parts->'day'='null'::jsonb; END IF;
 IF jsonb_typeof(parts->'day') IS DISTINCT FROM 'number' OR (parts->>'day') !~ '^[0-9]+$' THEN RETURN false; END IF;
 d=(parts->>'day')::integer;
 PERFORM make_date(y,m,d);
 RETURN true;
EXCEPTION WHEN OTHERS THEN RETURN false;
END; $$;
CREATE FUNCTION continuity_care_bound(parts jsonb, upper_bound boolean) RETURNS date LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE y integer; m integer; d integer;
BEGIN
 IF NOT continuity_care_date(parts) OR parts->>'precision'='unknown' THEN RETURN NULL; END IF;
 y=(parts->>'year')::integer;
 m=COALESCE((parts->>'month')::integer,CASE WHEN upper_bound THEN 12 ELSE 1 END);
 d=COALESCE((parts->>'day')::integer,CASE WHEN upper_bound THEN
    extract(day FROM (make_date(y,m,1)+interval '1 month'-interval '1 day'))::integer ELSE 1 END);
 RETURN make_date(y,m,d);
END; $$;
ALTER TABLE patient_health_concerns ADD CONSTRAINT concern_onset_date CHECK (COALESCE(continuity_care_date(onset),false));
ALTER TABLE patient_health_concerns ADD CONSTRAINT concern_title_required CHECK (length(btrim(title))>0);
ALTER TABLE reported_practitioners ADD CONSTRAINT care_doctor_name_required CHECK (length(btrim(name))>0);
ALTER TABLE care_team_assignments ADD CONSTRAINT care_role_required CHECK (length(btrim(role))>0);
ALTER TABLE care_team_assignments ADD CONSTRAINT care_start_date CHECK (COALESCE(continuity_care_date(start_date),false));
ALTER TABLE care_team_assignments ADD CONSTRAINT care_end_date CHECK (COALESCE(continuity_care_date(end_date),false));
ALTER TABLE care_team_assignments ADD CONSTRAINT care_date_order CHECK
 (continuity_care_bound(start_date,false)<=continuity_care_bound(end_date,true));
ALTER TABLE care_team_assignments ADD CONSTRAINT care_practitioner_workspace_fk FOREIGN KEY (workspace_id,practitioner_id)
 REFERENCES reported_practitioners(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE care_team_assignments ADD CONSTRAINT care_concern_workspace_fk FOREIGN KEY (workspace_id,concern_id)
 REFERENCES patient_health_concerns(workspace_id,id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX care_active_relationship ON care_team_assignments(workspace_id,practitioner_id,concern_id)
 NULLS NOT DISTINCT WHERE status='active';
CREATE FUNCTION continuity_care_snapshot() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 INSERT INTO public.care_history(id,workspace_id,created_at,target_kind,target_id,revision,actor_id,snapshot)
 VALUES(gen_random_uuid(),NEW.workspace_id,now(),TG_ARGV[0],NEW.id,NEW.revision,NEW.updated_by_id,
   to_jsonb(NEW)-ARRAY['id','workspace_id','created_at','updated_at','updated_by_id']);
 RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION continuity_care_snapshot() FROM PUBLIC;
"""


def install(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    editor.execute(SQL, params=None)
    for table, kind in TABLES.items():
        editor.execute(f'CREATE TRIGGER care_note_revision BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_patient_notes()')
        editor.execute(f'CREATE TRIGGER care_note_no_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_append_only()')
        editor.execute(f"CREATE TRIGGER care_note_snapshot AFTER INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION continuity_care_snapshot('{kind}')")
    editor.execute('CREATE TRIGGER care_history_immutable BEFORE UPDATE OR DELETE ON care_history FOR EACH ROW EXECUTE FUNCTION continuity_append_only()')


def remove(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    for table in TABLES:
        editor.execute(f'DROP TRIGGER care_note_revision ON {table}; DROP TRIGGER care_note_no_delete ON {table}; DROP TRIGGER care_note_snapshot ON {table}')
    editor.execute('DROP TRIGGER care_history_immutable ON care_history; DROP FUNCTION continuity_care_snapshot()')
    editor.execute('ALTER TABLE patient_health_concerns DROP CONSTRAINT concern_onset_date')
    editor.execute('ALTER TABLE patient_health_concerns DROP CONSTRAINT concern_title_required; ALTER TABLE reported_practitioners DROP CONSTRAINT care_doctor_name_required')
    for name in ('care_start_date','care_end_date','care_date_order','care_role_required','care_practitioner_workspace_fk','care_concern_workspace_fk'):
        editor.execute(f'ALTER TABLE care_team_assignments DROP CONSTRAINT {name}')
    editor.execute('DROP INDEX care_active_relationship; DROP FUNCTION continuity_care_bound(jsonb,boolean); DROP FUNCTION continuity_care_date(jsonb)')


class Migration(migrations.Migration):
    dependencies = [('records','0013_patienthealthconcern_reportedpractitioner_and_more')]
    operations = [migrations.RunPython(install, remove)]
