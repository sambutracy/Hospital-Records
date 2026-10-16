"""Keep a scoped historical draft UUID without retaining the disposable draft."""
from importlib import import_module

from django.db import migrations, models


GUARD = '''
CREATE OR REPLACE FUNCTION continuity_journal_ai_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
      (NEW.input_snapshot IS DISTINCT FROM OLD.input_snapshot AND NEW.input_snapshot<>'') OR
      (NEW.snapshot_released_at IS DISTINCT FROM OLD.snapshot_released_at AND
       (OLD.snapshot_released_at IS NOT NULL OR NEW.snapshot_released_at IS NULL OR NEW.input_snapshot<>'')) THEN
    RAISE EXCEPTION 'Journal AI request binding is immutable' USING ERRCODE='23514';
   END IF;
  END IF;
  SELECT workspace_id,requested_by_id,kind INTO request_workspace,bound_actor,bound_kind
    FROM assistant_tasks WHERE id=NEW.task_id;
  IF request_workspace IS DISTINCT FROM NEW.workspace_id OR bound_actor IS DISTINCT FROM NEW.requested_by_id OR
     bound_kind IS DISTINCT FROM 'journal_interpretation' THEN
    RAISE EXCEPTION 'Journal AI task scope mismatch' USING ERRCODE='23514';
  END IF;
  -- The live recovery draft is checked once. Its UUID and captured revision are
  -- historical after INSERT; legitimate edits/deletion cannot corrupt this row.
  IF TG_OP='INSERT' THEN
   IF NOT EXISTS (SELECT 1 FROM journal_drafts d WHERE d.id=NEW.draft_id AND d.workspace_id=NEW.workspace_id
        AND d.revision=NEW.draft_revision AND d.event_id IS NOT DISTINCT FROM NEW.event_id
        AND d.base_revision=NEW.base_revision) THEN
     RAISE EXCEPTION 'Journal AI draft binding mismatch' USING ERRCODE='23514';
   END IF;
   IF NEW.input_snapshot='' OR NEW.snapshot_released_at IS NOT NULL OR
      encode(sha256(convert_to(NEW.input_snapshot,'UTF8')),'hex') IS DISTINCT FROM NEW.input_sha256 THEN
     RAISE EXCEPTION 'Journal AI snapshot digest mismatch' USING ERRCODE='23514';
   END IF;
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
'''


def drop_draft_fk(apps, editor):
    if editor.connection.vendor == 'postgresql':
        editor.execute('ALTER TABLE journal_ai_requests DROP CONSTRAINT journal_ai_request_draft_scope')


def restore_draft_fk(apps, editor):
    if editor.connection.vendor == 'postgresql':
        # A reverse intentionally fails if historical drafts have been deleted.
        # Never fabricate drafts or discard history to make a rollback succeed.
        editor.execute('''ALTER TABLE journal_ai_requests ADD CONSTRAINT journal_ai_request_draft_scope
            FOREIGN KEY (workspace_id,draft_id) REFERENCES journal_drafts(workspace_id,id) ON DELETE RESTRICT''')


def install(apps, editor):
    if editor.connection.vendor == 'postgresql':
        editor.execute(GUARD)


def restore(apps, editor):
    if editor.connection.vendor == 'postgresql':
        previous = import_module('records.migrations.0018_journal_ai_guards').SQL
        function = previous[previous.index('CREATE FUNCTION continuity_journal_ai_guard()'):previous.index('CREATE TRIGGER journal_ai_request_guard')]
        editor.execute(function.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1))


class Migration(migrations.Migration):
    dependencies = [('records', '0018_journal_ai_guards')]
    operations = [
        migrations.RunPython(drop_draft_fk, restore_draft_fk),
        migrations.AlterField(model_name='journalairequest', name='draft',
            field=models.UUIDField(db_column='draft_id', db_index=True, editable=False)),
        migrations.RenameField(model_name='journalairequest', old_name='draft', new_name='draft_id'),
        migrations.RunPython(install, restore),
    ]
