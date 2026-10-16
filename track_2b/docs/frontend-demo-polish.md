# Frontend demo polish — 16 October 2026

The sprint refines the existing Comfort interface and preserves the current API,
authorization, source attribution and patient review flows.

## Visible changes

- Landing: balanced headline and CTA spacing, readable document illustrations,
  responsive composition and an inline logo dot in the Django shell.
- Home: concise workspace hero, three next actions and a clearer recent-records hierarchy.
- Records: reviewed document type, date and facility take precedence over filenames.
  Unreviewed metadata does not become a verified title.
- Apertus: newest requests, active progress and the latest supported result remain
  visible; older requests expand individually. Request timing and snapshot details
  are expandable. Source excerpts and AI-generated text have distinct labels.
- Workspace: a native mobile menu replaces the crowded navigation grid. It closes
  after navigation, supports Escape and restores keyboard focus.
- My Care: compact direct links to Health concerns, Care Team and visit preparation.
  Mobile secondary navigation scrolls horizontally.
- Visit preparation: selected source documents are expandable; snapshot warnings,
  patient input, consent choices, errors and AI actions remain outside the disclosure.
- Journal and history receive shared spacing and typography refinements.

Native disclosures keep their contents mounted. Collapsing supporting information
does not clear form values. Historical requests retain their quotations and original links.

## Changed files

Relative to the repository root:

```text
track_2b/src/static/app.css
track_2b/src/templates/landing.html
track_2b/frontend/src/main.tsx
track_2b/frontend/src/app/App.tsx
track_2b/frontend/src/app/MobileNavigation.tsx
track_2b/frontend/src/app/MobileNavigation.test.tsx
track_2b/frontend/src/design-system/demo-polish.css
track_2b/frontend/src/design-system/assistant-polish.css
track_2b/frontend/src/design-system/workspace-navigation.css
track_2b/frontend/src/features/home/Home.tsx
track_2b/frontend/src/features/records/RecordCard.tsx
track_2b/frontend/src/features/records/RecordCard.test.tsx
track_2b/frontend/src/features/records/TaskHistory.tsx
track_2b/frontend/src/features/records/Assistant.tsx
track_2b/frontend/src/features/records/AssistantHistory.test.tsx
track_2b/frontend/src/features/care/CareNavigation.tsx
track_2b/frontend/src/features/care/CareNavigation.test.tsx
track_2b/frontend/src/features/care/care-navigation.css
track_2b/frontend/src/features/care/Consultation.tsx
track_2b/frontend/src/features/insights/Insights.test.tsx
track_2b/docs/frontend-demo-polish.md
```

## Verification

- Current workspace: TypeScript and ESLint pass; 61 tests across 13 files pass;
  production build passes.
- Isolated frontend-only commit, without the ongoing visit-intelligence changes:
  TypeScript and ESLint pass; 54 tests across 12 files pass; production build passes.
- Mobile menu interaction tests: default closed, closes after selection, Escape
  returns focus. The final fixture-only hash-link adjustment passes both tests.
- Existing stale Health history test expectations now match the already-shipped copy;
  assertions for zero severity, missing observations and unknown days remain enforced.
- Live browser checks: landing at desktop, tablet and 390px mobile widths; signed-in
  Home, Records and My Care on desktop; mobile menu and direct visit navigation;
  selected-record disclosure exposes both original links.

Known non-blocking tooling warnings: jsdom lacks canvas support for part of axe;
Rollup reports dependency annotation warnings and a main bundle around 500 kB.
No dependency or broad bundling refactor was included.

The ongoing consultation-intelligence backend and contracts remain separate local
work. No inference calls, credentials, database migrations or volume resets were
needed for this presentation sprint. Optional Journal controls and some legacy
screens retain their existing disclosure patterns.

## Rebuild the local demonstration

Run from PowerShell:

```powershell
Set-Location D:\Hospital
$compose = @('--project-directory', 'track_2b', '--file', 'track_2b/compose.yaml', '--file', 'track_2b/compose.local.yaml')
docker compose @compose build app worker
if ($LASTEXITCODE -ne 0) { throw 'Comfort image build failed.' }
docker compose @compose up --detach --wait --no-deps app worker
```

This uses the existing local configuration and persistent volumes.
