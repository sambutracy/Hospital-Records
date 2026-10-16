# Comfort — patient health records, connected

Comfort is a patient-controlled workspace for bringing health records from different providers into one place, finding relevant source evidence, and preparing a focused visit brief. Patients keep originals, decide which records and optional personal context to use, and review AI suggestions before sharing. Comfort organizes information; it does not diagnose or recommend treatment.

Comfort is the Hack Apertus Track 2B Own Project submission. The public application and report live in [`track_2b/`](track_2b/); the official challenge instructions remain in [`track_2b/README.md`](track_2b/README.md). The repository-root `Makefile` is the judge entry point, following the organizers' clarification that `make run` must run from the repository root.

## Run locally

Requirements: x86-64 host, Docker Desktop with Linux containers and Compose v2 supporting `--wait`, GNU Make, about 16 GB available host memory (at least 12 GB allocated to Docker), at least 12 GB free disk, and free localhost ports 8000 and 8081. First setup downloads Docker images, dependencies and approximately 5.1 GB of local Apertus weights; it needs internet access. Subsequent starts verify and reuse the local model. Generation is asynchronous and CPU-bound.

From a clean checkout, run:

```sh
make run
```

Open [http://localhost:8000/app/](http://localhost:8000/app/). The bootstrap step creates a private synthetic demo account and local configuration. Keep generated credentials and `.runtime/` files private; never commit or paste them. `make run` keeps existing database and document volumes. See [`track_2b/src/intelligence/DEPLOYMENT.md`](track_2b/src/intelligence/DEPLOYMENT.md) for resource, model and configuration details. To stop the stack, run `make stop`.

## Apertus in Comfort

The default path serves the text-only Q4_K_M conversion of Apertus v1.5 8B in a pinned llama.cpp container on the same host. The server selects source evidence for related-record search and earlier packet overviews. A newer structured visit brief implementation organizes selected evidence around a patient's stated purpose and selected context; its deterministic and mocked software checks pass, but live model compatibility has not yet been verified. Journal AI extraction and Health history AI remain experimental; previous real Journal outputs failed validation. These features are not presented as clinically validated. Read the [technical report](track_2b/technical_report.md) and [demo runbook](track_2b/docs/demo-runbook.md) before recording.

## Project contents

- [`track_2b/src/`](track_2b/src/): Django application, worker, React client and local inference tools.
- [`track_2b/data/`](track_2b/data/): authored synthetic evaluations and fictional demonstration documents; currently about 1.8 MB.
- [`track_2b/docs/`](track_2b/docs/): implementation notes, evidence, evaluation limitations and demo instructions.
- [`track_2b/Comfort_Report.pdf`](track_2b/Comfort_Report.pdf): three-page technical report for upload.

Code is Apache-2.0. Authored evaluation data is CDLA-Permissive-2.0; imported synthetic sources retain their own MIT or CC BY 4.0 terms and attribution. See the [data license](track_2b/src/intelligence/DATA_LICENSE.txt) and [provenance card](track_2b/data/ecosystem-v1/DATA_CARD.md). Dataset publication to Hugging Face is optional for Track 2B and has not been performed.

## Submission status

The public repository and technical report are prepared. The project owner still needs to add the two-minute demo URL and upload the repository/report/video through the [official submission portal](https://hackapertus.ch/online-hack/submissions). Submission is complete only after the portal confirms receipt. See [`track_2b/docs/hack-apertus-release-checklist.md`](track_2b/docs/hack-apertus-release-checklist.md).
