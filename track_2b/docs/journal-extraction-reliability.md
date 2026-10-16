# Journal extraction reliability correction

## Scope and current outcome

`journal-interpretation-v6` / `journal-proposal-v2` adds a small pure source-normalization module to the existing Journal worker. It reuses the same request, proposal, review, authorization, immutable-history and inference mechanisms. It requires no database migration, credentials change, new provider or automatic retry.

The operator's latest real frozen `dev-03` call received a response but failed `evidence_quotation / citation_invalid / occurrence / required_quote_missing` after **41.0305 seconds**. Earlier real attempts failed at time, citation and severity checks. These results remain failures. The new method has mocked verification only until the single live check below is run.

## Root causes found in the uncommitted implementation

- The generation schema allowed occurrence precision and numeric date components without coupling them to an occurrence quote. “This morning” could therefore become an invented exact date.
- Occurrence resolution trusted a quoted date expression but did not compare supplied model year/month/day values against it. Contradictory values could be silently replaced by the resolved quote.
- Category, occurrence, clock, severity and quotation checks were one failure chain. Any unsupported optional field discarded the whole proposal, including valid source evidence.
- Schema constraints on severity/time reduced individual error paths but did not make extraction context reliable. Number-word severity and explicit dates/clocks are better normalized from exact source spans.
- The review UI displayed only evidence-backed checkboxes but copied every default-selected field, including unknown fields without evidence. That could clear a patient's manual date/time.

## Current contract

| Field | Proposal rule |
| --- | --- |
| Category | Apertus supplies `note` or `symptom` and a mandatory exact source quote. Missing/forged category evidence, extra output fields such as a diagnosis, and detected negated/hypothetical/family symptom context still hard-fail. |
| Occurrence | Deterministic source spans support valid ISO dates, ISO year-month, English month/year, temporally introduced years, and literal today/yesterday/day-before-yesterday using the trusted request timezone/date. Partial precision stays partial. “This morning”, vague dates, invalid calendar dates, uncertain onset and competing dates stay unknown. |
| Severity | Only an explicit integer out-of-ten scale, including zero and English number words, is eligible. Qualitative intensity and decimal scales are not converted. Distinct conflicting ratings or negated scales stay unknown. |
| Clock | Only a literal 24-hour `HH:MM` span is eligible. A clock also needs an exact occurrence day and a valid local time under the existing timezone/DST rules; gaps and ambiguous folds require manual confirmation. |
| Optional evidence | Every retained field has an exact verified source span with offsets. Missing model evidence may be supplied by a unique, independently verified source extraction, explicitly labelled as copied from source. A forged or semantically incomplete model quote is omitted, never replaced to make that suggestion appear supported. |
| Model/source disagreement | The field is omitted and flagged. The source value does not silently replace a contradictory model value. Conflicting source values are also omitted rather than selecting a convenient one. |
| Uncertainty | Model uncertainty can remove a suggestion. Arbitrary model-written clinical explanations are not displayed; the proposal uses fixed field-review messages and the original narrative remains intact. |

Optional fields are populated conservatively for an asserted symptom interpretation. Note/global-abstention outputs keep optional fields unknown for manual completion. The narrow context screens cover tested English negation, hypothetical and family forms; they are not a clinically validated universal language/negation parser. Complex narratives may need manual entry or separate observations. An invalid core model response can still fail safely instead of returning a proposal.

The worker records content-free `field_abstentions`, `discarded_model_fields`, `source_normalized_fields` and the normalization version. Source content stays in the private proposal and original Journal draft; diagnostic metadata does not include narratives, source quotations, scalar values, credentials or provider bodies. Retention and authority/lease checks are unchanged.

## Patient journey

The patient sees the preserved narrative, exact quotations, source-extraction labels, unknown fields and fixed reasons for abstention. Copying applies only checked evidence-backed suggestions and keeps other manual draft values. Explicit acceptance/editing updates only the private draft. A separate Save operation publishes the Journal event through the existing immutable-history path. Rejecting, changing the draft, losing authority or expiring a proposal retains the existing protections.

## Evaluation and verification

The frozen corpus and previous reports are unchanged. The evaluator still makes one model request per selected case and uses the actual shared pipeline/Journal validator. New report accuracy is explicitly labelled `validated_hybrid_proposals_after_source_normalization`, with normalization version and discarded-field diagnostics. It measures the safe review proposal, not raw model extraction accuracy. The deterministic baseline remains separate.

Mocked tests cover frozen `dev-03` with an unsupported inferred date and incomplete evidence, exact source offsets, number-word severity, zero, qualitative/decimal intensity, invalid/partial/relative dates, contradictory ratings/dates, model/source disagreement, optional forged quotes, core citation rejection, clinical-context negation, arbitrary generated claims, timezone/DST handling, and the request → partial proposal → patient review → separate publication journey. The evaluator privacy regression makes a single mocked `dev-03` request, verifies the normalized expected fields, and discloses the discarded occurrence suggestion. These successes are not real Apertus results.

Frontend regressions verify visible review warnings, preservation of manual date/time, unchanged original text and no publication on copying suggestions. Run the backend targeted suite with `records.tests.test_journal_normalization` and `records.tests.test_journal_eval_reporting` included, alongside the existing Journal, pipeline, care-intelligence and assistant suites.

Completed checks: **122/122 backend tests** passed on a new disposable PostgreSQL 18.3/PGlite instance; **13/13 frontend Journal tests**, TypeScript checking and the production Vite build passed. The evaluator regression produces one accepted, exact-field-matching normalized `dev-03` proposal while explicitly recording the discarded model occurrence. That response is mocked, not a measured Apertus success. The browser tests emitted the existing jsdom canvas warning and the build emitted dependency annotation warnings; both completed successfully. Python compilation and `git diff --check` passed. The corpus SHA-256 remains `a5546cce0ece486c3ba178b719097699ecc2b6285605287f783c41e5096a06ee`.

## One final live synthetic verification

Run only after mocked checks pass, from `D:\Hospital`:

```powershell
Set-Location D:\Hospital
$compose = @('--project-directory', 'track_2b', '--file', 'track_2b/compose.yaml', '--file', 'track_2b/compose.local.yaml')
docker compose @compose build worker
if ($LASTEXITCODE -ne 0) { throw 'Worker build failed.' }
$reportDir = Join-Path (Get-Location) 'track_2b/.runtime/journal-ai-eval'
New-Item -ItemType Directory -Force $reportDir | Out-Null
docker compose @compose run --rm --no-deps --volume "${reportDir}:/app/.runtime/journal-ai-eval" worker python src/tools/journal_ai_eval.py run --case-ids dev-03
```

Expected safe result: symptom; severity 6 with the actual “six out of ten” source span; unknown occurrence date/time; preserved original narrative; explicit review flags. Check `validator_accepted_outputs`, `passed_cases`, field/exact accuracy, invalid evidence, discarded-field diagnostics and latency. A valid partial proposal is distinct from a complete field-accurate result.

No full 23-case model run is authorized at this stage. If the live check fails, retain its report and document the core failure or coverage limit without another blind prompt cycle. A one-shot evaluation uses the new image; the running app/worker still require deployment and an actual authenticated UI request before claiming live application verification. No live performance improvement or clinical validation is established by mocked tests.
