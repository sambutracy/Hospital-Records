from django.db import migrations


def install(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    editor.execute('''
        ALTER TABLE image_inspections ADD CONSTRAINT image_source_workspace_fk
          FOREIGN KEY (workspace_id, source_version_id) REFERENCES source_versions(workspace_id, id) ON DELETE RESTRICT;
        ALTER TABLE image_inspections ADD CONSTRAINT image_preview_size
          CHECK (preview_png IS NULL OR octet_length(preview_png) BETWEEN 1 AND 1048576);
        CREATE TRIGGER image_inspection_append_only BEFORE UPDATE OR DELETE ON image_inspections
          FOR EACH ROW EXECUTE FUNCTION continuity_append_only();
        CREATE FUNCTION continuity_image_inspection_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE media text;
        BEGIN
          SELECT media_type INTO media FROM source_versions WHERE id=NEW.source_version_id;
          IF media NOT IN ('image/jpeg','image/png','application/dicom') OR
             (media='application/dicom' AND (NEW.details->>'format' IS DISTINCT FROM 'DICOM' OR NEW.preview_png IS NOT NULL)) OR
             (media='image/jpeg' AND (NEW.details->>'format' IS DISTINCT FROM 'JPEG' OR NEW.preview_png IS NULL)) OR
             (media='image/png' AND (NEW.details->>'format' IS DISTINCT FROM 'PNG' OR NEW.preview_png IS NULL)) THEN
            RAISE EXCEPTION 'Image inspection source mismatch' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END; $$;
        CREATE TRIGGER image_inspection_source BEFORE INSERT ON image_inspections
          FOR EACH ROW EXECUTE FUNCTION continuity_image_inspection_guard();
        CREATE FUNCTION continuity_manual_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.state='manual_review' THEN
            RAISE EXCEPTION 'Terminal image history is immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END; $$;
        CREATE TRIGGER image_job_terminal BEFORE UPDATE ON ingestion_jobs
          FOR EACH ROW EXECUTE FUNCTION continuity_manual_job_guard();
    ''')


def remove(apps, editor):
    if editor.connection.vendor != 'postgresql':
        return
    editor.execute('''
        DROP TRIGGER image_job_terminal ON ingestion_jobs;
        DROP FUNCTION continuity_manual_job_guard();
        DROP TRIGGER image_inspection_source ON image_inspections;
        DROP FUNCTION continuity_image_inspection_guard();
        DROP TRIGGER image_inspection_append_only ON image_inspections;
        ALTER TABLE image_inspections DROP CONSTRAINT image_preview_size;
        ALTER TABLE image_inspections DROP CONSTRAINT image_source_workspace_fk;
    ''')


class Migration(migrations.Migration):
    dependencies = [('records', '0003_imaging_intake')]
    operations = [migrations.RunPython(install, remove)]
