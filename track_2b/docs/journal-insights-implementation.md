# Journal and Insights: implementation contract

## First vertical slice

The existing React Journal placeholder becomes a private daily/list Journal for
personal notes and symptoms. This implements the foundation and first daily
journey from the supplied Journal/Insights specification. Insights remains a
placeholder until its source-aware projection is implemented; it does not invent
trends from document uploads.

The audit found existing `PatientHealthConcern`, `MedicationEntry`, `SourceVersion`,
`CareEpisode` and explicit packet/contribution grants. These remain the sources
of truth. No record, medication, concern or access registry is duplicated.

## Domain, provenance and authorization

- `JournalEvent`: stable UUID and workspace, typed note/symptom category, required
  narrative up to 2,000 characters, occurrence date, optional local minute/time
  zone/UTC instant, optional symptom severity 0–10, optional existing concern,
  original author, correction actor, revision and active/archived status.
  Category-specific severity is a typed column, constrained to symptoms; there
  is no unrestricted observation JSON payload.
- `JournalHistory`: database-generated immutable full revision snapshots,
  recording actor and transaction time. Direct runtime history writes are denied.
- `JournalDraft`: one private recovery draft per workspace. Its editor fields
  have an exact, bounded string schema, allowing incomplete writing without
  publishing invalid observations. It is mutable/discardable, separate from
  clinical history and never a model input. Correcting an entry records its
  target and baseline revision in the draft.

The authorization matrix is intentionally narrow:

| Actor / authority | Read, write, history, archive, draft |
|---|---|
| Active patient self membership with live `manage_profile` AND `read_workspace_records` | Allowed in that workspace |
| Another patient's membership | Denied |
| A recipient's document-read grant | Denied |
| An episode contribution authority | Denied |
| A reported doctor, relative, caregiver or guardian label | No access effect |
| Revoked membership/capability or expired session | Denied |

This follows the current private care-note capability contract. No new capability
is silently granted, and revoked permissions are not repaired. Future delegated
Journal access requires its own trustworthy authority and disclosure contract.

All APIs use the current Django session, CSRF checks and private/no-store headers.
All mutations lock the workspace and live authority before revision checks and
writes. PostgreSQL enforces patient authorship, immutable workspace/creator,
revision increments, valid calendar components, typed severity, same-workspace
concern/event links and append-only event/history behavior. There is no automatic
inclusion in packets, recipient views, contributions, exports or Apertus prompts.

## Temporal contract

`occurrence` is exactly `{precision,year,month,day}` with precision
`unknown|year|month|day`. Unknown components are null. Query-only bounds allow
partial dates to overlap a selected interval without inventing a displayed day.
The list can explicitly include undated observations. Their upload/recorded times
never substitute for occurrence dates.

A supplied local time needs an exact date and IANA time zone. Store the intended
local date/time, zone, fold and corresponding aware UTC instant. Reject skipped
daylight-saving times. Require an explicit first/second occurrence for repeated
times. A date-only entry has no invented midnight instant. The occurrence and
recorded/corrected timestamps are displayed separately.

## HTTP contract v1

Paths below are under `/api/workspaces/{workspace_id}/journal/`.

| Method / suffix | Contract |
|---|---|
| GET root | Required `from` and `to` ISO dates, at most 366 days; optional `category`, `concern`, `status`, `undated=true`, `page`; 30 entries and `next_page` |
| POST root | `{values,expected_revision:0,draft_revision:null or saved revision}` → entry, 201 |
| GET `{id}/` | Current entry, including archived entries |
| POST `{id}/` | `{values,expected_revision,draft_revision}` → correction; stale revision 409 |
| POST `{id}/status/` | `{status:active or archived,expected_revision}` → audited state revision |
| GET `{id}/history/` | Latest 100 revisions, newest first, with explicit `truncated` indicator |
| GET `draft/` | `{contract_version:1,draft:null or saved editor draft}` |
| POST `draft/` | `{fields,expected_revision,event_id,base_revision}` → saved draft |
| POST `draft/discard/` | `{expected_revision}` → explicit discard |

`values` has exactly `category`, `description`, `occurrence`, `time`, `timezone`,
`fold`, `severity`, `concern_id`. Optional time, fold, severity and concern are null.
Responses identify `provenance:patient_reported` and `visibility:private`.
Unexpected fields and invalid values are 400. Missing and unauthorized resources
are indistinguishable 404s. Draft conflicts also return 409 and do not overwrite
another tab's draft. Publication with an acknowledged draft verifies its revision
and target, writes the event and removes the draft in one transaction. Retrying a
consumed draft cannot duplicate publication.

## Frontend and draft recovery

Use Comfort's existing primitives, warm surfaces and scoped QueryClient. Offer
day navigation and an accessible chronological list, category/concern filters,
exact or approximate dates, optional details, correction/history and confirmed
archive/restore. An unrecorded day means unknown, never zero symptoms.

Editor changes autosave after 600 ms to the private server draft. Requests are
serialized and revision checked. Show whether the latest changes are acknowledged,
pending or failed. Keep draft and close waits for acknowledgement. Browser unload,
link navigation and context switching warn/block while writing is unacknowledged.
Explicit logout asks before discarding unacknowledged changes and remains possible
even if saving fails. A session-expiry warning tries to save before expiry; expired
authority never permits a late write. Reauthentication restores only server-saved
drafts after authorization is checked again. No sensitive browser persistence or
frontend token storage is introduced. Ordinary route back/forward also preserves
unacknowledged writing in the existing patient-scoped in-memory QueryClient;
logout, session expiry and patient-context teardown clear that memory. Network
failures, forced tab closure and
expiry before acknowledgement can still lose the last unsaved changes; the UI
states that risk rather than promising recovery it cannot provide.

Revision conflicts preserve the local writing and show the latest description,
category, occurrence/time zone, severity, concern and status.
The patient must explicitly select the latest revision as the correction baseline
and save again. Other changed fields remain visible in the editor; no automatic
merge is claimed. A conflicting recovery draft is displayed separately. The
patient explicitly confirms keeping it instead of the current writing, or
replacing it with the current writing. Replacement still checks the displayed
revision; a newer concurrent change is rejected again.

## Migrations and validation

`0015_journal_foundation` adds three tables only. `0016_journal_guards` adds scoped
foreign keys, temporal/revision/authorship guards, immutable history, indexes and
the bounded editor schema. Existing records and identity data are not rewritten.
The migration-owner startup configures runtime permissions. Reverse migrations
exist, but reverting the table-creation migration would delete Journal data;
production rollback must preserve/export new data first.

Run PostgreSQL backend tests with the repository's migration-owner test setup,
then `npm test` and `npm run build` in `frontend/`. New cases cover private notes,
optional severity, concern scope, stale corrections, archive/restore, immutable
SQL history, restricted runtime writes, date ranges/pagination, DST gaps/folds,
CSRF, actual share-recipient exclusion, session expiry and private draft recovery.
Client tests cover creation, correction conflict, history, drafts, failed saves,
archive, unauthorized context and automated accessibility. Real browser and final
regression results are recorded in the implementation report after execution.

## Following slices

Month/week calendars and date indicators; medication intake linked to existing
medications; wellbeing and explicitly enabled menstrual observations; optional
original-record links; unified paginated timeline; deterministic trends with
accessible tables; explicitly selected, versioned evidence for Apertus and care
preparation. Granular Journal sharing, delegation and guardianship require
separate authorization contracts. None is claimed by this first slice.
