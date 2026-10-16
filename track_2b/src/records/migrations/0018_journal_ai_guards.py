from django.db import migrations


SQL = '''
ALTER TABLE journal_ai_requests ADD CONSTRAINT journal_ai_request_task_scope
 FOREIGN KEY (workspace_id,task_id) REFERENCES assistant_tasks(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE journal_ai_requests ADD CONSTRAINT journal_ai_request_draft_scope
 FOREIGN KEY (workspace_id,draft_id) REFERENCES journal_drafts(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE journal_ai_requests ADD CONSTRAINT journal_ai_request_event_scope
 FOREIGN KEY (workspace_id,event_id) REFERENCES journal_events(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE journal_ai_proposals ADD CONSTRAINT journal_ai_proposal_request_scope
 FOREIGN KEY (workspace_id,request_id) REFERENCES journal_ai_requests(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE journal_ai_reviews ADD CONSTRAINT journal_ai_review_proposal_scope
 FOREIGN KEY (workspace_id,proposal_id) REFERENCES journal_ai_proposals(workspace_id,id) ON DELETE RESTRICT;
ALTER TABLE journal_ai_reviews ADD CONSTRAINT journal_ai_review_event_scope
 FOREIGN KEY (workspace_id,event_id) REFERENCES journal_events(workspace_id,id) ON DELETE RESTRICT;

CREATE FUNCTION continuity_journal_ai_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE request_workspace uuid; bound_actor uuid; bound_kind text;
BEGIN
 IF TG_TABLE_NAME='journal_ai_requests' THEN
  IF TG_OP='UPDATE' THEN
   IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.task_id IS DISTINCT FROM OLD.task_id OR
      NEW.requested_by_id IS DISTINCT FROM OLD.requested_by_id OR NEW.draft_id IS DISTINCT FROM OLD.draft_id OR
      NEW.draft_revision IS DISTINCT FROM OLD.draft_revision OR NEW.event_id IS DISTINCT FROM OLD.event_id OR
      NEW.base_revision IS DISTINCT FROM OLD.base_revision OR NEW.input_sha256 IS DISTINCT FROM OLD.input_sha256 OR
      NEW.reference_at IS DISTINCT FROM OLD.reference_at OR NEW.reference_timezone IS DISTINCT FROM OLD.reference_timezone OR
      NEW.expires_at IS DISTINCT FROM OLD.expires_at OR
      (OLD.input_snapshot='' AND NEW.input_snapshot IS DISTINCT FROM OLD.input_snapshot) THEN
    RAISE EXCEPTION 'Journal AI request binding is immutable' USING ERRCODE='23514';
   END IF;
  END IF;
  SELECT workspace_id,requested_by_id,kind INTO request_workspace,bound_actor,bound_kind
    FROM assistant_tasks WHERE id=NEW.task_id;
  IF request_workspace IS DISTINCT FROM NEW.workspace_id OR bound_actor IS DISTINCT FROM NEW.requested_by_id OR
     bound_kind IS DISTINCT FROM 'journal_interpretation' THEN
    RAISE EXCEPTION 'Journal AI task scope mismatch' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM journal_drafts d WHERE d.id=NEW.draft_id AND d.workspace_id=NEW.workspace_id
       AND d.revision=NEW.draft_revision AND d.event_id IS NOT DISTINCT FROM NEW.event_id
       AND d.base_revision=NEW.base_revision) THEN
    RAISE EXCEPTION 'Journal AI draft binding mismatch' USING ERRCODE='23514';
  END IF;
 ELSIF TG_TABLE_NAME='journal_ai_proposals' THEN
  SELECT workspace_id INTO request_workspace FROM journal_ai_requests WHERE id=NEW.request_id;
  IF request_workspace IS DISTINCT FROM NEW.workspace_id THEN
   RAISE EXCEPTION 'Journal AI proposal scope mismatch' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND NOT (NEW.workspace_id=OLD.workspace_id AND NEW.request_id=OLD.request_id AND
      NEW.schema_version=OLD.schema_version AND NEW.model_name=OLD.model_name AND
      NEW.prompt_version=OLD.prompt_version AND NEW.generated_at=OLD.generated_at AND NEW.expires_at=OLD.expires_at AND
      NEW.fields IS NULL AND NEW.evidence='{}'::jsonb AND NEW.unknown='[]'::jsonb AND NEW.ambiguities='[]'::jsonb) THEN
   RAISE EXCEPTION 'Journal AI proposal is immutable except for retention clearing' USING ERRCODE='23514';
  END IF;
 ELSIF TG_TABLE_NAME='journal_ai_reviews' THEN
  SELECT workspace_id INTO request_workspace FROM journal_ai_proposals WHERE id=NEW.proposal_id;
  IF request_workspace IS DISTINCT FROM NEW.workspace_id THEN
   RAISE EXCEPTION 'Journal AI review scope mismatch' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER journal_ai_request_guard BEFORE INSERT OR UPDATE ON journal_ai_requests
 FOR EACH ROW EXECUTE FUNCTION continuity_journal_ai_guard();
CREATE TRIGGER journal_ai_proposal_guard BEFORE INSERT OR UPDATE ON journal_ai_proposals
 FOR EACH ROW EXECUTE FUNCTION continuity_journal_ai_guard();
CREATE TRIGGER journal_ai_review_guard BEFORE INSERT ON journal_ai_reviews
 FOR EACH ROW EXECUTE FUNCTION continuity_journal_ai_guard();
CREATE TRIGGER journal_ai_review_immutable BEFORE UPDATE OR DELETE ON journal_ai_reviews
 FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
CREATE TRIGGER journal_ai_request_no_delete BEFORE DELETE ON journal_ai_requests
 FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
CREATE TRIGGER journal_ai_proposal_no_delete BEFORE DELETE ON journal_ai_proposals
 FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
'''

REVERSE = '''
DROP TRIGGER journal_ai_proposal_no_delete ON journal_ai_proposals;
DROP TRIGGER journal_ai_request_no_delete ON journal_ai_requests;
DROP TRIGGER journal_ai_review_immutable ON journal_ai_reviews;
DROP TRIGGER journal_ai_review_guard ON journal_ai_reviews;
DROP TRIGGER journal_ai_proposal_guard ON journal_ai_proposals;
DROP TRIGGER journal_ai_request_guard ON journal_ai_requests;
DROP FUNCTION continuity_journal_ai_guard();
ALTER TABLE journal_ai_reviews DROP CONSTRAINT journal_ai_review_event_scope, DROP CONSTRAINT journal_ai_review_proposal_scope;
ALTER TABLE journal_ai_proposals DROP CONSTRAINT journal_ai_proposal_request_scope;
ALTER TABLE journal_ai_requests DROP CONSTRAINT journal_ai_request_event_scope, DROP CONSTRAINT journal_ai_request_draft_scope, DROP CONSTRAINT journal_ai_request_task_scope;
'''


def install(apps, editor):
    if editor.connection.vendor == 'postgresql':
        editor.execute(SQL)


def remove(apps, editor):
    if editor.connection.vendor == 'postgresql':
        editor.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies = [('records', '0017_journalaiproposal_journalairequest_journalaireview_and_more')]
    operations = [migrations.RunPython(install, remove)]
