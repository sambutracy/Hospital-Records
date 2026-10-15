# Daily Journal: implementation report

Verified on 16 October 2026 (Africa/Nairobi), against the ordinary localhost:8000
application and native PostgreSQL. This is the foundation and first daily Journal
slice, not completion of the full Journal/Insights specification.

## Delivered

- Patient-authored personal notes and symptoms, optional severity and concern
  associations, exact/partial/unknown occurrence dates and optional local time.
- Day navigation and chronological list; category, concern, date and archive
  filters; bounded server pagination; empty, loading, save and error states.
- Optimistic corrections, immutable database-written actor/revision history,
  confirmed archive and restore. Original medical documents are not edited.
- Bounded private server recovery drafts, acknowledgement messages, explicit
  publication and draft discard. A competing draft is shown without overwriting
  it; replacement or choosing the saved draft requires explicit confirmation.
- Patient-scoped memory recovery across ordinary route navigation, cleared with
  the existing authorization context. No Journal content in localStorage or
  sessionStorage. Saved server drafts are retrieved only after fresh authority
  checks; they are never silently published on session interruption.
- Existing session, CSRF, capability and PostgreSQL guarantees retained. Record
  recipients and relationship labels acquire no Journal authority. No Journal
  content is added to shares, consultation packets or Apertus requests.

See [the domain/API contract](journal-insights-implementation.md) for schemas,
temporal semantics, permissions, migration details and recovery limits.

## Real client verification

On fictional P02 in the ordinary app, a private draft was resumed, edited, kept
without publication, recovered after a full page reload, and explicitly saved.
Its symptom observation was corrected, archived and restored. The client showed
all four database-backed revisions, including the original wording and archived
state. Optional severity and cause remained unrecorded rather than inferred.

A different pre-existing blank symptom draft initially caused a genuine conflict;
the server retained it and the local writing. That case prompted the explicit
draft-comparison interface and a regression test. No competing draft was silently
overwritten. The browser also reached the real expired-session state, which hid
patient content and retained the server recovery draft for sign-in.

Mobile width 390 and desktop width 1280 had no horizontal document overflow.
The narrow layout retained readable narrative, navigation and action controls.
Keyboard reverse-tab from correction history focused the Archive control with a
visible focus ring. These are targeted checks, not a complete WCAG certification
or a screen-reader/device compatibility audit.

Three versioned [fictional fixtures](../data/journal-v1/README.md) were added through
normal OIDC/CSRF APIs. P14 was inspected without writes and remained empty. The
browser check added one separately labelled fictional observation; it does not
modify the pinned fixture manifest or previous evaluation results.

## Validation

- 222 PostgreSQL identity/records tests passed, including native Journal guards,
  private drafts, invalid input, scope, stale revisions, DST gaps/folds, share
  recipient exclusion and forward/reverse migration checks in a disposable DB.
- 35 frontend tests passed, including 11 Journal journeys/contracts and the
  existing Records, My Care, session, primitives and contrast checks. Final
  TypeScript/production Docker build checks passed.
- Targeted ESLint checks passed for Journal, routing and the API client.
- Automated accessibility checks passed in the component journey; jsdom cannot
  verify browser color contrast or canvas-dependent checks. Existing token
  contrast tests and the targeted real-browser checks supplement them.

Earlier full-suite attempts exposed a test-container static-assets mount issue
and a rollback-test catalogue-fixture setup issue. Both were corrected before the
passing full PostgreSQL run; they were not product authorization exceptions.

Private receipts, screenshots, build/test logs and local IDs remain in ignored
`.runtime/journal-demo/`. No credentials are added to public fixtures or reports.
The final preservation check retained all pre-existing workspaces, records and
source versions in the original receipt and verified their original bytes.
The existing client cohort still contains 308 fixture records (307 extracted,
one requiring OCR); Journal adds no original-document replacements.

## Remaining work

Month/week calendar views and date indicators; more than 100 history revisions
through a paginated history UI; medication intake; wellbeing; explicitly enabled
menstrual observations; source-record associations; the unified care timeline;
deterministic Insights; and explicitly selected evidence for Apertus/care
preparation. Trusted caregiver/guardian authority and granular Journal sharing
remain separate authorization work.

Recovery cannot guarantee the last unacknowledged keystrokes during network
failure, forced browser closure or expired authorization. The editor shows whether
its newest changes are saved and warns before ordinary departure. Drafts remain
private on the server until explicitly discarded or published; no draft retention
or automatic erasure policy is claimed. Existing short session lifetime is not
changed by this slice.
