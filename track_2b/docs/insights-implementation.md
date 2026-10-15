# Insights: integrated timeline and observation counts

Implemented and verified on 16 October 2026 in the ordinary `localhost:8000`
application. This is the first Insights slice of the Journal/Insights product
specification, not completion of every longitudinal-intelligence feature.

## User journey

Open Insights in an authorized patient context → select a date range and optional
concern → inspect recorded symptom counts and their coverage → browse dated or
undated care events → open an exact observation with its correction/history tools
or review an original → explicitly select up to 30 exact document versions →
confirm a private visit selection → reopen its frozen sources in My Care. An
Apertus overview can then be requested separately from the existing visit screen.

The timeline includes active Journal notes/symptoms, current document versions,
active reported medication entries, active concerns, care groupings and active
care relationships (which can describe historical participation). Drafts and
archived events are excluded. Document-date metadata must come from the current
patient-reviewed metadata head; an unreviewed AI proposal never supplies a date.
Accepted submissions retain attribution to an unverified invited account rather
than implying verified clinical authorship.

## Backend extension and authority

`records/insights.py` is a read projection across existing authoritative tables.
There are no migrations, duplicate event records, changed constraints or new
capability rules. The existing `manage_profile` **and** `read_workspace_records`
checks protect both endpoints, matching private Journal and care relationships.
Medication history additionally requires the live `manage_medications` capability.
Share recipients cannot read the private timeline. A care relationship or concern
label creates no access, delegation or professional verification.

Both endpoints use the existing authenticated/no-store API wrapper and protected
query context. Every download and mutation retains its own live server checks.
No user-entered medical narrative is placed in an Insights page URL. Filters live
in component memory; query responses live only in the existing patient-scoped
QueryClient and clear at context teardown/session loss. There is no new persistent
browser storage or external service dependency.

| GET endpoint under `/api/workspaces/{id}/insights/` | Contract v1 |
|---|---|
| `timeline/` | Required ISO `from`, `to`, inclusive and at most 366 days. Optional `kind`, `origin`, `concern`, `episode`, `document_type`, `date_scope=dated or undated`, `page`. Returns 30 items, next-page number, matching dated/undated counts, scope, coverage flags and generation time. |
| `observations/` | Same required dates and optional `concern`. Returns one bin per local calendar date, observation/scored counts, nullable severity min/max, coverage/exclusion counts, explicit method and chart eligibility. |

Unexpected filters or invalid dates/IDs are 400. Unavailable/foreign resources are
404; anonymous sessions are 401. Domain selectors validate the workspace before
querying. SQL identifiers and union fragments are fixed application code; all
workspace/filter values are bound parameters. The timeline counts and pages the
union in PostgreSQL, with one global stable order and batched hydration of the
returned page. It does not load an entire patient's records into Python.

Each timeline item contains a stable `kind:id`, source/workspace ID, preserved
typed occurrence date, date meaning, separate recorded timestamp, provenance,
review status, private visibility, same-origin source/entry link, nullable exact
source-version link and labelled details. Counts and page reads are a live
projection, not a transactional export: concurrent new events can move page
boundaries. The frozen visit selection remains the existing immutable snapshot.

## Temporal and source semantics

- Known day, month, year and unknown stay distinct. Query-only lower/upper bounds
  decide overlap without inventing an occurrence date. Dated items sort by their
  possible start, then recorded timestamp, kind and ID; this is browsing order,
  not a claim of a precise clinical sequence.
- Undated entries are separate and **not** asserted to fall inside the chosen
  range. Their matching count spans all undated entries under the other filters.
- Care groupings currently have no occurrence/appointment date. Their creation
  timestamp is shown only as recorded time. The existing grouping tools remain
  accessible through an explicitly labelled earlier-interface link.
- Concern filters use only direct saved concern links; they do not infer document
  associations from words or proximity. Grouping filters follow exact linked
  source-version IDs and medication links. An older linked document version never
  implicitly pulls a newer current version into that grouping.
- Medication dates mean the reported visit date. Prescribed, reported taken,
  reported not taken and unknown use remain distinct. This is medication history,
  not an intake event stream or an adherence calculation. Its existing editing
  journey remains available through a labelled link.
- Dropdowns reuse the bounded existing care APIs (including the 50 most recent
  groupings). Timeline pagination itself is not limited to those dropdown rows.

## Deterministic observation summaries

The method `active_patient_reported_symptom_entries_by_exact_local_date_v1` counts
only active symptom entries with exact local dates inside the chosen range and
optional concern. One entry is one observation, not a unique symptom episode.
Duplicate descriptions are not silently deduplicated. Personal notes, drafts,
archived entries and partially/unknown-dated entries do not enter daily counts.
Partially dated overlapping entries and all undated symptom entries are counted
separately as exclusions. No timezone conversion shifts a date-only observation.

No-entry dates have zero **recorded entries**, while severity is null. An explicit
severity of zero remains zero. Missing scores are not zero and do not enter the
min/max. The accessible table shows both facts. Different symptoms are not
averaged. The bar chart appears only with observations on at least three distinct
dates; its height counts entries. It omits unrecorded dates with explicit wording,
and the table retains every date. This presentation threshold is not a statistical
or medical validation rule. No diagnosis, causal explanation, adherence or
clinical trend is inferred. Timeline-only filters do not change these counts;
the UI explains the shared date/concern scope.

## Visit preparation and AI boundary

Only document cards can be selected. The confirmed POST reuses `packets/` with
`purpose` and exact `source_version_ids`, freezing their currently reviewed
metadata through the existing service and database contracts. Selected versions
remain selected while paging/filtering on Insights, until saved, removed or the
page is left. Confirmation lists the actual filenames. It creates no access grant
and no model request. Journal, care relationships and medication-entry text are
not added to the packet or model context.

Automatic Journal interpretation, cross-domain AI narratives, versioned selected
Journal evidence, granular sharing and extra event categories are future slices.
They require explicit evidence/authorization contracts; an ordinary record packet
must not be repurposed to imply those capabilities.

## Verification

- All **234** native PostgreSQL identity/records tests passed. Twelve new Insights
  integration tests cover live authority/revocation, share-recipient exclusion,
  restricted runtime database-role reads, medication permission, mixed source
  types, partial/unknown dates, accepted-submission attribution, explicit concern
  links, exact-version grouping behavior, bounded global pagination/query count,
  deterministic counts and absence of automatic grants/model requests.
- All **42** frontend tests passed, including seven new Insights journeys:
  exact Journal navigation, zero/missing data, dated/undated filters, explicit
  document-only preparation, pagination/error retry, empty history and denied
  capability. Axe semantic/landmark/table checks passed; JSDOM cannot validate
  real visual contrast or assistive technology. Existing palette contrast tests
  pass. These checks do not establish complete WCAG conformance.
- Strict TypeScript, targeted ESLint, production Docker frontend/backend builds
  and migration-drift check passed. App and worker are healthy. The local model,
  identity service, databases and existing volumes were retained.
- Authenticated normal OIDC/CSRF API reads on the ordinary app traversed all
  **100** P13 documents without duplicates. P14 remained empty. The complete
  grouped read sequences took about 0.33–0.65 seconds locally; these are measured
  fixture checks, not a production performance guarantee.
- A real browser opened P02 Insights, followed a specific fictional observation
  into its four-revision correction history, inspected undated concern provenance,
  used the native date picker and document filter, then selected one fictional
  original and confirmed a private visit selection. The saved selection showed
  exactly that original and its separate, unpressed Apertus-request button.
- Targeted browser checks at 390px and 1440px widths found no horizontal document
  overflow. The mobile data table remained inside its scrolling container and
  exposed named pagination controls. A real session expiry hid the protected
  counts and history; ordinary Keycloak reauthentication restored authorized
  access. Full screen-reader and device compatibility research remains pending.
- Original workspaces, record/version rows and original file bytes passed the
  existing preservation checker. The fixture cohort remains 308 originals,
  307 readable-text records and one OCR-needed record. Frozen evaluation fixtures
  and previous model results were not rewritten.

Local verification receipts and screenshots stay in ignored `.runtime/insights-demo/`.
The added browser verification visit is clearly fictional and private. No model
quality improvement or new clinical-validation claim is made by this slice.
