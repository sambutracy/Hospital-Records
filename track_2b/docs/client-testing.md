# Test the fictional people in the ordinary Comfort client

The frozen evaluation installation on port 8010 protects historical model outputs
and reproducibility receipts. Hands-on testing uses the ordinary application at
`http://localhost:8000/app/`, with its own Keycloak realm on port 8081. The same
fictional usernames/passwords can be provisioned there; subjects, account IDs,
workspace IDs and saved requests are installation-specific.

The explicit local loader adds the functional cohort (15 patient accounts,
10 additional accounts, 308 initial documents) through normal OIDC, CSRF and
authorized ingestion/review/profile APIs. It never adopts an existing account
without its exact previously saved Keycloak subject, resets passwords, imports
SQL fixtures, deletes volumes, approves grants, or overwrites reviewed edits.
P14 stays empty for a real onboarding journey. Care contacts confer no access.

Private, resumable receipts are in `.runtime/client-demo/`; the generated
`CLIENT_TEST_GUIDE.private.md` contains account IDs, local credentials, clinical
source examples, patient/recipient steps, and Apertus questions with expected
support/uncertainty. Keep these files ignored. Existing evaluation receipts at
`.runtime/ecosystem/` and published frozen suites remain unchanged.

## Prepare an existing local development installation

Run from the repository root after `make run`. Do not use this loader against a
production installation. Before the bulk import, record existing record/version
IDs and checksums for preservation verification. Stop only the ordinary worker
temporarily to avoid automatically generating hundreds of metadata requests:

```powershell
docker compose --project-directory track_2b -f track_2b/compose.yaml -f track_2b/compose.local.yaml build app worker
docker compose --project-directory track_2b -f track_2b/compose.yaml -f track_2b/compose.local.yaml stop worker
docker compose --project-directory track_2b -f track_2b/compose.yaml -f track_2b/compose.local.yaml up --no-deps --detach --wait app
python track_2b/src/tools/client_demo.py --max-documents 64
```

Repeat the last bounded command until `completed` equals `planned` (308).
All account and document bindings are saved separately from the evaluation.
The normal API records fixture reference metadata as manually reviewed patient
assertions; it is not an AI prediction or clinical validation.

Then prepare searchable text without model generation. This administrative
command accepts only exact fixture subjects, workspaces, sources and original
hashes in the explicit binding file, only on the localhost demo issuer. It uses
the production extractor and upload/read authorization checks. Jobs finish in
`manual_review` with `text_extracted_manual_metadata`; unreadable scans report
`needs_ocr`. It creates no AI artifacts and makes no model requests.

```powershell
docker compose --project-directory track_2b -f track_2b/compose.yaml -f track_2b/compose.local.yaml run --rm --no-deps --volume "./track_2b/.runtime/client-demo/bindings.private.json:/client-demo-bindings.json:ro" worker python src/manage.py prepare_client_demo --bindings /client-demo-bindings.json
docker compose --project-directory track_2b -f track_2b/compose.yaml -f track_2b/compose.local.yaml up --no-deps --detach --wait worker
```

Resume the worker after preparation. On interruption, keep queued fixture jobs
bounded by completing preparation before restarting it. No changes to normal
uploads' automatic processing, database constraints or patient grants are needed.
New user-initiated assistant requests run through the regular worker and local
Apertus service; historical evaluation results are not copied to new accounts.

## What the browser journeys actually support

Use separate browsers or a private window for patient and recipient sessions.
The new Records/My Care screens support upload, filtering, source details,
private visit selections and source-linked Apertus requests. Profile, sharing,
contribution and Received access still use their existing linked screens. That
frontend transition is a remaining product gap, not a simulated permission.

P02's practitioner recipients are A01/A02. P03 has reported caregivers A05/A06;
P04 has reported guardians A07/A08. Patients explicitly approve a selected packet
for each recipient. Read permission does not grant contribution rights, full
workspace access or verified guardian delegation. A03 can test contribution-only
access from P07; A09 tests absence of access. Revocation/expiry should deny
subsequent reads. Previously downloaded copies cannot be recalled.

P02 includes a hip osteoarthritis/hip-replacement history and source-reported
HTN, hyperlipidemia, osteopenia and anaemia. One pre-clerking note lists the
**father's** type 2 diabetes/HLD under family history. Searching `diabetes` must
not turn that into the patient's diagnosis. These are literal synthetic source
facts, not independently verified clinical findings or a current problem list.

For more controlled model checks, use P01's `Medicine Q` uncertainty and lab
units/specimen date, and P15's conflicting `Medicine Z` prescriptions and later
reported non-use. Create a visit selection of the relevant originals before
requesting its overview. Check citations against the PDF. The current local CPU
mode selects bounded exact excerpts; it does not answer arbitrary diagnostic
questions or guarantee that adjacent qualifications are retained.

The first ordinary-client P02 overview exposed a usefulness failure: with six
selected originals, the completed response cited two document-date values only.
It was a real local model run with valid citations, but it did not provide a
useful history overview. Completion/source validation must not be scored as
successful summarization. The private browser-test receipts preserve that output
separately from the earlier frozen evaluation reports.
