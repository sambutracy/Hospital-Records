from django.db import migrations


SQL='''
ALTER TABLE care_ai_evidence ADD CONSTRAINT care_ai_evidence_task_scope FOREIGN KEY (workspace_id,task_id)
 REFERENCES assistant_tasks(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE care_ai_reviews ADD CONSTRAINT care_ai_review_task_scope FOREIGN KEY (workspace_id,task_id)
 REFERENCES assistant_tasks(workspace_id,id) ON DELETE RESTRICT;
CREATE FUNCTION continuity_care_ai_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_workspace uuid; parent_actor uuid; parent_kind text; parent_state text; packet uuid;
 target_workspace uuid; target_revision integer; source_identity uuid; contents jsonb;
BEGIN
 SELECT workspace_id,requested_by_id,kind,state,packet_revision_id INTO parent_workspace,parent_actor,parent_kind,parent_state,packet
 FROM assistant_tasks WHERE id=NEW.task_id;
 IF parent_workspace IS DISTINCT FROM NEW.workspace_id OR parent_kind NOT IN ('history_exploration','followup_actions') THEN
  RAISE EXCEPTION 'Care AI task scope mismatch' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='care_ai_evidence' THEN
  IF parent_state<>'queued' OR NEW.label !~ '^e([1-9]|1[0-2])$' OR length(NEW.body)>6000 OR
     encode(sha256(convert_to(NEW.body,'UTF8')),'hex') IS DISTINCT FROM NEW.snapshot_sha256 THEN
   RAISE EXCEPTION 'Invalid care AI snapshot' USING ERRCODE='23514'; END IF;
  contents=NEW.body::jsonb;
  IF jsonb_typeof(contents->'text') IS DISTINCT FROM 'string' OR length(contents->>'text') NOT BETWEEN 1 AND 1000 OR
     jsonb_typeof(contents->'metadata') IS DISTINCT FROM 'object' OR contents->'metadata'->>'kind' IS DISTINCT FROM NEW.kind OR
     (contents->'metadata'->>'revision')::integer IS DISTINCT FROM NEW.revision OR
     NOT COALESCE(continuity_care_date(contents->'metadata'->'occurrence'),false) THEN
   RAISE EXCEPTION 'Invalid care AI evidence shape' USING ERRCODE='23514'; END IF;
  CASE NEW.kind
   WHEN 'journal' THEN SELECT workspace_id,revision,event_id INTO target_workspace,target_revision,source_identity FROM journal_history WHERE id=NEW.target_id;
   WHEN 'document' THEN SELECT workspace_id,version_number,id INTO target_workspace,target_revision,source_identity FROM source_versions WHERE id=NEW.target_id;
   WHEN 'medication' THEN SELECT workspace_id,revision,id INTO target_workspace,target_revision,source_identity FROM medication_entries WHERE id=NEW.target_id AND status='active';
   WHEN 'concern' THEN SELECT workspace_id,revision,target_id INTO target_workspace,target_revision,source_identity FROM care_history WHERE id=NEW.target_id AND target_kind='concern';
   WHEN 'episode' THEN SELECT workspace_id,1,id INTO target_workspace,target_revision,source_identity FROM care_episodes WHERE id=NEW.target_id;
   ELSE RAISE EXCEPTION 'Unsupported care AI evidence' USING ERRCODE='23514';
  END CASE;
  IF target_workspace IS DISTINCT FROM NEW.workspace_id OR target_revision IS DISTINCT FROM NEW.revision OR
     contents->'metadata'->>'source_id' IS DISTINCT FROM source_identity::text THEN
   RAISE EXCEPTION 'Care AI evidence source mismatch' USING ERRCODE='23514'; END IF;
  IF parent_kind='followup_actions' AND (NEW.kind<>'document' OR packet IS NULL OR NOT EXISTS
      (SELECT 1 FROM packet_source_items WHERE revision_id=packet AND source_version_id=NEW.target_id AND workspace_id=NEW.workspace_id)) THEN
   RAISE EXCEPTION 'Follow-up evidence outside selected packet' USING ERRCODE='23514'; END IF;
 ELSE
  IF parent_state<>'completed' OR NEW.actor_id IS DISTINCT FROM parent_actor OR
     (NEW.outcome='rejected' AND NEW.planning_draft IS NOT NULL) OR
     (NEW.outcome<>'rejected' AND (jsonb_typeof(NEW.planning_draft) IS DISTINCT FROM 'array' OR jsonb_array_length(NEW.planning_draft)>6)) THEN
   RAISE EXCEPTION 'Invalid care AI review binding' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER care_ai_evidence_scope BEFORE INSERT ON care_ai_evidence FOR EACH ROW EXECUTE FUNCTION continuity_care_ai_guard();
CREATE TRIGGER care_ai_review_scope BEFORE INSERT ON care_ai_reviews FOR EACH ROW EXECUTE FUNCTION continuity_care_ai_guard();
CREATE TRIGGER care_ai_evidence_immutable BEFORE UPDATE OR DELETE ON care_ai_evidence FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
CREATE TRIGGER care_ai_review_immutable BEFORE UPDATE OR DELETE ON care_ai_reviews FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
'''

REVERSE='''
DROP TRIGGER care_ai_review_immutable ON care_ai_reviews;
DROP TRIGGER care_ai_evidence_immutable ON care_ai_evidence;
DROP TRIGGER care_ai_review_scope ON care_ai_reviews;
DROP TRIGGER care_ai_evidence_scope ON care_ai_evidence;
DROP FUNCTION continuity_care_ai_guard();
ALTER TABLE care_ai_reviews DROP CONSTRAINT care_ai_review_task_scope;
ALTER TABLE care_ai_evidence DROP CONSTRAINT care_ai_evidence_task_scope;
'''


def install(apps,editor):
    if editor.connection.vendor=='postgresql': editor.execute(SQL)


def remove(apps,editor):
    if editor.connection.vendor=='postgresql': editor.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies=[('records','0020_care_ai_evidence')]
    operations=[migrations.RunPython(install,remove)]
