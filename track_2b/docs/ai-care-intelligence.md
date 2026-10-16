# Journal hardening and reusable care intelligence

## Delivery status — 16 October 2026

Journal hardening and the shared evidence pipeline are implemented. History exploration and consultation follow-up extraction have authenticated UI/API/worker/review journeys, tested with mocked inference. Both new capabilities remain disabled by default (`CARE_INTELLIGENCE_ENABLED=0`) pending real worker verification. This is not evidence of clinical validation or measured model accuracy.

Base commit: `535b92423db3b8d5eb6925e2cbb7824dae4f6442`. This delivery is currently an uncommitted working-tree change; nothing has been pushed.

## Stage 0 repairs

- Acceptance verifies the preserved original narrative against its immutable SHA-256 digest after the transient input snapshot is cleared.
- Migration 0019 retains the historical draft UUID without a live foreign key that prevents draft deletion. Historical request scope is checked at creation; later task updates do not require the draft to remain at its original revision.
- Stale or deleted drafts cannot accept suggestions, but their requests can be rejected or cleaned up without changing patient writing.
- Expiry cleanup excludes in-flight and already-cleared rows before applying its batch limit. Leases are checked before inference and again before publication.
- All 33 Journal workflow regressions passed on disposable PostgreSQL before introducing the shared pipeline.

## Shared pipeline and boundaries

`records/evidence_pipeline.py` registers bounded task specifications, immutable evidence, exact citations, live authorization/lease checkpoints, strict structured-output validation and safe timing provenance. Journal, history and follow-up tasks reuse `AssistantTask` and the existing worker scheduler. All model calls use the established local `intelligence.trial` configuration and authentication helpers; credentials are never persisted in task provenance. There are no automatic inference retries.

The additional persistence is limited to immutable evidence snapshots and explicit private review outcomes. Migrations 0020–0021 enforce workspace/type bindings, snapshot digests, packet membership and append-only evidence/reviews. Existing domain histories and permissions remain authoritative.

History exploration requires an explicit date range (maximum 366 days) and up to 12 explicitly selected revisions. It supports published Journal history, written document versions, patient-reported medication entries, concerns and episode groupings. Unknown dates require explicit inclusion. Partial dates, source attribution and medication-use status are preserved. Browse results are bounded to 50 per source type and disclose their coverage limit. Extracted text is bounded to 1,000 characters per source and 18,000 serialized context characters overall; truncation is disclosed.

Follow-up extraction uses written sources from the frozen consultation packet. It identifies quoted documented requests, questions to ask and ambiguous instructions. It cannot read imaging pixels, create appointments, share records, schedule reminders or change care records. Both tasks return source excerpts rather than generated clinical conclusions. Citation validation expands excerpts to their complete source sentence to retain negation, family subjects and uncertainty. Review can keep, edit or reject a private planning draft while retaining original citations.

The UI is integrated into existing Insights and Consultation pages. Tasks are actor-private, results recheck current authority, and the generic assistant routes exclude these task kinds. No model request starts on page load.

## Verification evidence

The combined backend run passed **87/87 tests** on a fresh in-memory PostgreSQL 18.3 engine (PGlite). It covered Journal acceptance/publication, historical draft lifecycle, PostgreSQL guards and runtime-role restrictions, pipeline bounds/citations, authorization and revocation, care task review, packet isolation, expired leases and existing assistant regressions. This verifies PostgreSQL behavior in the isolated test engine; native Docker deployment and concurrent production workloads remain unverified.

Frontend verification passed **46/46 tests across eight suites**, TypeScript checking, lint of the new care-intelligence feature and the production Vite build. The new mocked journeys cover exact revision selection, one explicit inference request, cited editable private review, frozen-packet extraction, rejection and the default-off gate. Axe checks passed with color contrast excluded from jsdom; existing dedicated contrast tests also passed. The runner emitted jsdom canvas warnings and Rollup dependency-comment warnings, but neither failed verification. Dependencies were restored from the unchanged lockfile with install scripts disabled. Migration model consistency reported no changes; checking the running application's migration history remains an operator step.

The frozen 23-case corpus integrity check passed. Its deterministic baseline scored 22 nonempty cases: field accuracy **0.8377**, exact-case accuracy **0.5909**. These scores are not Apertus results.

| Real-model check | Outcome | Accuracy / latency |
| --- | --- | --- |
| Earlier operator authentication diagnostic | Reported successful synthetic completion in trial container | 21.384 seconds; not a Journal benchmark |
| Actual authenticated Journal app/worker request | Unattempted in this session: Docker named-pipe access denied | Not measured |
| History exploration app/worker request | Unattempted | Not measured |
| Follow-up app/worker request | Unattempted | Not measured |
| Five-case gate and complete 23-case Apertus evaluation | Unattempted; existing reports preserved | No new Apertus scores |

Mocked test successes must not be entered as successful real Apertus responses. The deterministic baseline and frozen corpus remain separate from model outcomes. The evaluator records selected IDs, request failures, invalid outputs, unattempted cases, field accuracy, exact-case accuracy and latency in new timestamped reports.

## Operator deployment and remaining checks

From `D:\Hospital` in PowerShell, use the existing local model and volumes:

```powershell
$compose = @('--project-directory', 'track_2b', '--file', 'track_2b/compose.yaml', '--file', 'track_2b/compose.local.yaml')
docker compose @compose build app worker migrate
if ($LASTEXITCODE -ne 0) { throw 'Image build failed.' }
docker compose @compose run --rm migrate
if ($LASTEXITCODE -ne 0) { throw 'Migration failed.' }
docker compose @compose up --detach --wait app worker
if ($LASTEXITCODE -ne 0) { throw 'Startup failed.' }
docker compose @compose images app worker
docker compose @compose run --rm --no-deps migrate python src/manage.py showmigrations records
```

First verify one explicit Journal request as a fictional patient through the actual application. Then enable the new journeys for synthetic verification in both services:

```powershell
$env:CARE_INTELLIGENCE_ENABLED = '1'
docker compose @compose up --detach --wait app worker
```

In Insights, choose a date range and exact fictional source revisions, run once, inspect citations and keep/edit/reject the private draft. In Consultation, use a frozen fictional packet containing written follow-up instructions, invoke extraction once and review its citations. Verify that none of these actions publishes a Journal event or schedules/shares anything. Capture each task UUID from Request details and report safe status/timings only:

```powershell
docker compose @compose exec worker python src/manage.py report_ai_verification --task-id REPLACE_WITH_TASK_UUID
```

Run the staged evaluation commands in [the Journal verification guide](ai-journal-milestone-1.md). Use the worker image, which includes Django and application settings; bind the report directory so reports survive container removal. Run the complete corpus only after reviewing the five-case gate. Do not repeat expensive inference merely to reproduce an already recorded outcome.

Targeted native PostgreSQL regressions:

```powershell
docker compose @compose run --rm --no-deps migrate python src/manage.py test records.tests.test_journal_ai records.tests.test_journal records.tests.test_evidence_pipeline records.tests.test_care_intelligence records.tests.test_assistant --settings=continuity.test_settings --noinput
```

If verification fails, preserve the safe failure state and existing reports. Disable the new features by setting `CARE_INTELLIGENCE_ENABLED` back to `0` and recreating app/worker. Do not reset volumes or regenerate credentials. Commit/push remains gated on recording the actual worker outcomes and required evaluation results.
