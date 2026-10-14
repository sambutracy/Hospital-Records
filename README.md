# Hack Apertus — project template

Template repository for [Hack Apertus](https://hackapertus.ch/) submissions.
Comfort's integrated React interface is available at `http://localhost:8000/app/` after `make run`. See [frontend contracts, workflow and verification](track_2b/frontend/README.md). Django remains the authorization authority, with existing verification interfaces preserved.
Every project keeps almost the same layout, so organizers and judges find the
same things in the same place.

## Select your track

This repository holds one example project per track:

- `track_1a/`
- `track_1b/`
- `track_2a/`
- `track_2b/`

Keep the directory for the track you are competing in **exactly as it is** —
don't rename it or move its files — and delete the other track directories.
Keep the track's application and report files inside that directory. The
repository root contains the launch Makefile, following the organizer's
9 October clarification shared in Discord.

## The structure

| Path | What it is |
| --- | --- |
| `README.md` | The challenge description and submission requirements for your track |
| `technical_report.md` | The deeper write-up: architecture, evaluation, limitations |
| Repository-root `Makefile` | Judges launch the application with `make run` |
| `src/` | Your code |
| `data/` | Datasets — `track_1a`, `track_2a` and `track_2b` only; max. 100 MB |
| `findings/` | Issue files — `track_1a` only |
| `docs/` | Diagrams, notes, longer write-ups |

## Run it

Judges run `make run` from the repository root, on a clean checkout:

```bash
make run
```

`make run` is expected to run the project using Docker, since that
is how the judges will run it.
- If you used other local open-weight models, include instructions for running the project in your technical report.
- Use the following environment variables:
```
LLM_NAME — name and version of the model
LLM_BASE_URL — endpoint base URL
LLM_API_KEY — your API key
```

## Getting started

1. Click **Use this template** to create your own repository.
2. Delete the other track directories. Don't rename or restructure yours.
3. Read its `README.md` and fill in `technical_report.md`.
4. Make `make run` work from the root of the project, on a clean checkout.

For Comfort, the layout is:

```text
Makefile
README.md
track_2b/
  compose.yaml
  Dockerfile
  README.md
  technical_report.md
  src/
  data/
  docs/
```

The root Makefile explicitly selects `track_2b/compose.yaml` and its project
directory, preserving the existing volumes and private configuration paths.
The report PDF is provisionally kept in `track_2b/` beside its Markdown source;
the shared Discord reply clarifies only the Makefile location.

## License

All Hack Apertus projects are open-sourced. Please check our Terms & Conditions for specific licensing details (6. What you build is open source): https://hackapertus.ch/terms-and-conditions

## Comfort — Patient Health Continuity Platform

Current status: self-hosted Keycloak OAuth/OIDC, explicit self-workspace authorization, private record storage, metadata review/history, keyword search and frozen consultation packets. The workspace includes upload/review/preview/packet screens and an assistant for semantic search, source-linked overview drafts and reviewed glossary definitions. Patient-approved, recipient-bound expiring/revocable packet reads, independent episode-scoped note contributions and a patient acceptance/rejection inbox connect the return journey. Named episodes and document-date ordering preserve partial and unknown dates. A private [patient profile and Care circle](track_2b/src/identity/PROFILE.md) stores personal and emergency-contact details; saved contacts can be selected for separately approved sharing. [Medication entries](track_2b/src/records/MEDICATIONS.md) distinguish medicines prescribed from medicines reportedly taken at different visits, with optional exact original links. All 161 identity/records/assistant/continuity/profile/medication/evaluation tests pass on PostgreSQL 18. See the [continuity contract](track_2b/src/records/CONTINUITY.md). Invited accounts are not verified clinical identities. A local CPU Apertus 8B text conversion is installed and connected while CSCS approval is pending. Medical-image previews and bounded DICOM header inspection work; image interpretation, OCR, full study viewing, delegated assistance and voice controls remain pending.

Work in `track_2b/`, the application directory; run Make targets from the repository root. The official challenge README and technical report are preserved there. See [application setup and current implementation](track_2b/src/README.md). Internal planning notes stay local and ignored by Git.

`make run` now includes a [pinned local Docker Apertus server](track_2b/src/intelligence/DEPLOYMENT.md), verified weights and authenticated readiness. It retains existing application data/configuration; hosted inference remains an explicit alternative. Public hospital lookup is disabled by default in this local deployment and can use an organization-administered endpoint. A [frozen synthetic evaluation](track_2b/src/intelligence/EVALUATION.md) provides 30 short text records, 20 queries and 10 overview cases. Exact fresh-package verification, final report PDF, demo video and submission checks are tracked separately from an existing-stack launch.

A separate [Apertus synthetic text trial](track_2b/src/intelligence/README.md) uses five authored development cases and 14 offline harness tests. It records real responses, strict metadata/evidence grading and latency in private artifacts, using the required LLM environment variables. Those live results must be distinguished from mocked protocol tests and from clinical validation.
