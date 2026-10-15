from django.db import migrations

SQL = """
ALTER TABLE journal_events ADD CONSTRAINT journal_occurrence_date CHECK (COALESCE(continuity_care_date(occurrence),false));
ALTER TABLE journal_events ADD CONSTRAINT journal_description_required CHECK (length(btrim(description))>0);
ALTER TABLE journal_events ADD CONSTRAINT journal_concern_scope FOREIGN KEY (workspace_id,concern_id)
 REFERENCES patient_health_concerns(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE journal_history ADD CONSTRAINT journal_history_scope FOREIGN KEY (workspace_id,event_id)
 REFERENCES journal_events(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE journal_drafts ADD CONSTRAINT journal_draft_scope FOREIGN KEY (workspace_id,event_id)
 REFERENCES journal_events(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE journal_drafts ADD CONSTRAINT journal_draft_binding CHECK
 ((event_id IS NULL AND base_revision=0) OR (event_id IS NOT NULL AND base_revision>0));
CREATE FUNCTION continuity_journal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE local_stamp timestamp;
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name=NEW.timezone_name) THEN
  RAISE EXCEPTION 'Invalid journal time zone' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.created_by_id IS DISTINCT FROM NEW.updated_by_id THEN
   RAISE EXCEPTION 'Journal initial actor mismatch' USING ERRCODE='23514'; END IF;
 ELSIF NEW.created_by_id IS DISTINCT FROM OLD.created_by_id THEN
  RAISE EXCEPTION 'Journal creator is immutable' USING ERRCODE='23514';
 END IF;
 IF NEW.occurrence_time IS NULL THEN
  IF NEW.occurred_at IS NOT NULL OR NEW.time_fold IS NOT NULL THEN
   RAISE EXCEPTION 'Journal instant needs local time' USING ERRCODE='23514'; END IF;
 ELSE
  IF NEW.occurrence->>'precision' IS DISTINCT FROM 'day' OR NEW.occurred_at IS NULL OR NEW.time_fold IS NULL OR
    extract(second FROM NEW.occurrence_time)<>0 THEN
   RAISE EXCEPTION 'Journal time needs complete date and instant' USING ERRCODE='23514'; END IF;
  local_stamp=make_date((NEW.occurrence->>'year')::int,(NEW.occurrence->>'month')::int,(NEW.occurrence->>'day')::int)+NEW.occurrence_time;
  IF timezone(NEW.timezone_name,NEW.occurred_at) IS DISTINCT FROM local_stamp THEN
   RAISE EXCEPTION 'Journal time zone round trip failed' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE FUNCTION continuity_journal_snapshot() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 INSERT INTO public.journal_history(id,workspace_id,created_at,event_id,revision,actor_id,snapshot)
 VALUES(gen_random_uuid(),NEW.workspace_id,now(),NEW.id,NEW.revision,NEW.updated_by_id,
  to_jsonb(NEW)-ARRAY['id','workspace_id']);
 RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION continuity_journal_snapshot() FROM PUBLIC;
CREATE FUNCTION continuity_journal_draft_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE key text; lim integer;
BEGIN
 IF jsonb_typeof(NEW.fields) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(NEW.fields))<>11 THEN
  RAISE EXCEPTION 'Invalid editor schema' USING ERRCODE='23514'; END IF;
 FOR key,lim IN SELECT * FROM (VALUES ('category',16),('description',2000),('precision',8),('year',4),('month',2),('day',2),
   ('time',5),('timezone',64),('fold',1),('severity',2),('concern_id',36)) AS limits(k,l)
 LOOP
  IF jsonb_typeof(NEW.fields->key) IS DISTINCT FROM 'string' OR length(NEW.fields->>key)>lim THEN
   RAISE EXCEPTION 'Invalid editor field' USING ERRCODE='23514'; END IF;
 END LOOP;
 IF NEW.fields->>'category' NOT IN ('note','symptom') OR NEW.fields->>'precision' NOT IN ('unknown','year','month','day') OR NEW.status<>'active' THEN
  RAISE EXCEPTION 'Invalid editor category' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER journal_note_revision BEFORE INSERT OR UPDATE ON journal_events FOR EACH ROW EXECUTE FUNCTION continuity_patient_notes();
CREATE TRIGGER journal_guard BEFORE INSERT OR UPDATE ON journal_events FOR EACH ROW EXECUTE FUNCTION continuity_journal_guard();
CREATE TRIGGER journal_no_delete BEFORE DELETE ON journal_events FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
CREATE TRIGGER journal_snapshot AFTER INSERT OR UPDATE ON journal_events FOR EACH ROW EXECUTE FUNCTION continuity_journal_snapshot();
CREATE TRIGGER journal_history_immutable BEFORE UPDATE OR DELETE ON journal_history FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
CREATE TRIGGER journal_draft_revision BEFORE INSERT OR UPDATE ON journal_drafts FOR EACH ROW EXECUTE FUNCTION continuity_patient_notes();
CREATE TRIGGER journal_draft_guard BEFORE INSERT OR UPDATE ON journal_drafts FOR EACH ROW EXECUTE FUNCTION continuity_journal_draft_guard();
CREATE INDEX journal_occurrence_lookup ON journal_events(workspace_id,continuity_care_bound(occurrence,false),id);
"""

REVERSE = """
DROP TRIGGER journal_note_revision ON journal_events;
DROP TRIGGER journal_guard ON journal_events;
DROP TRIGGER journal_no_delete ON journal_events;
DROP TRIGGER journal_snapshot ON journal_events;
DROP TRIGGER journal_history_immutable ON journal_history;
DROP TRIGGER journal_draft_revision ON journal_drafts;
DROP TRIGGER journal_draft_guard ON journal_drafts;
DROP FUNCTION continuity_journal_guard(); DROP FUNCTION continuity_journal_snapshot(); DROP FUNCTION continuity_journal_draft_guard();
DROP INDEX journal_occurrence_lookup;
ALTER TABLE journal_events DROP CONSTRAINT journal_occurrence_date, DROP CONSTRAINT journal_description_required, DROP CONSTRAINT journal_concern_scope;
ALTER TABLE journal_history DROP CONSTRAINT journal_history_scope;
ALTER TABLE journal_drafts DROP CONSTRAINT journal_draft_scope, DROP CONSTRAINT journal_draft_binding;
"""


def install(apps,editor):
    if editor.connection.vendor=='postgresql': editor.execute(SQL,params=None)


def remove(apps,editor):
    if editor.connection.vendor=='postgresql': editor.execute(REVERSE,params=None)


class Migration(migrations.Migration):
    dependencies=[('records','0015_journal_foundation')]
    operations=[migrations.RunPython(install,remove)]
