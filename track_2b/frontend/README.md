# Comfort frontend — foundation and records

This React + strict TypeScript + Vite application implements the foundation and first records slice from the 14 October product specification. Django remains the identity and authorization authority. The existing verification interfaces remain available by direct URL; their visual layout was not used as a design reference.

## Run and verify

From the repository root, `make run` builds the frontend in a Node Docker stage, collects its assets in Django, and serves everything at the same origin. Open `http://localhost:8000/app/`. The existing Keycloak authorization-code flow, callback and POST logout remain unchanged. Successful sign-in selects the authorized application context. No browser-held OIDC tokens are introduced.

For frontend development, use Node 22.12+ and `npm ci`, then `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`. `npm run storybook` opens the component workbench; `npm run build-storybook` builds it. Vite builds use `/static/comfort/`; live integrated testing uses the Docker app, not invented API fixtures. Test-only mocked responses are confined to `.test.tsx`.

## Contracts and privacy

- `GET /api/session/` contract v1 returns the actor's opaque ID/display name, authorized patient contexts, each live effective capability, default context only when exactly one is available, session expiry and masked CSRF token. Anonymous/expired sessions receive 401. It sets the existing CSRF cookie. It never returns ID documents, blood type, contact details or model credentials. Unverified caregiver/guardian labels do not create contexts. Recipient grants are not promoted to full patient workspaces or verified clinician status.
- `/app/` and nested routes return a data-free shell. API calls are schema-validated. Opaque IDs may appear in routes; search terms and medical details are held in memory and sent in JSON bodies. No analytics, external fonts, persistent browser caches or stored patient data are added.
- New `POST /api/workspaces/{id}/records/search/` reuses live record-read authorization and current-version projection. Input: `q` (max160), offset0–10000, order upload/document_date, document_type, reviewed yes/no, uploaded_from/uploaded_until (inclusive UTC calendar dates), document_year (known year, including partial dates). Output retains the record contract and adds total/has_more. Pages contain at most50. Unknown filters and invalid dates fail400. Unknown/unauthorized workspace IDs share404. CSRF is required. Existing GET records and original upload contracts remain supported.
- No data-model migration was needed. Originals, metadata assertions, source-version scope, revision checks, audit and patient/actor separation remain authoritative on the server. Changing displayed UI capabilities does not grant authority.
- Session expiry removes protected UI. Bootstrap refreshes on visibility and every30seconds, and rejects stale responses. Context changes/permission changes unmount the patient scope, abort reads and clear TanStack Query's in-memory cache. Direct URLs cannot select an unauthorized context. The backend still rechecks every request and download; this is not a claim of immediate provider back-channel logout.

## Complete first journey

Sign in → authorized shell → upload up to30 PDF/JPEG/PNG/DICOM originals individually → inspect saved/duplicate/error states and continuing background job status → download exact original or inspect a non-diagnostic raster preview → review document type, facility and partial/unknown date → retain entries on revision conflict and explicitly reload → find/filter/page records → select exact source versions → confirm a private visit selection → reopen/download its immutable sources. Saved asynchronous Apertus searches and overview drafts are created only by explicit action. Polling reads saved state; it never regenerates automatically. Original versions and earlier verification interfaces remain available.

Journal, new Care Team/concern domains, verified professional contexts and delegated caregiver/guardian workflows are explicitly pending. Existing profile, reported medications and sharing/contribution tools remain reachable through clearly labelled links to the earlier interface. A private visit selection is not a share or clinical summary. Image pixels are not sent to the text model.

## Accessibility and design decisions

The foundation uses the proposed Quiet Editorial Care palette, Source Sans3 served locally, semantic landmarks, skip navigation, labelled native inputs, React Aria buttons/confirmation dialogs, explicit provenance and outcome text, visible focus,44px control targets, reduced-motion and forced-colour rules. Mobile uses four primary routes plus More; desktop uses a navigation rail. Storybook compares the three specified directions using the same content; directionA is the specification's provisional recommendation, not a completed usability research result.

Unit tests cover partial dates, file limits, successful-file retention on retry, revision conflicts, original/revision binding, CSRF/contract failures, context isolation, late bootstrap responses and expiry hiding. Axe component checks supplement manual keyboard, responsive and focus review. Automated checks alone do not establish WCAG2.2AA compliance. NVDA/VoiceOver and participant usability research remain required before claiming accessibility compliance.

Future features follow the specification's dependency sequence: care relationships and verified contexts; scoped sharing/contributions; private journal/event domains; then longitudinal insights. Do not broaden existing authority or invent appointment/clinical data to fill future screens.
