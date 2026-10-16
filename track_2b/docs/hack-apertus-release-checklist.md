# Hack Apertus Track 2B release checklist

Status: technical package prepared for owner upload. This is **not** confirmation of a portal submission.

| Item | Status |
| --- | --- |
| Track | 2B — Own Project |
| Team | Comfort (solo) |
| Public repository | https://github.com/sambutracy/Hospital-Records |
| Release commit | Final commit is the repository `main` HEAD reported in the handoff. Check with `git rev-parse HEAD`. |
| Repository-root `make run` | Target is present and configured for local Docker Apertus. Fresh end-to-end startup must be verified on the submission host; it downloads about 5.1 GB on first setup. |
| Technical report Markdown | `track_2b/technical_report.md` — prepared |
| Technical report PDF | `track_2b/Comfort_Report.pdf` — prepared; 3 pages, text/metadata checks passed; rendered-page visual inspection unavailable in this environment |
| Code license | Apache-2.0 at repository root |
| Data license/provenance | Authored evaluation content CDLA-Permissive-2.0; imported synthetic sources retain their own MIT/CC BY 4.0 terms and attribution |
| Public data size | 1,817,307 bytes across 34 files (about 1.74 MiB), below 100 MB |
| Hugging Face dataset | Optional for Track 2B; no public dataset release claimed or required for this project |
| Demo video URL | Pending from owner; maximum two minutes |
| Official portal upload | Pending manual upload at https://hackapertus.ch/online-hack/submissions |
| Submission receipt | Pending portal confirmation |

## Copy-ready project description

Comfort is an on-premise patient-controlled health-record workspace that helps people bring records from different providers together, find source evidence and prepare for a visit. Patients preserve their originals, select the records and optional personal context used for preparation, review source-linked suggestions and control any sharing. Comfort uses local Apertus v1.5 8B text inference to select and organize evidence. AI output is a reviewable aid, not a diagnosis or treatment recommendation.

## Apertus role

The local Q4_K_M text conversion of Apertus v1.5 8B selects relevant evidence from bounded, authorized record excerpts for search and packet overviews. The server verifies citations against preserved source text and displays original links. The structured visit-brief implementation builds on the same evidence-selection approach, but still needs live model validation. Journal extraction and Health history AI remain experimental; previous real Journal outputs failed validation. No fine-tuning, clinical accuracy, clinical review or health outcome is claimed.

## Before owner submission

1. Confirm current `main` and the release commit are visible in the public GitHub repository.
2. Verify `make run` on the intended clean/demo host and confirm the app is reachable at `http://localhost:8000/app/`.
3. Generate/inspect the included PDF and confirm its page count is no more than six.
4. Add the owner-recorded two-minute demo URL to the portal.
5. Upload the repository URL and technical report PDF through the official portal.
6. Record the portal's receipt/confirmation before describing the submission as complete.
