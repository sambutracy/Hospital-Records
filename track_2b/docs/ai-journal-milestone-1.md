# Comfort — AI journaling milestone 1 design

Status: Patient-controlled backend/frontend slice and synthetic evaluation harness implemented. Trial-container Apertus authentication passed; app/worker path and live Journal evaluation remain to be verified.

## Implementation status (16 October 2026)

The working tree now adds `journal_interpretation` to the existing queue, with dedicated request, proposal and append-only review tables. A request can be created only for the patient's currently saved draft revision. The worker uses the configured Apertus endpoint, sends that narrative alone with a trusted server reference date/time zone, validates the JSON shape, checks quoted evidence against the original text, and records a proposal separately from `JournalEvent`. The generic assistant-task API excludes this task kind and its result contains only the proposal ID. The Journal editor has an explicit **Organize with Apertus** action, proposal polling, stale/expiry states, evidence-backed field checkboxes, and a separate action to copy selected fields into the private draft. The patient's original text remains unchanged, and the existing explicit save is still required to create a Journal event.

Temporary narrative and unreviewed proposal content expire after seven days; rejection clears proposal content immediately. The existing serial worker runs bounded cleanup hourly. Queue wait, model setup, inference, validation and end-to-end worker timing are available as task metrics. Request and proposal tables have scoped foreign keys and PostgreSQL guards; the runtime role cannot delete the request/proposal rows or mutate review history.

Verification on 16 October 2026: the app Docker build and TypeScript production build pass; all 43 frontend tests pass, including the AI proposal review journey; eight focused backend tests pass on an isolated SQLite test database; the 0017–0018 migration chain and custom guards passed against disposable PostgreSQL 18. The new corpus has 23 cases (12 development, 5 validation, 6 held-out), and the harness verifies all non-null evidence quotations against source text. Its narrow deterministic baseline scores 83.77% field accuracy and 59.09% exact-case accuracy over 22 non-empty cases. Those are baseline harness results, not Apertus results. The first direct request returned HTTP 401. A later trial-container diagnostic successfully authenticated model listing and a synthetic completion, which returned choices in 21.384 seconds. This does not yet verify the app's mounted credential or the Journal worker path. Do not describe the model as evaluated or clinically effective.

## Objective and boundary

Let an authenticated patient ask local Apertus v1.5 8B to organize one saved private Journal draft. The output is an unconfirmed, editable proposal for fields already supported by `JournalEvent`. It never creates or revises a Journal event by itself. The existing patient-authored description remains the publication source and is never rewritten by the model.

The first release supports `note` or `symptom`, occurrence date at existing year/month/day/unknown precision, optional exact local time and timezone, and numeric symptom severity only when directly stated. Health-concern IDs are not model-selected. Cause, diagnosis, medication identity/dose, treatment, reproductive events, sharing and other unsupported fields remain unknown or narrative-only. One request represents one Journal event; multiple experiences remain together in the patient's narrative.

## Current implementation audit

- Journal data is `JournalEvent`, with immutable `JournalHistory`, one mutable `JournalDraft` per workspace, optimistic revision checks and database triggers in `records/migrations/0015_journal_foundation.py` and `0016_journal_guards.py`.
- `journal.save_draft` and `journal.save` are the only supported draft/publication services. Both re-check capability under workspace locks. Save validates the exact field set, complete/partial dates, time zone, DST folds, concern scope, event revision and acknowledged draft revision. The DB writes a history snapshot and denies event/history deletion.
- Journal APIs use the authenticated OIDC session, CSRF on POST, `journal.authorize`, private/no-store responses and indistinguishable 404s for unavailable resources. Existing capabilities are `manage_profile` and `read_workspace_records`. Care relationship, packet-read and contribution labels are not Journal authority.
- Assistant work already has a single bounded serial scheduler (`process_records`), task lease/state transitions, actor/workspace bindings, live authorization at worker boundaries, safe failure codes, no automatic billable retry and one active request per kind. `AssistantTask` is not sufficient as the Journal persistence model: `AssistantSource` requires a `SourceVersion`, while Journal input is a private patient draft; generic `result` is not a reviewed Journal proposal; the existing closed task-kind and immutability rules need an explicit extension.
- The local 8B runner is a CPU-hosted llama.cpp server reached from Docker through `host.docker.internal`; configuration remains the existing local model endpoint. Current local config permits a 300-second model request and the serial worker grants bounded child/lease time. It must be profiled for this shorter prompt separately. The server's configured timezone is UTC; relative-date results must carry that trusted reference and may be resolved only by deterministic server code.

## Security verification gate (16 October 2026)

The GitHub screenshot showed four open Dependabot alerts in `track_2b/frontend/package-lock.json`. The default branch is commit `423b153` (`chore: update Storybook and Vitest dependencies to latest versions`), which updates Vitest to 4.1.11 and Storybook to 10.6.2.

| Finding | Affected component | Remediation and evidence | Residual risk |
|---|---|---|---|
| GHSA-82fw-gwwq-j7x9 / CVE-2026-84373, Moderate; two vulnerable lockfile paths | `@vitest/mocker` 3.2.4 and 3.2.7, pulled by Vitest/Storybook | Vitest 4.1.11 includes the patched mocker; Storybook 10.6.2 removes its old nested copy. `npm audit`: 0 findings. Frontend production build and Storybook build succeed. | Dependabot page refresh requires the commit to exist on the remote default branch. Dev-tool impact is limited to the development/build environment; no application endpoint is exposed by this advisory. |
| GHSA-5gmw-xhrv-c9v3 / CVE-2026-104848, Critical | Tinypool 1.1.1, worker-options prototype-pollution gadget | Removed from the resolved Vitest 4.1.11 dependency graph. `npm audit`: 0 findings. | No Tinypool package remains in the lockfile. |
| GHSA-85c8-ppgw-ccpr / CVE-2026-104849, Critical | Tinypool 1.1.1, `run()`-options prototype-pollution gadget | Removed from the resolved Vitest 4.1.11 dependency graph. `npm audit`: 0 findings. | No Tinypool package remains in the lockfile. |
| PYSEC-2026-1795, PYSEC-2026-1796, PYSEC-2026-2875, PYSEC-2026-2876, PYSEC-2026-196 and PYSEC-2026-3721; multiple severities | Local build virtualenv's pip 25.0.1; the Python base image's installer was not pinned | Local ignored environment upgraded to pip 26.2.1; `track_2b/Dockerfile` now pins pip 26.2.1 before installing runtime requirements. Pinned runtime and ecosystem requirement audits and a fresh app-image build pass; local audit after upgrade reports no known findings. | The local pip remediation and Dockerfile change are in the current working tree until committed. Base-image OS packages were not independently CVE-scanned; `python:3.12-slim` remains a mutable tag. |

Audit commands: `npm audit`; `pip-audit --no-deps --disable-pip -r track_2b/requirements.txt`; same command for `requirements-ecosystem.txt`; `pip-audit --local` after pip upgrade. Regression/build evidence: npm audit is clean; frontend production build and tests pass; the app Docker build succeeds and pins pip 26.2.1. Focused Journal AI tests cover private proposal persistence, source-text isolation, evidence/date/severity validation, added-field rejection, stale-draft refusal, review clearing and patient isolation. They do not substitute for real inference. No full penetration test or OS-image scan was run. Do not load genuine patient data until live model access and deployment-image review are complete.

## Proposed persistence and task lifecycle

Reuse the existing AssistantTask queue, worker lease and serial scheduler, but add a new closed `journal_interpretation` kind with its own tables and service. Do not put Journal text in `AssistantTask.parameters`, generic logs, or `AssistantSource`.

- `JournalAIRequest` is one-to-one with its queue task. It binds workspace, requesting actor, exact `JournalDraft` ID/revision and edited-event ID/base revision, immutable input digest, input snapshot, schema/prompt version, trusted `as_of` instant and timezone, expiry/retention state and stage timings. It contains no client-selected workspace/task authority beyond server-validated route IDs.
- `JournalAIProposal` is one-to-one with a completed request and holds only strictly validated suggestions, exact evidence spans, unknowns and ambiguity flags, model identity and review state. It is explicitly unconfirmed and has no `JournalEvent` write path.
- `JournalAIReview` is append-only and records accepted, edited, rejected or abandoned, actor and reviewed proposal. The existing Journal save records the eventual event/revision separately; the proposal review does not publish an event.
- The generic task's JSON result contains only the proposal UUID and safe state code. Queue records never copy patient text. Journal request/proposal tables are accessible only through the private Journal service and the worker role required for processing; composite workspace/task foreign keys and DB triggers enforce scope, immutable bindings and legal lifecycle transitions.
- Worker transitions use the existing one-at-a-time runner and lease. Add queue kind filtering and request handling to the same child, with checks before context prep, immediately before inference and before proposal persistence. Revocation or cancellation prevents subsequent processing/publication. A model call already in flight cannot be recalled; its output is discarded if authority is gone.
- Request snapshots are private temporary data. Current code uses a seven-day expiry for requests and proposals; rejection clears proposal content immediately, and the worker clears its temporary request snapshot after inference. Expired queue entries become terminal safe failures and unreviewed proposal content is cleared by the worker cleanup. The running queue calls bounded cleanup hourly; it never deletes Journal records or modifies volumes.

This design avoids a second scheduler while keeping Journal input and proposal lifecycle distinct from document-grounded assistant results. Before Phase 2, validate the assistant-task DB guards and restricted app/worker grants against a migration in disposable PostgreSQL.

## Versioned model contract

The current server contract is `journal-proposal-v1`; it uses exact top-level keys and rejects additional properties. The server computes offsets after verifying each quoted span is an exact substring, avoiding reliance on model-generated Unicode offsets. The more descriptive JSON below remains the intended documentation shape; it is not byte-for-byte the current inference schema.

```json
{
  "schema_version": "comfort.journal-proposal.v1",
  "abstained": false,
  "category": {"value": "symptom", "evidence": {"start": 0, "end": 8, "quote": "headache"}},
  "occurrence": {
    "precision": "unknown",
    "year": null,
    "month": null,
    "day": null,
    "evidence": null,
    "relative_phrase": null
  },
  "time": {"value": null, "evidence": null},
  "severity": {"value": 6, "evidence": {"start": 49, "end": 63, "quote": "six out of ten"}},
  "unknowns": ["cause", "medication_identity"],
  "ambiguities": []
}
```

Each returned span has integer half-open offsets and a quote; the server verifies that the quote occurs in the exact snapshot and computes Unicode code-point offsets itself. A field with no direct support must be null/unknown and have no invented span. Severity is an integer 0–10 only when the narrative directly states a number or number word on a ten-point scale; qualitative intensity is never mapped to a number. Exact dates and partial dates (ISO year/month or English month-name/year) need their own source span. Relative dates support explicit English today/yesterday phrases plus the server-provided reference date/time zone; other relative or ambiguous expressions remain unknown. The model cannot select a concern ID or author any database ID, navigation URL, diagnosis, medication, treatment, causal claim or new event category. The server normalizes to existing Journal draft fields and keeps the suggestion unconfirmed.

Prompt version `journal-interpretation-v1` treats all user content as untrusted data, puts it in a separate user message, supplies no tools/history/profile/record evidence, avoids prompt caching and demands abstention for unsupported interpretations. The request asks for constrained JSON Schema output and strict server validation always applies. Patient text is capped at 2,000 characters; output is capped at 350 tokens. No model response or exception body is logged.

## Authorization and HTTP contract

All operations require the same live patient-self capabilities as Journal: `manage_profile` and `read_workspace_records`, plus `requested_by == current user`. No caregiver, recipient, provider-contribution or packet permission grants AI access. Every lookup filters on workspace and task/request owner. Unavailable/foreign IDs return the same 404; anonymous requests return 401; mutations require same-origin CSRF.

Endpoints under `/api/workspaces/{workspace_id}/journal/ai/`:

| Operation | Contract |
|---|---|
| `POST requests/` | Explicitly start assistance for the currently saved draft: `{draft_revision}`. Server reads text from that exact draft, binds event/base revision, snapshots text and trusted temporal reference, returns queued request ID. No client-supplied narrative or other records. |
| `GET requests/` | List the current actor's ten most recent private requests for resume/polling; opening Journal does not invoke inference. |
| `GET requests/{request_id}/` | Live authorization/ownership check; returns bounded status, timing, safe error or ready proposal and stale flag. |
| `POST requests/{request_id}/` | Record reject/abandon or apply selected patient-reviewed fields to the matching private draft. Revalidates authority, owner, proposal, draft revision and original text. The existing `journal.save` remains necessary to publish; no inference path writes `JournalEvent`. |

Cancellation and a separate published-event link are not implemented in this slice. Generic assistant cancellation deliberately rejects this task kind.

One active request per actor/workspace. Bounded server-side queue and request rate limit. No retries that incur model calls. A new request requires a new explicit action. Polling reads state only. Protected responses use `private, no-store`.

## Draft and publication rules

The AI action is offered only after the current private draft save is acknowledged. The request captures an immutable snapshot/digest and draft revision. Editing while it runs is allowed; it marks the result stale. A stale proposal can be inspected against its captured text but cannot populate or publish into the newer draft. The patient may explicitly re-run against the current saved draft.

The review screen keeps the original narrative visible and unchanged. Every suggestion is optional and editable; no suggestion must be accepted. Applying accepted suggestions only populates the current editor/draft after an explicit patient action and a fresh revision check. Final Save still uses the existing `journal.save` confirmation and revision workflow, which records patient-authored history. Reject, close, timeout, model failure and reauthentication never publish. Manual Journal remains usable with inference unavailable.

## Performance and failure states

Measure queue wait, model setup, generation, validation, total, prompt/completion tokens and model identity separately. Current task payload exposes those timing metrics when available. Compare cold and warm CPU runs against the existing local 8B endpoint. Do not place this task ahead of currently executing work or retry automatically. Use the existing configured request/child/lease bounds, and expose `waiting_model`, `queued`, `processing`, proposal, stale, expired and safe-error states in Journal. Failure leaves the editable draft untouched and offers manual save. Do not claim that CPU inference is fast until repeated measurements demonstrate it.

## Evaluation and delivery gates

Use the versioned fictional corpus under `data/journal-ai-v1/`; never edit frozen Apertus metadata or synthetic healthcare fixtures. Expected values are authored independently. Version 1 splits into development (12), validation (5), and held-out test (6). It covers numeric and qualitative severity, exact/partial/relative/ambiguous dates, negation, uncertainty, unspecified medication, family vs patient history, multiple symptoms, recovery, chronic-care wording, Kenyan English, mixed language, prompt injection, contradiction and empty input. Empty input is a pre-inference rejection. `python src/tools/journal_ai_eval.py check` verifies fixture integrity and produces the deterministic baseline; `run --split development|validation|test|all` sends only fictional cases to the configured Apertus endpoint and records aggregate metrics under ignored `.runtime/`. A status-only diagnostic in the local `trial` container succeeded for authenticated model listing and a synthetic completion (21.384 seconds). That verifies the local key-file flow in `trial`, but not the app container mount or actual Journal worker path. Do not claim a Journal score or speed until the staged worker-path and evaluation runs complete. Include only synthetic strings and no external patient data.

Score strict-schema rate; field precision/recall/exact match; evidence-span validity; unsupported-value invention; date/negation/uncertainty correctness; abstentions; corrections/rejections; manual-vs-AI authoring time; p50/p95 queue/generation/total latency; token counts and memory. Compare manual Journal, a deterministic extraction baseline, and Apertus. Do not grade Apertus against outputs generated by Apertus. Do not claim clinical accuracy or improvement from a schema/build test.

Phase 2 security tests must cover self authorization, cross-workspace and share-recipient denial, ownership, revocation before prep/inference/persist/retrieve/publish, CSRF, strict schema and span validation, injected narratives, cancellation/expiry, worker lease, request deletion, context isolation, no logs, no auto publication, stale draft/event conflict, immutable history and atomic accepted publication. Use disposable PostgreSQL and fictional users only; never reset existing Docker volumes.

## Residual deployment constraints

The Journal AI workflow, review interface and reproducible evaluation harness are implemented. The later trial-container check succeeded, but this Codex session cannot verify the running app/worker image IDs, mounted-file status, database migration state, or a real Journal request: Docker Desktop denied the non-elevated CLI access to its named pipe. No elevated retry or credential access was attempted. An OS package CVE scan and full application penetration test remain open. Do not load genuine patient data or describe Comfort as clinically validated.

## Local Apertus authentication investigation (16 October 2026)

The local Compose source sets both app and worker to `http://inference:8080/v1` with model `Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF`, sets `LLM_API_KEY_FILE=/run/secrets/apertus_key`, and bind-mounts `.runtime/local-model/server.key` read-only at that path. The model server reads the same host file through `/models/server.key` using `--api-key-file`; its health check sends a bearer header from the corresponding `auth-header.txt`. The host-side default `server.key` exists and is readable by the current Windows process, verified without reading its bytes.

Both the Journal worker and the existing assistant use `intelligence.trial.configuration()`, `available_models()` and `request_json()`. The configuration loader reads the configured key file and lets it override the intentionally empty `LLM_API_KEY`; the shared request helper adds `Authorization: Bearer …`. Unit coverage verifies this precedence with fictional keys. This source-level comparison shows no Journal-specific authentication divergence.

The operator reports that the status-only diagnostic returned `models_auth=ok`, `completion_auth=ok`, the configured model was listed, and the synthetic completion returned choices in 21.384 seconds. This confirms authentication through the local `trial` container. The earlier direct HTTP 401 may have come from an older image or request path; it does not prove that the credential is rejected. The running app/worker image IDs, worker's mounted-file status, database migration state and actual Journal request still need verification. Docker's named-pipe access is denied to this Codex session, so no elevated retry or alternate credential access was attempted.

```powershell
$compose = @('--project-directory', 'track_2b', '--file', 'track_2b/compose.yaml', '--file', 'track_2b/compose.local.yaml')
docker compose @compose build app worker migrate
if ($LASTEXITCODE -ne 0) { throw 'Image build failed.' }
docker compose @compose run --rm migrate
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
docker compose @compose up --build --detach --wait app worker
if ($LASTEXITCODE -ne 0) { throw 'App/worker startup failed.' }
docker compose @compose ps app worker inference database
docker compose @compose images app worker
docker compose @compose run --rm --no-deps migrate python src/manage.py showmigrations records
docker compose @compose exec worker python -c "import os,pathlib; k=os.environ.get('LLM_API_KEY_FILE',''); p=pathlib.Path(k) if k else pathlib.Path('/__comfort_missing__'); print({'base_url':os.environ.get('LLM_BASE_URL'), 'model':os.environ.get('LLM_NAME'), 'key_file_configured':bool(k), 'key_file_exists':p.is_file(), 'key_file_readable':p.is_file() and os.access(p,os.R_OK), 'legacy_key_env_populated':bool(os.environ.get('LLM_API_KEY'))})"
```

The `migrate` service applies pending migrations without resetting volumes. `up --build` recreates stale app/worker containers and waits for their dependencies and health checks. To verify an actual app-to-worker request, sign in as a fictional synthetic patient, save a short fictional Journal draft, and invoke the Journal AI organization action once. Confirm that a completed, reviewable proposal appears in the app. Do not use real health information. This traverses authenticated app request, persisted task, worker, local endpoint and proposal retrieval. If it fails, preserve the safe UI error and inspect only bounded service logs with `docker compose @compose logs --tail 100 app worker`; do not print environment variables or credentials.

The evaluator needs the application dependencies and settings, so run it in the worker image, rather than the minimal authentication trial image. Preserve its timestamped reports with a host mount:

```powershell
$reportDir = Join-Path $PWD 'track_2b/.runtime/journal-ai-eval'
New-Item -ItemType Directory -Force $reportDir | Out-Null
```

The five-case Apertus gate below covers explicit numeric severity, an ambiguous date, negation/family-history separation, unspecified medication information and a prompt-injection attempt requesting an unsupported diagnosis. The evaluator saves each timestamped outcome under ignored `.runtime/journal-ai-eval` and returns nonzero for incomplete cases, invalid outputs or request failures:

```powershell
docker compose @compose run --rm --no-deps --volume "${reportDir}:/app/.runtime/journal-ai-eval" worker python src/tools/journal_ai_eval.py run --case-ids dev-03 dev-07 dev-09 dev-08 val-04
```

Proceed to the full run only if all five produce valid schema and evidence, exact expected fields, no unsupported values, and no request failures. The full pass includes those five again by design and covers the complete frozen 23-case corpus:

```powershell
docker compose @compose run --rm --no-deps --volume "${reportDir}:/app/.runtime/journal-ai-eval" worker python src/tools/journal_ai_eval.py run --split all
```

The evaluator continues after per-case failures, records failed and not-attempted case IDs, and reports model-response field/exact-case accuracy, invalid outputs, request failures and latency separately from the deterministic baseline. It never overwrites prior timestamped reports. After reviewing these results, run focused regressions with `docker compose @compose run --rm --no-deps migrate python src/manage.py test records.tests.test_journal_ai --settings=continuity.test_settings --noinput`, then run `make test` from the repository root. Push only after the app-worker request, required evaluation runs and targeted regressions have completed and been recorded.
