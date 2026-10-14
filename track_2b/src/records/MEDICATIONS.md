# Patient-reported medicines across visits

Prescription originals were already supported by the `prescription` metadata type. The medication list adds structured patient notes around different visits: medicine name, dose/strength and frequency **as written**, how taken, instructions/notes, patient-reported prescribed/taken/not-taken/unknown status, partial or unknown visit date, optional named care episode and optional exact supporting source version. More than one entry for the same medicine is allowed, so different visits can retain separate contexts. The date describes the patient's stated visit/record context; it is not an inferred appointment or medication start/stop time.

Prescribed and taken are separate states. An original prescription link is not proof of adherence, a verified dose or current suitability. Comfort does not calculate dose, reconcile prescriptions, check drug interactions or recommend treatment changes. Entries are explicitly patient-reported; no LLM call generates or updates them. Original bytes/checksums and source-version links remain exact when an uploaded record is replaced later.

## API

Patient routes under `/api/workspaces/{workspace}/`:

- `medications/`: GET a 50-row page (offset, include_archived=0|1) or POST `{values,expected_revision:0}`.
- `medications/{entry}/`: POST complete values with current expected_revision.
- `medications/{entry}/status/`: POST `{status:active|archived,expected_revision}`; archive is reversible.
- `medications/choices/`: same-workspace episode and original-version choices; originals are paged in batches of 100.

Values have exactly medicine_name, dose, frequency, route, instructions, use_status (`reported_taken`, `reported_prescribed`, `not_taken`, `unknown`), visit_date (`precision`,`year`,`month`,`day`), episode_id (UUID or null), source_version_id (UUID or null). Empty optional text is retained as empty, not inferred. The linked original may be an old immutable version. Pending clinician submissions cannot be linked until accepted into SourceVersion.

**manage_medications** is a live self capability separate from record reads. Linking/browsing/downloading originals also needs the existing read capability. Recipient read shares and provider contribution authority do not permit opening/editing this medication list. Same-workspace foreign keys, true calendar checks, editor/subject and creator bindings, revision/row locks and private audit metadata protect writes. Patient note edits retain current values and revision/actor/time audit; they do not create a full immutable field-value history. Uploaded originals remain immutable.

Medication notes are currently private and are not automatically added to packets, shared views or Apertus prompts. Share the chosen original prescription through an approved packet when needed. Exporting/sharing a selected medication-note snapshot, prescribing workflows, reconciliation and appointment/referral lifecycle integration remain separate work.
