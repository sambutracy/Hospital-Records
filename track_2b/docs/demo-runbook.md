# Comfort technical demo runbook

Use synthetic accounts and records only. This is a two-minute walkthrough of the current prototype, not a clinical performance demonstration. Do not trigger inference during recording; select a previously completed local Apertus request first.

## Start and check

From PowerShell in a clean checkout:

```powershell
Set-Location D:\Hospital
make run
```

First run downloads the pinned local text model (about 5.1 GB) and required images. The local CPU model can take minutes to initialize. Later runs verify/reuse the cached model and retain existing database and document volumes. Keep the private generated credentials and `.runtime/` files on the machine; do not put them in the video.

Check service state and app health without printing secrets or service logs:

```powershell
$compose = @('--project-directory', 'track_2b', '--file', 'track_2b/compose.yaml', '--file', 'track_2b/compose.local.yaml')
docker compose @compose ps
Invoke-WebRequest -Uri 'http://localhost:8000/health/' -Method Get
```

Open [http://localhost:8000/app/](http://localhost:8000/app/). Sign in with an existing fictional account. If its local sign-in details are needed, retrieve them privately on the owner machine from `track_2b/.runtime/demo-credentials.txt`; never paste or show the file contents. Select a synthetic patient workspace and a visit with only relevant fictional records.

## Choose a verified result

Use an already completed local Apertus related-record search or packet overview, not a newly generated request. Previously recorded local examples include a related-record search completed in 7.11 seconds and a lab/prescription overview completed in 10.00 seconds. A separate six-record overview took 54.73 seconds and cited two of six selected records. Timings are individual warm-cache CPU development runs, not guarantees. Confirm in the app before recording that the chosen result still loads and its linked source originals open.

The current structured Visit Brief is a separate implementation and has not yet been validated with a live Apertus call. Do not present it as a confirmed model result. Journal organization and Health history AI also remain experimental; previous Journal outputs failed strict validation. Avoid those screens as evidence of successful AI performance.

## Two-minute action and narration

**0:00–0:15 — Home.** “Comfort helps a patient keep records from different providers together and prepare for a visit. The patient remains in control of what is selected and shared.” Show the patient workspace and available next actions; do not imply a recommendation or appointment exists.

**0:15–0:35 — Records.** Open Records and show a synthetic source with reviewed type/date/facility metadata. Say: “The original stays preserved; the reviewed description helps the patient find it.” Open the original briefly if readable. Avoid claiming OCR or image interpretation.

**0:35–1:15 — Apertus search.** Open the previously completed local search. Say: “Apertus runs locally and helps select relevant evidence from the authorized records. These are excerpts, not a complete medical history.” Open one result's original source and point out its exact quotation and attribution. If the visible source concerns a relative, explicitly retain that attribution; do not frame it as the patient's diagnosis.

**1:15–1:45 — Visit overview.** Show the already completed overview and its original links. Say: “This helps organize a small, selected set of records. The citations let the patient check context; they do not prove medical correctness or completeness.” Do not represent an older planned procedure as completed or a prescribed medicine as confirmed use.

**1:45–2:00 — Patient control.** Show the selection/review or sharing controls without granting access. Say: “The patient reviews the sources and decides what to share. AI output does not change the original record or create a diagnosis.” End on the workspace, not an unverified experimental feature.

## If the result is pending or fails

Do not submit a duplicate request or trigger a fresh model call for the recording. Check that Docker shows the app, worker and inference services running and the health endpoint responds. Allow an existing task to finish; CPU inference is asynchronous and can be slow. If the chosen prior result is unavailable, use the Records and patient-review portions of the walkthrough and describe the AI result as unavailable. Do not substitute a mocked result or edit task status.

The app and worker may be rebuilt without resetting volumes using:

```powershell
docker compose @compose build app worker
if ($LASTEXITCODE -eq 0) { docker compose @compose up --detach --wait --no-deps app worker }
```
