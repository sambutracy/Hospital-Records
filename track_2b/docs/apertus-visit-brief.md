# Apertus visit brief

Comfort prepares a private, source-linked brief around five questions: why the
patient is seeking care, what has happened, what matters for this conversation,
what needs confirmation, and what the patient wants from this visit.

## Information hierarchy

Only supported sections are populated, in this order:

1. Purpose of this visit, including the patient's current concern.
2. Allergies and medication context.
3. Relevant conditions and history.
4. Symptoms and changes over time.
5. Key investigations and findings.
6. Decisions and documented follow-ups.
7. Daily functioning and support.
8. Care coordination.
9. Patient priorities and questions.
10. Recorded health basics, when available.

The patient can add their current focus, goals and questions before requesting
the brief. A complaint in an old document is attributed to that source rather
than being substituted for the patient's current purpose.

## Purposeful model task and source safety

The old local overview protocol supplied at most two passages per source,
2,400 characters overall and four selections. It could return repeated medicine
paragraphs while never seeing later-page findings or plans.

The new explicit `visit_brief: true` contract uses the existing asynchronous
`packet_overview` task and shared evidence pipeline. Apertus evaluates relevance
to the current visit, organizes evidence into the prioritized areas, and selects
up to 28 distinct facts/passages across those areas. It sees dates and provenance.
The request is one bounded, schema-constrained generation with 700 output tokens,
temperature zero and no automatic retries. Existing model endpoint and mounted
authentication-file handling are reused.

The model returns candidate IDs and area assignments. Comfort expands those IDs
into the complete saved source statements, so the model cannot rewrite a dose,
invent an investigation, remove a negation, convert family history into the
patient's diagnosis, or invent a patient goal in the displayed clinical text.
Explicit source headings constrain area assignment. Unheaded passages still need
human review for relevance and categorization. The brief is structured extraction
and organization, not independent clinical reasoning or validated medical advice.

Every source quotation is checked against the immutable document chunk. Longer
passages retain all their words through multiple individually bounded citations.
Identical passages from different records become one item with all supporting
originals retained. Source dates are displayed separately from the draft date.
Historical plans stay plans: the brief does not assert that a procedure occurred
or that an old instruction still applies. Differing medicine accounts are kept
with their provenance; there is no automatic reconciliation or adherence claim.

## Optional patient context

The patient explicitly chooses profile, medications, Journal, and/or care context.
Each option defaults off. The snapshot includes only its allowed fields:

- Profile: reported blood group and gender. Names, identity documents, birth date,
  contacts and Care circle are excluded from inference.
- Medicines: at most 20 active entries, ordered by reported visit date. Prescribed,
  reportedly taken, not taken and unknown remain distinct; active storage status
  does not mean a medicine is currently taken.
- Journal: at most 12 active observations ordered by reported occurrence, with
  severity, negation, uncertainty and partial dates preserved.
- Care: at most eight concerns and eight care relationships, retaining reported
  certainty, participation and dates. A care relationship grants no access.

Unknown dates sort after known dates; upload time is never a clinical date.
Coverage exposes omitted entries. Immutable Journal/care history is used where
available. The profile/medication rows are locked while captured; the resulting
allowlisted snapshot and its digest are stored in already-immutable task
parameters. Later changes produce a stale-context notice without rewriting the
saved draft. Documents remain constrained to the approved packet by existing
PostgreSQL guards. This extension requires no new database migration.

Record-read and packet-preparation authority are always required. Private context
also requires profile authority, and medication context requires medication
authority. The application rechecks these permissions on result reads, task
listing, before inference, and before persistence. Revocation hides the draft and
prevents a newly generated result from being saved. A draft does not modify a
packet, Journal, prescription, sharing grant, appointment or clinical record.

There is currently no structured appointment lifecycle or dated height/weight
model. Such information can be surfaced when explicitly written in a selected
report. Missing measurements, appointment outcomes and follow-up completion stay
unknown. No invented data fills an empty section.

## Evidence bounds

The new document snapshot allows up to 16,000 extracted characters per source,
shared fairly within the existing 48,000-character packet budget. The planning
stage uses a smaller character-bounded pool with at most 80 candidate passages,
balanced across clinical areas. Input truncation drops incomplete trailing
sections. Whole sections exceeding 1,000 characters and ambiguous page
continuations are omitted rather than detached from their qualifications. The UI
shows omitted-passage counts, shortened-source counts and scope limits. OCR and diagnostic image analysis
are unchanged; image-only packets still require readable report text.

## Verification and model evaluation

The separate authored fictional corpus is
`data/visit-brief-evaluation-v1.json`. It covers a multi-page hip-care note,
duplicate medicine passages, conflicting prescription/use accounts, and
family-history/negation/unknown-measurement evidence. Existing frozen corpora and
reports are not changed. Run the deterministic planning baseline separately:

```powershell
python track_2b/src/tools/visit_brief_eval.py --baseline
```

The evaluator uses the production planner, schema and validator. Reports separate
transport success, accepted output, request failures, invalid output, unattempted
cases, section coverage, authored fact accuracy, exact-case accuracy, duplicate
passages and latency. Deterministic baseline scores are not Apertus scores. These
four cases are development screens, not a representative clinical benchmark.
Safe reports retain hashes, fixed failure labels and selected candidate IDs;
they do not save patient narratives, model response bodies or credentials.

Targeted tests cover app-to-worker dispatch with mocked inference, source
integrity, immutable snapshots/results, cross-patient isolation, revocation before
and during generation, later profile changes, exact citations, inline headings,
long passages, unknown dates, deduplication and UI input/rendering contracts.

On 16 October, the broader assistant/shared-pipeline run passed 70 tests on
disposable PostgreSQL 18.3 (PGlite). The final affected run passed 40 tests,
including the added page-scope safeguards. The frontend suite passed 53 tests;
after adding explicit abstention handling, its affected 16 tests also passed.
TypeScript, ESLint and the production build passed. The deterministic four-case
development screen retained all authored fact/section targets with zero duplicate
passages. These are software and deterministic screening results: no new live
Apertus response, model accuracy or model latency is claimed. Docker Desktop's
named-pipe API was inaccessible from the agent environment.

## Update the local running app

From `D:\Hospital`, rebuild both services so the app and worker use the same
implementation. Existing volumes and credential files are retained. This feature
adds no migration.

```powershell
$compose = @('--project-directory', 'track_2b', '--file', 'track_2b/compose.yaml', '--file', 'track_2b/compose.local.yaml')
docker compose @compose build app worker
if ($LASTEXITCODE -ne 0) { throw 'App/worker build failed.' }
docker compose @compose up --detach --wait --no-deps app worker
if ($LASTEXITCODE -ne 0) { throw 'App/worker update failed.' }
```

Existing drafts retain their previous format. Request a new brief in My Care to
use the new contract. Start with one fictional live model case, not the complete
Journal corpus:

```powershell
$reportDir = Join-Path (Get-Location) 'track_2b/.runtime/visit-brief-eval'
New-Item -ItemType Directory -Force $reportDir | Out-Null
docker compose @compose run --rm --no-deps --volume "${reportDir}:/app/.runtime/visit-brief-eval" worker python src/tools/visit_brief_eval.py --live --case-ids visit-01
```

The saved timestamped report records failures as well as successes. Do not rerun
an expensive case merely to erase a failed result. Actual local Apertus latency,
selection quality and live schema compatibility require this operator run; mocked
worker tests and deterministic fixture checks do not establish them.
