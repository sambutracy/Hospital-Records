# Patient-reported concerns and care relationships (contract v1)

This slice adds private Health Concerns and Care Team journeys to the React
frontend. It preserves the existing record, medication, immutable care-episode,
sharing and clinician-contribution contracts.

## Domain and provenance

- `PatientHealthConcern`: a title, description, type, reported certainty and
  partial onset date. Types are issue, investigation, injury, condition and
  episode. Certainty is `unconfirmed` or `patient_reported_diagnosis`; neither
  implies clinical verification. An episode-shaped concern is a patient note,
  separate from the existing immutable `CareEpisode` used for contribution scope.
- `ReportedPractitioner`: a workspace-local name, specialty, facility and notes.
  This is a patient's record of a doctor. It creates no person, account, OIDC
  identity, professional verification, membership or authorization capability.
- `CareTeamAssignment`: a doctor linked to an optional concern, with a care role,
  current/historical participation, partial start/end dates and notes. A null
  concern means general care. Only one active assignment for a given doctor and
  concern is allowed; archived assignments remain in history.
- Existing `CareCircleEntry` contacts appear alongside doctors. Family,
  caregiver and guardian labels remain reported relationships. Their separate
  explicit recipient-account linkage is preserved; it confers no authority.
- `CareHistory`: immutable, database-generated full revision snapshots and actor
  attribution. Originals, metadata assertions and grants are never rewritten by
  this slice.

## HTTP interface

All paths are under `/api/workspaces/{workspace_id}/care/`. `kind` is exactly
`concerns`, `practitioners` or `assignments`.

| Method and suffix | Request / response |
| --- | --- |
| GET `{kind}/` | `{items:[entry...]}`; includes active and archived entries |
| POST `{kind}/` | `{values,expected_revision:0}` → entry, 201 |
| POST `{kind}/{id}/` | `{values,expected_revision}` → corrected entry, 200 |
| POST `{kind}/{id}/status/` | `{status:"active" or "archived",expected_revision}` → entry |
| GET `{kind}/{id}/history/` | `{history:[{revision,created_at,snapshot}...]}`, newest first |

An entry contains `id`, positive `revision`, `status`, `updated_at`, `values`,
`provenance:"patient_reported"` and `access_effect:"none"`.

Exact `values` fields:

- Concerns: `title` (required, 180), `description` (1000), `kind`, `certainty`,
  `onset`.
- Practitioners: `name` (required, 160), `specialty` (120), `facility` (180),
  `notes` (500).
- Assignments: `practitioner_id` (required UUID), `concern_id` (UUID or null),
  `role` (required, 120), `participation`, `start_date`, `end_date`, `notes` (500).

Dates have exactly `{precision,year,month,day}`. Precision is unknown/year/month/day;
unused components are null. Complete dates must be valid calendar dates. A date
range is rejected only when even the earliest possible start exceeds the latest
possible end; partial dates never invent a known day. There are at most 200 saved
entries of each kind per workspace, including archived entries.

Unexpected fields (including `verified`, `recipient_id` and authority claims)
are rejected. A stale revision is 409 and does not write a snapshot. Foreign,
missing and unauthorized resources produce the same 404; unauthenticated APIs
are 401. Mutation requests require CSRF. Responses are private/no-store.

## Authorization and transactions

These patient-reported notes use the existing live `manage_profile` **and**
`read_workspace_records` capabilities. No additional grants are seeded and
revoked capabilities are not repaired. Both capabilities are checked on every
request; mutations lock workspace and authorization rows before resolving
linked objects and committing a revision plus audit event. There is no client
permission decision, name/email matching or inferred clinician authority.

PostgreSQL enforces same-workspace composite foreign keys, immutable workspace
bindings, patient-subject editor identity, monotonically increasing revisions,
calendar dates, range order, required names/roles, and one active doctor-concern
relationship. Trigger-generated history runs with a fixed search path under the
migration owner. The runtime role can read but cannot insert, edit, delete or
truncate history, and cannot delete care entries. Production uses PostgreSQL;
the SQLite local-test option does not provide these PostgreSQL guards/history.

Archiving a concern or doctor preserves existing associations and all revisions;
it does not revoke access grants. New links require active parents. Restoring
an archived assignment requires active parents and no duplicate active link.
Sharing revocation remains an explicit operation in the existing access tools.

## Frontend behavior

My Care includes Health Concerns, Care Team and Visit Selections. Edits keep a
frozen revision and draft through background refetches; a conflict disables
resubmission until the patient explicitly discards the draft and reloads.
Network errors retain input. Explicit cancellation and ordinary link navigation
warn about unsaved drafts; browser reload/close uses a before-unload warning.
Browser back/forward navigation can leave the form, but the draft and its frozen
revision are recovered when returning to My Care in the same patient context.
Recovery uses only that context's memory cache; signing out, losing authority or
changing contexts clears it. Forms do not persist private content in browser
storage. Typed responses, capability
gating, existing context-scoped request cancellation, focus handling, labelled
controls and confirmation dialogs are reused. No LLM is invoked for saving care
relationships. Current/historical participation is not an access indicator;
cards explicitly state that the relationship itself grants no record access.

## Verified identities and additional acting contexts: extension boundary

Professional verification is deliberately unavailable to patient mutation APIs.
A future verified practitioner identity needs a separate canonical practitioner
record, an explicit account binding, verifier identity, authoritative registry or
institution evidence, verification timestamps/status and revocation. An
affiliation needs an independently verified facility identity, practitioner
binding, role, validity dates and evidence. Caregiver/guardian authority similarly
needs independently established authority and separately scoped capabilities.
Name, email, a patient-entered facility, or an assignment must never create those
bindings. Such workflows require a trusted verifier and authority rules before
the server can offer clinician, guardian or caregiver acting contexts. The UI
continues to expose only the acting contexts authorized by the existing server.

The next implementation slice is the new secure-sharing and clinician
participation journey, built on the existing separate read and contribution
grants. Patient-reported relationships are ready to inform its presentation;
they must not become its permission source.
