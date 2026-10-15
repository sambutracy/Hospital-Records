# Synthetic ecosystem: reproducible integration evaluation

This tooling is separate from the ordinary Comfort installation. It does not
reset databases, rewrite patient identities, import SQL fixtures, or start a
continuous model queue by default. Source documents enter the installed HTTP ingestion
API after normal Keycloak authorization-code authentication and CSRF validation.

## Prerequisites and isolation

Run commands from the repository root with Python 3.12+, the application Python
dependencies, and `pip install -r track_2b/requirements-ecosystem.txt`.
Docker Compose and the ordinary local Apertus installation must be available.
The evaluation reuses only its inference service on
`health-continuity_model_runtime`, including the already prepared API-key file.
It creates a separate `comfort-ecosystem` project, database and document volumes.
The app is at `http://127.0.0.1:8010/app/`, Keycloak at
`http://127.0.0.1:8091`. Use these exact origins; the ordinary installation stays
on its existing ports. The initial fixture download needs internet access;
cached inference and subsequent document processing stay on local services.

The command-line protocol client emulates browser handling of Keycloak Secure
cookies only for its fixed, trustworthy loopback realm. Server cookie, CSRF,
OIDC and production authorization settings are unchanged. This is a protocol
integration test; it is not a browser usability or assistive-technology test.

## Prepare and inspect

For hands-on use of the older port-8010 installation, explicitly enable its
assistant-only worker:

```powershell
python track_2b/src/tools/ecosystem.py interactive
```

This processes saved user assistant requests, including already queued ones,
without draining bulk metadata jobs. Before controlled model evaluation, stop
`assistant-worker` with this project's Compose configuration and allow its stale
heartbeat (at most 20 seconds) to clear. Evaluation refuses to create requests
while that interactive worker is active. For the ordinary port-8000 client use
the [client testing guide](client-testing.md); its worker starts with `make run`.
The [performance follow-up](apertus-performance.md) covers protocol v7 and actual
client checks separately from the frozen historical evaluation below.

```powershell
python track_2b/src/tools/ecosystem.py prepare
python track_2b/src/tools/ecosystem.py plan --profile smoke
python track_2b/src/tools/ecosystem.py plan --profile functional
python track_2b/src/tools/ecosystem.py init
python track_2b/src/tools/ecosystem.py start
```

`prepare` downloads checksum-verified files from pinned revisions, validates
patient/admission/note joins and creates deterministic, supported PDF
representations. It prepares mappings for 50 patients; this does **not** mean
50 patients have been seeded. Original benchmark PDFs remain byte-for-byte
unchanged. Rendered NHS notes have explicit synthetic wrappers; original CSVs,
text hashes, normalization changes and encounter IDs remain available.

`plan` performs no network or database writes. It validates already prepared
local files and writes a private plan receipt. JSON is written with explicit
CRLF to preserve the initially frozen bytes on every platform; the dataset's
Git attributes disable checkout line-ending conversion for these JSON files.
Population, source and reference
text locks are public under `data/ecosystem-v1/`; raw downloads, prepared PDFs,
credentials, sessions, detailed results and provider captures stay in ignored
`.runtime/ecosystem/`. Do not publish this directory or private account files.

## Smoke, functional and stress profiles

```powershell
python track_2b/src/tools/ecosystem.py seed --profile smoke --max-documents 32
python track_2b/src/tools/ecosystem.py verify --profile smoke
python track_2b/src/tools/ecosystem.py workflows --profile smoke
python track_2b/src/tools/ecosystem.py process --profile smoke --max-jobs 32
```

Smoke selects P01, P02 and P14 plus A01, A02 and A09: 23 initial documents.
P14 starts empty; its onboarding journey subsequently creates one auxiliary
record. Functional selects 15 patients and 10 additional actor accounts with
308 initial documents. Each actor also has their own canonical patient workspace.

Repeat the following bounded commands until their receipt reports all selected
documents present or no queued extraction jobs left. Run one operation at a
time; an OS lock prevents overlapping population writers.

```powershell
python track_2b/src/tools/ecosystem.py seed --profile functional --max-documents 64
python track_2b/src/tools/ecosystem.py verify --profile functional
python track_2b/src/tools/ecosystem.py workflows --profile functional
python track_2b/src/tools/ecosystem.py process --profile functional --max-jobs 32
python track_2b/src/tools/ecosystem.py journeys --profile functional
```

Seed operations resume via stable OIDC subject/workspace/document checksums.
They do not reset passwords or modify an existing mismatched identity. If a
creation response is lost before its exact subject is saved, provisioning fails
closed: inspect the isolated realm instead of adopting a similarly named account.
Repeated uploads use normal original-byte deduplication. Reviewer decisions and
metadata revisions are not overwritten. Temporary permission tests intentionally
create new grants each invocation; existing grants are never extended or reopened.
Expiry is tested against actual elapsed wall time. Contribution resume checks
existing submitter/checksum-bound receipts before attempting another submission.

Stress maps 50 coherent patients, but seeding is gated by a private
`functional-ready.json` containing `approved_for_stress: true`. Create that gate
only after reviewing functional results. Preparing mappings is not a load test,
and a synthetic run does not establish production capacity.

## Actual Apertus evaluation

```powershell
python track_2b/src/tools/ecosystem.py process --profile functional --live --max-jobs 4
python track_2b/src/tools/ecosystem.py evaluate --profile functional --max-jobs 1
python track_2b/src/tools/ecosystem.py evaluate --profile functional --live --max-jobs 1
python track_2b/src/tools/ecosystem.py report --profile functional
```

Extraction mode deliberately leaves readable PDFs in the existing `waiting_model`
state. Live processing selects only the annotated metadata cases, rather than
generating hundreds of unchecked outputs. Live evaluation issues normal saved
assistant requests and dispatches bounded production worker functions. Repeat
live evaluation to advance through remaining cases. Failed attempts remain in
the report; they are not silently rerun. Normal application retry requires an
explicit new job and a separately reported evaluation attempt.

The synthetic-only capture command wraps the unchanged production model client
to save redacted request/response JSON under `model-captures/` in private runtime
storage. It requires the dedicated marker, demo mode, exact fixture OIDC subject
and a normal worker lease. It is unavailable in the ordinary stack. The first
two smoke metadata attempts predate capture support; their validated artifacts
and configuration are retained, but original provider envelopes are unavailable.

The immutable ecosystem v1 case file is extended by `evaluation-v2.json` with
verified physical PDF page locators, abbreviation retrieval and provider/date
cases. `evaluation-v3.json` adds a source-verified query targeting the two oldest
P13 notes, both outside the ten latest uploads. The earlier authored marker case
is not evidence of older-record retrieval by itself. An existing v2 execution
receipt is archived and its checksum retained when continuing into the extended
suite. The pre-existing Comfort evaluation v1/v2 fixtures are unchanged.
`evaluation-v4.json` adds three explicitly labelled single-source controls
(`cq01`, `co01`, `co02`). They measure a narrower input scope and must not be
pooled into claims about full-history reliability. To collect only these cases:

```powershell
python track_2b/src/tools/ecosystem.py evaluate --profile functional --live --max-jobs 1 --case-ids cq01 co01 co02
```

Two local request failures near the configured timeout activate a private runtime
gate. Larger unstarted cases stay recorded as not run; compact controls remain
available for diagnosis. Diagnose the runtime before resuming larger cases.
Deleting the gate does not repair inference or authorize relabelling failures.
`evaluation-v5.json` adds six fresh `cpu-*` attempts against unchanged reference
questions. They retain the original attempt as `baseline_case`. For example:

```powershell
python track_2b/src/tools/ecosystem.py evaluate --profile functional --live --max-jobs 1 --case-ids cpu-q01 cpu-o01 cpu-q08 cpu-co01 cpu-co02 cpu-q06
```

The local text model defaults to `LOCAL_ASSISTANT_MODE=extractive`: at most 2,400
source-text characters and 24 candidate excerpts, with at most 64 generated
tokens. Apertus chooses evidence IDs; the server expands only exact immutable
source passages and runs the existing citation validator. Search still starts
with authorized PostgreSQL candidate ranking. The UI labels the output as source
excerpts. This is an extractive alternative, not proof of improved abstractive
summarization. `LOCAL_ASSISTANT_MODE=generative` reproduces the earlier protocol;
hosted-model behavior is unchanged. Both request modes remain in the report.
The historical `local-evidence-v4` protocol further bounded search to 1,800
text characters and 16 candidate excerpts; overviews use per-source selections
for up to four input sources, a transparent lexical clinical-passage prior,
dated evidence and a narrative fallback for unrecognized vocabulary. A mixed
clinical/administrative line is retained. These heuristics have incomplete
coverage and are not clinical judgments. `evaluation-v6.json` through
`evaluation-v8.json` preserve the follow-up comparisons and their unchanged
reference questions; no earlier failure or omission was overwritten.

```powershell
python track_2b/src/tools/ecosystem.py evaluate --profile functional --live --max-jobs 1 --case-ids cpu4-co01
```

Saved terminal requests are read without replaying the model. A fresh checkout
runs the current protocol; its recorded configuration is authoritative. Reports
flag a mismatch with a historical requested protocol and group results by the
actual protocol. To repeat the original generative baseline, explicitly set
`LOCAL_ASSISTANT_MODE=generative` in both app and worker before creating fresh
requests. Historical raw CPU requests remain in private capture artifacts.
Those historical runs found a real limitation: an exact excerpt could end before
a qualification on the next PDF line. The current `local-evidence-v7` protocol
retains adjacent lines and splits longer passages into two exact citations,
displayed together. Search also narrows the model context to at most five relevant
documents. See the [performance follow-up](apertus-performance.md) for fresh
development results, cache statistics and remaining coverage limits. Historical
evaluation files are unchanged; independent review remains necessary.
Ground truth is authored independently or comes from literal cited source spans;
patient-reviewed metadata is not model ground truth. Review readiness means
valid structure and source quotes, not clinical correctness.

Search evaluation distinguishes keyword baseline, PostgreSQL lexical
preselection, source truncation, generation failures, model ranking and
independent human semantic review. Precision@5 keeps a denominator of five even
though the current assistant returns at most three matches; returned precision
is also reported. Unseeded reference documents are excluded explicitly from a
smoke denominator. Missing/failed responses are not counted as correct abstention.

## Results, safety and regression checks

Public `RESULTS-*.md` and sanitized `results-*.json` summarize actual completed
runs. Private receipts preserve account/document bindings, valid responses,
configuration, latency, usage and failed cases. `human-review-functional.json` is a review
worksheet, not evidence that a person or clinician has reviewed an answer.
Separate `human-decisions-functional.json` decisions bind to the exact output and
context hashes. An `unable_to_assess` response remains inconclusive and is
excluded from assessed-case counts and factual-correctness claims.
Semantic entailment and actual usability remain unestablished until reviewed.
Container resource samples are point-in-time observations, not peak capacity or
throughput estimates; inference is shared with the ordinary development app.

```powershell
python -m unittest discover -s track_2b/src/ecosystem/tests -v
make test
```

For host contract tests, put `track_2b/src` on `PYTHONPATH`; use a writable
temporary directory on restricted Windows installations. The separate test
stack can run the same Django suite against its own disposable PostgreSQL test
database. Frontend tests remain `npm test` in `track_2b/frontend`.

Never run `down --volumes`, reset an existing realm, replace ordinary `.env`
files, publish credentials, infer trusted guardian authority, or relabel an
unimplemented workflow as passed. Keep the isolated stack if its evidence is
still needed; stopping it without deleting volumes is reversible.
