# Initial implementation inventory - 15 October 2026

Baseline: `5a77d245c787a7003cce1cbd3d938744a074691e`. This inventory was
prepared before population seeding. Historical test results are evidence of
earlier verification, not new integrated-evaluation results.

| Category | Existing implementation and evidence | Required integrated verification |
|---|---|---|
| Implemented and previously working | Self-hosted Keycloak code flow with state/nonce/PKCE; distinct person/account/patient/workspace; live capability checks; PostgreSQL immutable/same-workspace guards. Previous recorded suite: 176 backend tests. | Repeat regression suite; real Keycloak authentication of new fixture users; isolate current development data. |
| Implemented and previously working | Immutable PDF/JPEG/PNG/Part 10 DICOM originals; SHA-256 deduplication and versions; ingestion jobs; protected downloads; bounded pypdf extraction and image inspection. | Import selected source PDFs through HTTP; verify original bytes and queue outcomes. |
| Implemented and previously working | Patient-reported profiles, contacts, medications, concerns and doctor assignments; revision checks and care history. React records and care journeys; previous 20 frontend tests and a fictional browser flow. | Populate through existing APIs; repeat patient isolation and distinguish prescriptions from reported use. |
| Implemented but requiring population-level verification | Exact approved packet grants; expiry/revocation and exact recipient enforcement; independent contribution authority; pending/accepted/rejected originals; recipient's own patient context remains separate. | Exercise real independently authenticated recipients and accepted/rejected submissions, including negative permissions. |
| Implemented but requiring population-level verification | Actual local Apertus Q4_K_M text conversion; production prompts, quote validation, request provenance and bounded workers. Frozen v1/v2 evaluation suites. | Sample actual ingestion, search and overview runs on populated workspaces. Structural/quotation validity is separate from factual entailment. |
| Partially implemented | Search: PostgreSQL computed full-text OR ranking over authorized current-version text before local top-10 selection (maximum 30). Each source contributes at most 2,000 extracted text characters; combined context is capped. No persistent semantic/vector index. Literal keyword API is separate. | Compare existing keyword results, preselection coverage, model-ranked results and generation errors. Test 100+ documents and later-page/older evidence. |
| Partially implemented | Technical image previews and selected DICOM headers; source-linked packet overview; document-date ordering with partial dates; family/guardian labels without trusted authority. Existing sharing/contribution UI is the earlier Django interface. | Report unsupported pixel understanding/OCR/delegation; do not reinterpret these labels as authorization. |
| Not implemented | Journal/menstrual event services, trusted guardian/caregiver delegation, professional identity/affiliation verification, clinician/guardian acting-context shells, voice controls, OCR, DICOM pixel viewer/diagnosis, appointment/referral lifecycles. | Define negative or unsupported scenarios; do not create fake successful operations or unrelated product features. |
| Not verified | Human usability with assistive technology, clinical validation, representative throughput/capacity, complete semantic quality benchmark. | Separate human-review sheets and bounded measured runs; no inference of clinical validity from software tests. |

Inspected executable references include `identity/{models,authorization,services,oidc,profile_services}.py`,
`records/{models,services,storage,worker,assistant,assistant_worker,retrieval,continuity,care_services,medications}.py`,
all migrations and HTTP URL contracts, the React features/services, Docker worker
resource/timeout settings and the frozen evaluation harness. Source docs with old
161-test counts are historical; they do not override executable code or later receipts.

## Experimental branch cleanup

The remote `feature/hf-synthetic-clinical-seed` contained exactly one unmerged
commit, `a873870fd866b9eeffd42178132ad05ae27492bb`, adding only the abandoned
108-line `src/tools/hf_seed_support.py`. No local branch/worktree or main-tree
reference depended on it. An initial automatic approval rejection left it
untouched. After explicit human deletion approval, a SHA-guarded remote deletion
succeeded and `git ls-remote` verified absence. No merge or local work was removed.

## Dataset audit findings

Pinned NHS data has 69 patient CSV rows but only **50 unique patients**: 19
patient rows are exact duplicates. These are deduplicated only after full-row
equality checks; a conflicting duplicate fails closed. The 69 admissions have
unique IDs, and all 1,602 unique notes join to the correct patient/admission.
These are silver synthetic notes, not individually clinician-verified.
No pregnancy or menstrual-history material was found in the inspected source;
P05/P06 are explicit authored scenarios. P13 uses 90 notes belonging to one source
patient plus ten authored non-diagnostic administrative follow-ups. Stress mappings
are planned separately from the functional cohort and are not permission to run load tests.
