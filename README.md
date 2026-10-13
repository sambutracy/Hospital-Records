# Hack Apertus — project template

Template repository for [Hack Apertus](https://hackapertus.ch/) submissions.
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

Current status: self-hosted Keycloak OAuth/OIDC, explicit self-workspace authorization, private record storage, metadata review/history, keyword search and frozen consultation packets. The workspace now has upload/review/preview/packet screens and an assistant for semantic search, source-linked overview drafts and reviewed glossary definitions. All 127 identity/records/assistant tests pass on native PostgreSQL. A local CPU Apertus 8B text conversion is installed and connected while CSCS approval is pending. Medical-image previews and bounded DICOM header inspection work; image interpretation, OCR, full study viewing and clinician sharing remain pending.

Work in `track_2b/`, the application directory; run Make targets from the repository root. The official challenge README and technical report outline are preserved there. See [application setup and current implementation](track_2b/src/README.md). Internal planning notes stay local and ignored by Git.

`make run` defines a local Docker demo with Keycloak, PostgreSQL, migration, web and worker services. The equivalent Compose commands built and started it on Docker Desktop. Real Keycloak sign-in, workspace isolation, sign-out and restart persistence were checked earlier. The optional Windows inference process is started separately; see [model setup](track_2b/src/intelligence/README.md). A portable model deployment, clean-checkout verification, final evaluation, report PDF, demo video and submission checks remain pending.

A separate [Apertus synthetic text trial](track_2b/src/intelligence/README.md) uses five authored development cases and 14 offline harness tests. It records real responses, strict metadata/evidence grading and latency in private artifacts, using the required LLM environment variables. Those live results must be distinguished from mocked protocol tests and from clinical validation.
