# Comfort frontend

## Insights

The integrated `/insights` route provides a paginated care timeline across active
Journal entries, current source documents, reported medication history, concerns,
care groupings and care relationships. Dates retain their actual precision;
undated entries have a separate view. Deterministic daily symptom-entry counts
preserve missing scores and unrecorded days. Exact observation links open the
existing correction/history journey. Confirmed private visit selections include
only chosen exact document versions; Journal entries are not silently shared or
sent to Apertus. No additional model call is needed to open this view.

See [Insights contracts, limits and verification](../docs/insights-implementation.md).
The current frontend suite passes **42 tests**, including seven Insights tests
and eleven Journal tests. The complete native PostgreSQL suite passes **234 tests**.

## Daily Journal

The integrated `/journal` route now supports private patient notes and symptoms,
concern links, exact/partial dates, optional severity/time, daily and list views,
correction history, archive/restore and private server recovery drafts. Typed
APIs and PostgreSQL migrations extend the existing backend. Journal information
is not automatically shared or sent to Apertus. Draft conflicts require explicit
comparison; acknowledged server drafts survive sign-in changes, while recent
unacknowledged writing has the recovery limits explained in the editor.

See the [domain and API contract](../docs/journal-insights-implementation.md) and
[implementation/verification report](../docs/journal-implementation-report.md).
The historical foundation and My Care validation below describes those earlier slices.

This React + strict TypeScript + Vite application implements the foundation and first records slice from the 14 October product specification. Django remains the identity and authorization authority. The existing verification interfaces remain available by direct URL; their visual layout was not used as a design reference.

## Run and verify

From the repository root, `make run` builds the frontend in a Node Docker stage, collects its assets in Django, and serves everything at the same origin. Open `http://localhost:8000/app/`. The existing Keycloak authorization-code flow, callback and POST logout remain unchanged. Successful sign-in selects the authorized application context. No browser-held OIDC tokens are introduced.

For frontend development, use Node 22.12+ and `npm ci`, then `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`. `npm run storybook` opens the component workbench; `npm run build-storybook` builds it. Vite builds use `/static/comfort/`; live integrated testing uses the Docker app, not invented API fixtures. Test-only mocked responses are confined to `.test.tsx`. The explicit AJV8 development dependency resolves a reproduced npm peer-hoisting conflict between Storybook and ESLint's AJV6 dependency; it is not a patient-data validator or runtime API dependency.

## Contracts and privacy

- `GET /api/session/` contract v1 returns the actor's opaque ID/display name, authorized patient contexts, each live effective capability, default context only when exactly one is available, session expiry and masked CSRF token. Anonymous/expired sessions receive 401. It sets the existing CSRF cookie. It never returns ID documents, blood type, contact details or model credentials. Unverified caregiver/guardian labels do not create contexts. Recipient grants are not promoted to full patient workspaces or verified clinician status.
- `/app/` and nested routes return a data-free shell. API calls are schema-validated. Opaque IDs may appear in routes; search terms and medical details are held in memory and sent in JSON bodies. No analytics, external fonts, persistent browser caches or stored patient data are added.
- New `POST /api/workspaces/{id}/records/search/` reuses live record-read authorization and current-version projection. Input: `q` (max160), offset0–10000, order upload/document_date, document_type, reviewed yes/no, uploaded_from/uploaded_until (inclusive UTC calendar dates), document_year (known year, including partial dates). Output retains the record contract and adds total/has_more. Pages contain at most50. Unknown filters and invalid dates fail400. Unknown/unauthorized workspace IDs share404. CSRF is required. Existing GET records and original upload contracts remain supported.
- No data-model migration was needed. Originals, metadata assertions, source-version scope, revision checks, audit and patient/actor separation remain authoritative on the server. Changing displayed UI capabilities does not grant authority.
- Assistant task responses add `packet_id` (nullable). Visit pages display only drafts belonging to that exact packet; an earlier draft for another visit cannot be mistaken for the selected visit's overview.
- Session expiry removes protected UI. Bootstrap refreshes on visibility and every30seconds, and rejects stale responses. Context changes/permission changes unmount the patient scope, abort reads and clear TanStack Query's in-memory cache. Direct URLs cannot select an unauthorized context. The backend still rechecks every request and download; this is not a claim of immediate provider back-channel logout.

## Complete first journey

Sign in → authorized shell → upload up to30 PDF/JPEG/PNG/DICOM originals individually → inspect saved/duplicate/error states and continuing background job status → download exact original or inspect a non-diagnostic raster preview → review document type, facility and partial/unknown date → retain entries on revision conflict and explicitly reload → find/filter/page records → select exact source versions → confirm a private visit selection → reopen/download its immutable sources. Saved asynchronous Apertus searches and overview drafts are created only by explicit action. Polling reads saved state; it never regenerates automatically. Original versions and earlier verification interfaces remain available.

Private Journal, patient-reported Care Team/concern domains and the first Insights slice are now integrated. Verified professional contexts and delegated caregiver/guardian workflows remain pending. Existing profile, reported medications and sharing/contribution tools remain reachable through clearly labelled links to the earlier interface. A private visit selection is not a share or clinical summary. Image pixels are not sent to the text model.

## Accessibility and design decisions

The foundation uses the proposed Quiet Editorial Care palette, Source Sans3 served locally, semantic landmarks, skip navigation, labelled native inputs, React Aria buttons/confirmation dialogs, explicit provenance and outcome text, visible focus,44px control targets, reduced-motion and forced-colour rules. Mobile uses four primary routes plus More; desktop uses a navigation rail. Storybook compares the three specified directions using the same content; directionA is the specification's provisional recommendation, not a completed usability research result.

Unit tests cover partial dates, file limits, successful-file retention on retry, revision conflicts, original/revision binding, CSRF/contract failures, context isolation, late bootstrap responses and expiry hiding. Axe component checks supplement manual keyboard, responsive and focus review. Automated checks alone do not establish WCAG2.2AA compliance. NVDA/VoiceOver and participant usability research remain required before claiming accessibility compliance.

Subsequent features retain the specification's dependency boundaries: verified contexts, granular Journal sharing, further event categories and explicitly selected versioned Journal evidence for AI need their own contracts. Do not broaden existing authority or invent appointment/clinical data to fill screens.

## Verified first-pass results — 14 October 2026

- Strict TypeScript, ESLint, production build, Storybook build and14frontend tests passed. All168identity/records PostgreSQL tests passed, including the existing authority, immutable-source and clinical-data boundaries. No schema migration is added by this frontend slice.
- The root `make run` path successfully installs with `npm ci` in Linux and starts healthy app, worker, database, Keycloak and inference services while retaining the existing volumes.
- Real browser checks used the pre-authorized fictional patient account: Keycloak sign-in; two authored PDF uploads; exact-original download with matching SHA256; document review and retained history; keyword search; two exact-version selections; private packet persistence; a real saved Apertus request; expiration hiding; reauthentication; keyboard Escape cancellation and trigger focus restoration; provider logout. Existing patient uploads were not edited.
- The live320px visit page reflowed without horizontal scrolling; its axe WCAG-tag check reported zero violations/incomplete checks. Component axe and semantic-token contrast checks also passed. NVDA/VoiceOver,200% text resizing, high-contrast assistive-technology review and participant research remain unverified.

The screenshots and local test receipts remain in ignored `.runtime/`. A saved/queued model request is not evidence of a clinically correct generated summary. No final model benchmark or WCAG conformance claim is made here.
The initial live overview was interrupted by a deployment worker restart (`worker_interrupted`). After deployment, an explicit second request completed with actual Apertus in25.51seconds over the two fictional source versions; its source-linked output remains a draft, not clinical validation. Context teardown also aborts in-flight workspace JSON mutations and reads before their completion can navigate to an old patient context. Abort does not undo server work already committed.

The locally served Source Sans3 font license is retained in `public/SOURCE_SANS_3_LICENSE.txt`. Implementation references: [Vite backend integration](https://vite.dev/guide/backend-integration), [TanStack Query cancellation](https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation), [React Aria controls](https://react-aria.adobe.com/Button).
# My Care relationships

The second slice adds `/care/concerns`, `/care/team` and `/care/visits` under each
authorized workspace route. Patients can save uncertain health concerns, record
doctors, link current/historical participation with partial dates, correct entries,
inspect revision history and archive/restore entries. Existing family/support
contacts are displayed without duplicating their data or creating authority.

The backend extension and verified-identity boundary are documented in
[`CARE.md`](../src/records/CARE.md). A relationship never creates record access.
Verified professional affiliation and delegated acting contexts remain pending
trusted verification workflows. Forms warn on ordinary links/reload/close.
Back/forward navigation preserves drafts in the current context's memory cache
for recovery on returning to My Care; no draft enters persistent browser storage.
