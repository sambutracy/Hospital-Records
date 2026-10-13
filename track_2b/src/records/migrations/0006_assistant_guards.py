from django.db import migrations


def install(apps, editor):
    if editor.connection.vendor!='postgresql':
        return
    editor.execute('''
      ALTER TABLE assistant_tasks ADD CONSTRAINT assistant_packet_workspace_fk
        FOREIGN KEY (workspace_id,packet_revision_id) REFERENCES packet_revisions(workspace_id,id) ON DELETE RESTRICT;
      ALTER TABLE assistant_sources ADD CONSTRAINT assistant_task_workspace_fk
        FOREIGN KEY (workspace_id,task_id) REFERENCES assistant_tasks(workspace_id,id) ON DELETE RESTRICT;
      ALTER TABLE assistant_sources ADD CONSTRAINT assistant_version_workspace_fk
        FOREIGN KEY (workspace_id,source_version_id) REFERENCES source_versions(workspace_id,id) ON DELETE RESTRICT;
      ALTER TABLE assistant_sources ADD CONSTRAINT assistant_extraction_workspace_fk
        FOREIGN KEY (workspace_id,extraction_id) REFERENCES text_extractions(workspace_id,id) ON DELETE RESTRICT;
      CREATE TRIGGER assistant_source_history BEFORE UPDATE OR DELETE ON assistant_sources
        FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
      CREATE TRIGGER assistant_task_no_delete BEFORE DELETE ON assistant_tasks
        FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
      CREATE FUNCTION continuity_assistant_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE request_kind text; revision uuid; expected_source text; extracted_source uuid;
      BEGIN
        IF TG_TABLE_NAME='assistant_sources' THEN
          SELECT kind,packet_revision_id,parameters->>'source_version_id'
            INTO request_kind,revision,expected_source FROM assistant_tasks WHERE id=NEW.task_id;
          IF request_kind='packet_overview' AND NOT EXISTS
            (SELECT 1 FROM packet_source_items WHERE revision_id=revision AND source_version_id=NEW.source_version_id) THEN
            RAISE EXCEPTION 'Source outside selected packet' USING ERRCODE='23514';
          END IF;
          IF request_kind='explain_term' AND expected_source IS DISTINCT FROM NEW.source_version_id::text THEN
            RAISE EXCEPTION 'Term source mismatch' USING ERRCODE='23514';
          END IF;
          IF NEW.extraction_id IS NOT NULL THEN
            SELECT source_version_id INTO extracted_source FROM text_extractions WHERE id=NEW.extraction_id;
            IF extracted_source IS DISTINCT FROM NEW.source_version_id THEN
              RAISE EXCEPTION 'Assistant extraction source mismatch' USING ERRCODE='23514';
            END IF;
          END IF;
        ELSE
          IF OLD.state IN ('completed','failed') THEN
            RAISE EXCEPTION 'Terminal assistant history is immutable' USING ERRCODE='23514';
          END IF;
          IF NEW.state IS DISTINCT FROM OLD.state AND NOT
            ((OLD.state='queued' AND NEW.state IN ('processing','failed')) OR
             (OLD.state='waiting_model' AND NEW.state IN ('processing','failed')) OR
             (OLD.state='processing' AND NEW.state IN ('waiting_model','completed','failed'))) THEN
            RAISE EXCEPTION 'Invalid assistant transition' USING ERRCODE='23514';
          END IF;
          IF OLD.model_name<>'' AND
             (NEW.model_name IS DISTINCT FROM OLD.model_name OR NEW.prompt_version IS DISTINCT FROM OLD.prompt_version OR NEW.configuration IS DISTINCT FROM OLD.configuration) THEN
            RAISE EXCEPTION 'Assistant generation provenance is immutable' USING ERRCODE='23514';
          END IF;
          IF OLD.model_name='' AND NEW.model_name<>'' AND (OLD.state<>'processing' OR NEW.state<>'processing') THEN
            RAISE EXCEPTION 'Generation requires processing lease' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER assistant_source_scope BEFORE INSERT ON assistant_sources
        FOR EACH ROW EXECUTE FUNCTION continuity_assistant_guard();
      CREATE TRIGGER assistant_task_history BEFORE UPDATE ON assistant_tasks
        FOR EACH ROW EXECUTE FUNCTION continuity_assistant_guard();
    ''')
    for field in ('workspace_id','requested_by_id','created_at','kind','parameters','coverage','packet_revision_id'):
        editor.execute(f"CREATE TRIGGER assistant_bind_{field} BEFORE UPDATE ON assistant_tasks FOR EACH ROW EXECUTE FUNCTION continuity_immutable_binding('{field}')")


def remove(apps, editor):
    if editor.connection.vendor!='postgresql':
        return
    for field in ('workspace_id','requested_by_id','created_at','kind','parameters','coverage','packet_revision_id'):
        editor.execute(f'DROP TRIGGER assistant_bind_{field} ON assistant_tasks')
    editor.execute('''
      DROP TRIGGER assistant_task_history ON assistant_tasks;
      DROP TRIGGER assistant_source_scope ON assistant_sources;
      DROP FUNCTION continuity_assistant_guard();
      DROP TRIGGER assistant_task_no_delete ON assistant_tasks;
      DROP TRIGGER assistant_source_history ON assistant_sources;
      ALTER TABLE assistant_sources DROP CONSTRAINT assistant_extraction_workspace_fk;
      ALTER TABLE assistant_sources DROP CONSTRAINT assistant_version_workspace_fk;
      ALTER TABLE assistant_sources DROP CONSTRAINT assistant_task_workspace_fk;
      ALTER TABLE assistant_tasks DROP CONSTRAINT assistant_packet_workspace_fk;
    ''')


class Migration(migrations.Migration):
    dependencies=[('records','0005_record_assistant')]
    operations=[migrations.RunPython(install,remove)]
