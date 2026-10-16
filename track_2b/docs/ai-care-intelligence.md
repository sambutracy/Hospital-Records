# Journal hardening and reusable care intelligence

## Delivery status — 16 October 2026

Journal hardening and the shared evidence pipeline are implemented. History exploration and consultation follow-up extraction have authenticated UI/API/worker/review journeys, tested with mocked inference. Both new capabilities remain disabled by default (`CARE_INTELLIGENCE_ENABLED=0`) pending real worker verification. This is not evidence of clinical validation or measured model accuracy.

Base commit: `535b92423db3b8d5eb6925e2cbb7824dae4f6442`. This delivery is currently an uncommitted working-tree change; nothing has been pushed.

The active Journal correction is now `journal-interpretation-v6` / `journal-proposal-v2`, with deterministic source normalization and explicit abstention for unsupported optional fields. See [the current extraction contract and verification](journal-extraction-reliability.md). Earlier failure iterations below are historical evidence, not the current optional-field policy. The latest operator-reported v5 `dev-03` call still failed at `occurrence / required_quote_missing` in 41.0305 seconds; there is no live success claim for v6 yet.

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

## Journal failure diagnosis update

The reported task code `invalid_or_unsupported_output` came from a catch that collapsed several unrelated failures: non-`stop` generation (including the 350-token cap), malformed JSON, schema/citation rejection, relative-date parsing and severity checks. The worker already gave preflight expiry/draft changes and inference transport/configuration failures separate codes; unrelated database/persistence errors used the generic worker code. Since the task retained only the umbrella code and no raw output by design, the exact cause of that already-failed request cannot be reconstructed safely.

One concrete defect fits this synthetic input: `resolve_date` accepted “yesterday” only when the entire evidence quote was exactly that word (or a standalone variant). A valid verbatim quote such as “I had a headache yesterday.” therefore failed despite the date being clear. The resolver now accepts exactly one supported relative-day phrase within the cited quote and still resolves it from the trusted request timestamp and timezone. It rejects quotes containing multiple competing relative dates.

Future failures now have safe task codes for incomplete generation, malformed JSON, invalid output shape, citation mismatch, unsupported/ambiguous relative or explicit dates, unsupported/negated severity, unsupported time, and proposal persistence. A capped response records only an allowlisted finish reason, configured token ceiling and provider completion-token count. No source text, model response or provider error body is stored. Existing exact citation, severity, negation, review and manual-entry checks remain in force.

The regression passes the supplied fictional sentence through the Journal worker with a mocked Apertus response that cites the full first sentence, resolves “yesterday” to the trusted local date, preserves the 6/10 score and leaves the original narrative unchanged. Separate worker regressions prove that `finish_reason=length` at 350 tokens is classified as `generation_incomplete`, malformed JSON as `invalid_model_json`, and a quote absent from the source as `citation_invalid`. These are parser/worker regressions, not real inference results.

## Structured-output compatibility follow-up

The frozen `dev-03` report records that an HTTP/model response arrived, but it did not retain the finish reason, token usage, parsed fields or failure stage. Its exact rejection cannot be reconstructed from that report. Static contract review found a concrete schema mismatch: `validate()` requires a category citation, while `output_schema()` previously allowed the nested `evidence` object to omit every property. The schema now requires only `evidence.category`; occurrence, time and severity citations remain optional, and the date/time/severity values remain nullable. This is the minimal generation correction. The 350-token ceiling is unchanged because the saved `dev-03` report has no truncation evidence.

The pinned llama.cpp `server-b11429` receives `json_schema` and converts it to constrained grammar. Its schema builder represents required and optional nested object properties and expands union `type` arrays into alternatives; the grammar includes a JSON `null` primitive. The Comfort schema uses those forms. This source inspection supports compatibility for nested objects, optional properties and nullable values; it is not a live grammar-conversion or real-model test. The application validator remains authoritative after decoding.

The evaluator now runs through the production `evidence_pipeline.invoke()` response path. It records a safe stage for incomplete generation, invalid JSON, structural schema, citation, date, severity, model-response shape and other output validation. A received model response is recorded separately from an output accepted by the validator. Invalid-evidence counts include citation rejection or a validator-accepted output that misses the fixture's evidence target; unrelated parse/date/severity failures have `evidence_valid: null` and do not inflate that count. Fixture contents are unchanged.

Verification before the operator run: Python compilation, the frozen-corpus integrity check, and 32 targeted Journal/evaluator/evidence-pipeline tests passed on a new disposable PGlite database. The deterministic baseline remains field accuracy **0.8377** and exact-case accuracy **0.5909** over 22 nonempty cases. This execution environment cannot access Docker Desktop's named pipe (`npipe:////./pipe/dockerDesktopLinuxEngine`), so the operator ran the one-case PowerShell check below. It preserved existing reports and did not run the 23-case corpus.

The saved real `dev-03` report (`20261016T023857Z-66ca57fd.json`) shows one authenticated response in **24.4932 seconds**, no request failure, and one invalid output. Its safe failure code is `time_unsupported`; it is **not** a JSON, truncation, severity, date or citation failure. The fictional source says “this morning” but has no exact clock time, so any non-null model time fails the existing exact `HH:MM` citation rule. The report deliberately does not retain the proposed value or response body. `invalid_evidence_cases` is correctly **0**. The report's zero field/exact scores are failed-output scores, not a measured breakdown of accepted fields; there were **0** validator-accepted outputs.

Prompt `journal-interpretation-v2` explicitly asks Apertus to use `null` for time unless the source states an exact clock time, not to convert a part of day into a clock time, and to cite the clock string when present. It also makes the existing number-word severity rule and conservative date handling explicit. The evaluator uses the same registered production prompt; an unused duplicate prompt was removed. The fictional part-of-day regression proves a supported null-time proposal passes and an invented `09:00` remains rejected. The targeted isolated PostgreSQL suite passed **59/59** tests, and evaluator reporting tests passed **2/2**.

The operator's next real `dev-03` report (`20261016T024742Z-9002ea82.json`, prompt v2) received a response in **41.5604 seconds** with no request failure, but rejected it as `citation_invalid`. It correctly counts **1** invalid-evidence case and **0** validator-accepted outputs. The failed-output field/exact scores are both zero; no accepted-field accuracy is available. This code means an empty/non-verbatim quote or a missing required quote. The report does not identify its field or retain the quote. Citation checking precedes time, date and severity validation, so this result does not establish that the previous time problem was fixed.

Prompt `journal-interpretation-v3` added the missing general instruction that evidence quotes must be nonempty contiguous source substrings copied verbatim, including spelling, case, spaces and punctuation, and must not be paraphrased. Optional evidence should be included only for supported values. Citation diagnostics contain only the allowlisted evidence field (`category`, `occurrence`, `time` or `severity`) and reason (`quote_missing_or_invalid`, `quote_not_in_source` or `required_quote_missing`). The worker and evaluator preserve these labels without narrative or model output. Exact citation matching, the 350-token ceiling, patient confirmation and frozen fixtures remain unchanged. **33/33** targeted Journal, evaluator-reporting and shared-pipeline tests passed on disposable PostgreSQL before the prompt-v3 operator run.

The operator's prompt-v3 `dev-03` report (`20261016T030058Z-efec6bd1.json`) received a response in **50.8292 seconds**, with **0** request failures and **0** validator-accepted outputs. Its code is `severity_unsupported`; it correctly records **0** invalid-evidence cases. Exact citation and date validation finished before the severity failure; time validation follows severity and was not reached. The source has a spelled-out numeric severity that the deterministic validator accepts when cited in full. This report does not distinguish a wrong numeric type, an out-of-scale value, a missing severity quote, a quote omitting the scale, or a disagreement between value and quote. The raw response was not retained and those branches cannot be reconstructed from this saved report.

Prompt v3 was held fixed while this ambiguity was investigated. Severity diagnostics distinguish `value_not_integer`, `value_outside_scale`, `required_quote_missing`, `quoted_scale_missing`, `value_quote_mismatch` and `negated_scale`; time diagnostics distinguish `invalid_clock_format`, `required_quote_missing` and `value_quote_mismatch`. These are fixed labels, not the severity number or clock value. Acceptance logic is unchanged. **37/37** targeted tests passed on disposable PostgreSQL, covering every branch, explicit number-word and clock-time acceptance, negation rejection, worker diagnostic persistence, reporting and the diagnostic allowlist. The console summary includes `output_failure_diagnostics` so the operator does not need another report-reading command; a separate console privacy regression also passed.

The detailed prompt-v3 report (`20261016T030807Z-84809ea7.json`) establishes the exact branch: `severity_unsupported / severity / required_quote_missing`. Apertus returned a non-null, in-range integer severity but omitted `evidence.severity`. The response arrived in **31.5655 seconds**, with **0** request failures and **0** validator-accepted outputs. No output body was retained. The generation schema permitted an uncited numeric severity while the production validator required its citation; this mismatch caused the rejection.

The severity correction in `journal-interpretation-v4` used two complete `anyOf` alternatives: null severity with category evidence required, or integer severity with category and severity evidence required. The public proposal shape and validator are unchanged. The pinned llama.cpp builder [supports complete `anyOf` alternatives](https://github.com/ggml-org/llama.cpp/blob/b11429/common/json-schema.cpp#L217-L219); this avoids relying on conditional sibling keywords. The prompt explicitly requires the corresponding quote for each non-null supported field. The evaluator additionally records a SHA-256 digest of the output schema. The 350-token allowance is unchanged because no truncation was observed.

Verification before the v4 model run: **38/38** targeted Journal/evaluator/pipeline tests passed on disposable PostgreSQL. Eight independent AJV schema checks passed using the actual `output_schema()` definition, proving an uncited numeric severity is rejected, cited severity and null severity are accepted, and category evidence/quote objects/additional-field protections still apply.

The v4 operator report (`20261016T031629Z-f2f1a875.json`) received a response in **54.5366 seconds**, with **0** request failures and **0** validator-accepted outputs. Exact quotations, date and severity validation passed, then `time_unsupported / time / invalid_clock_format` rejected a non-null time that was not `HH:MM`. The generated clock value was not retained. The static schema still permitted arbitrary strings for time, so the generation contract did not match the stricter time validator.

The current generation contract is `journal-interpretation-v5`. The shared pipeline now supports an optional source-schema callback; existing history/follow-up clients retain their static schemas. For Journal, the exact saved narrative bounds clock eligibility before inference: no explicit 24-hour `HH:MM` means null time only; otherwise null or one of the distinct exact source clocks is allowed. This is a deterministic input constraint on Apertus generation, not an output repair, rule-baseline fallback, or inference retry. It does not choose a clock for the model. Every non-null severity and time requires its corresponding quote; their null alternatives omit orphan severity/time evidence. The public proposal shape, domain validator, patient confirmation, manual Journal path and token limit are unchanged.

The pipeline sends that exact contextual schema and records only its SHA-256 digest in safe provenance, not the schema or its source clock values. The evaluator retains a general contract hash plus the effective per-case schema hash and labels the method `source_clock_candidates_v1`. Scores from this version describe an Apertus workflow with deterministic clock eligibility, not unconstrained model extraction. The frozen deterministic baseline remains separate.

Twenty independent AJV checks passed against the actual general and contextual schemas: malformed times, uncited times, invented clocks when the source has none, and clocks outside the explicit candidate set are blocked, while cited exact times and null remain supported. Sixteen fast diagnostic/reporting/pipeline tests also passed. The complete targeted run then passed **89/89** tests on disposable PostgreSQL, including Journal, evaluator reporting, shared-pipeline dispatch, history/follow-up and existing assistant regressions. It verifies source-specific schema dispatch and hash-only provenance through the worker without changing other pipeline clients. No database migration is required for this contract correction. Native Docker inference and live grammar enforcement of the new contract remain unverified from this environment. Existing reports and frozen fixtures are preserved. The full 23-case evaluation, actual UI/worker verification and push remain pending.

```powershell
$compose = @('--project-directory', 'track_2b', '--file', 'track_2b/compose.yaml', '--file', 'track_2b/compose.local.yaml')
docker compose @compose build worker
if ($LASTEXITCODE -ne 0) { throw 'Worker image build failed.' }
$reportDir = Join-Path (Get-Location) 'track_2b/.runtime/journal-ai-eval'
New-Item -ItemType Directory -Force $reportDir | Out-Null
$reportsBefore = @((Get-ChildItem -LiteralPath $reportDir -Filter '*.json' -File).Name)
docker compose @compose run --rm --no-deps --volume "${reportDir}:/app/.runtime/journal-ai-eval" worker python src/tools/journal_ai_eval.py run --case-ids dev-03
$runExitCode = $LASTEXITCODE  # A rejected proposal exits 1 but still saves its report.
$latestReport = Get-ChildItem -LiteralPath $reportDir -Filter '*.json' -File |
    Where-Object { $_.Name -notin $reportsBefore } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($null -eq $latestReport) { throw 'No new report was saved; previous reports were preserved.' }
$report = Get-Content -LiteralPath $latestReport.FullName -Raw | ConvertFrom-Json
$report.summary | Select-Object transport_successes,validator_accepted_outputs,request_failures,invalid_responses,invalid_evidence_cases,field_accuracy,exact_case_accuracy,median_latency_seconds | Format-List
$report.results | Select-Object case_id,status,failure_category,failure_code,failure_diagnostic,validator_accepted,latency_seconds | Format-List
```

| Real-model check | Outcome | Accuracy / latency |
| --- | --- | --- |
| Earlier operator authentication diagnostic | Reported successful synthetic completion in trial container | 21.384 seconds; not a Journal benchmark |
| Actual authenticated Journal app/worker request | Earlier request reached processing but failed with `invalid_or_unsupported_output`; its exact historical stage was not retained | No accepted result |
| Real synthetic `dev-03` evaluation, prompt v1 | Authenticated response; rejected as `time_unsupported`, not an inference failure | 24.4932 seconds; 0 validator-accepted outputs |
| Real synthetic `dev-03` evaluation, prompt v2 | Authenticated response; rejected as `citation_invalid` | 41.5604 seconds; 0 validator-accepted outputs |
| Real synthetic `dev-03` evaluation, prompt v3 | Authenticated response; rejected as `severity_unsupported` | 50.8292 seconds; 0 validator-accepted outputs |
| Real synthetic `dev-03` evaluation, unchanged prompt v3 with detailed severity diagnostics | Authenticated response; numeric severity omitted its required quote | 31.5655 seconds; 0 validator-accepted outputs |
| Real synthetic `dev-03` evaluation, prompt v4 with severity dependency enforced | Authenticated response; rejected an invalid clock format after severity validation | 54.5366 seconds; 0 validator-accepted outputs |
| Real synthetic `dev-03` evaluation, contract v5 with source-bounded clock schema | Unattempted: operator verification required | Not measured |
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
docker compose @compose run --rm --no-deps migrate python src/manage.py test records.tests.test_journal_ai records.tests.test_journal_normalization records.tests.test_journal_eval_reporting records.tests.test_journal records.tests.test_evidence_pipeline records.tests.test_care_intelligence records.tests.test_assistant --settings=continuity.test_settings --noinput
```

If verification fails, preserve the safe failure state and existing reports. Disable the new features by setting `CARE_INTELLIGENCE_ENABLED` back to `0` and recreating app/worker. Do not reset volumes or regenerate credentials. Commit/push remains gated on recording the actual worker outcomes and required evaluation results.
