# Comfort: records backend and servers

The patient-to-recipient return workflow is described in [CONTINUITY.md](CONTINUITY.md): exact approved packet reads, independent note-submission authority, patient review, named episodes and precision-preserving document-date order. All 155 identity/records/assistant/continuity/profile/medication PostgreSQL tests passed on 14 October. Invited accounts do not establish verified professional identity. [Medication notes](MEDICATIONS.md) preserve distinct prescribed/taken reports across visits. The private [profile and Care circle](../identity/PROFILE.md) do not automatically grant or disclose records.

The local Compose stack runs PostgreSQL 18, Keycloak 26.8.0, Django/Gunicorn and a separate Python extraction/assistant worker. The web/worker use the restricted `continuity_app` role; only the migration service receives owner credentials. A pinned local CPU Apertus 8B text conversion can now serve inference while CSCS approval is pending; see [setup](../intelligence/README.md). No remote server was provisioned. The Windows host inference setup still needs a portable submission deployment.

From the repository root (the directory containing `track_2b/`):

```sh
make run
make test
```

Without GNU Make, use:

```sh
docker compose --project-directory track_2b --file track_2b/compose.yaml run --rm --no-deps bootstrap
docker compose --project-directory track_2b --file track_2b/compose.yaml up --build --detach --wait app worker
docker compose --project-directory track_2b --file track_2b/compose.yaml run --rm --no-deps migrate python src/manage.py test identity records --settings=continuity.test_settings --noinput
```

Startup applies identity/records migrations, adds the three explicit self-record actions, initializes only the private volume's directory ownership, then starts the application and worker. Repeat startup retains databases, demo secrets and originals. Never use `down --volumes` to restart this project. The new `private_documents` volume is not host-published or served through a public media URL. Application files have generated workspace/version keys, exclusive creation and read-only mode; database source versions are immutable. This is not a filesystem WORM or malware-scanning claim. Reference hashes are checked before extraction/download. Back up database and document volumes together; an unexpected process crash between file creation and database commit may leave a private unreferenced object. Automatic orphan deletion is not implemented.

The workspace accepts a selection of up to 30 files, at most 10 MB each. It uploads each in its own authorized request, displays per-file saved/duplicate/failure status and retains failed files for an explicit retry on the same page. Successful originals are not resent by **Retry failed files**. PDFs use document classification, DICOM uses medical_image and the selected report/image mode applies to JPEG/PNG. Mixed-format batches are supported; mixed JPEG/PNG purposes should be sent in separate selections. Leaving the page loses unsaved file/retry selections. The multipart API remains one original per request, so server memory/body limits are retained. A batch is not an all-or-nothing transaction: successful files remain saved if another fails. The first record-list page refreshes processing state automatically without changing open review fields.

## Session API

The review form now provides an in-app [hospital search and selection](FACILITIES.md): search by hospital/town, choose a result, and confirm to store its source-linked location and Google Maps pin. OpenStreetMap supplies search results; provider access and deployment limits are documented there.

Sign in through the existing Keycloak browser flow. These endpoints use the resulting Django session and live local capability checks; they do not accept raw bearer tokens or passwords. GET the records endpoint to receive the CSRF cookie, then send its value as `X-CSRFToken` for POST, from the same application origin. CSRF remains enabled. Anonymous reads return 401; unavailable/unauthorized workspace or resource IDs return the same 404. Health data responses remain private/no-store.

Upload, review, packet creation and background processing also require continuing source-read authority. A write/packet capability cannot bypass a revoked read capability by returning a duplicate descriptor, copying proposal evidence, or rendering a packet snapshot.

Base path: `/api/workspaces/{workspace_uuid}/`.

| Method/path | Input/result | Required action |
| --- | --- | --- |
| GET `records/?q=...&offset=0` | Up to 50 records, current source/version, confirmed metadata and job state. Simple keyword search over filename/confirmed facility/type; ordered by upload time, never presented as inferred clinical chronology. | read_workspace_records |
| POST `records/` | Multipart `file`; one PDF/JPEG/PNG/Part 10 DICOM up to 10 MB. Optional `content_kind`: document (default) or medical_image. DICOM always uses medical_image. Returns source version, 201 new / 200 workspace-local duplicate. | upload_source |
| GET `records/{record_uuid}/` | Current version, version list, patient review history and separate AI proposals. No private storage path or credentials. | read_workspace_records |
| POST `records/{record_uuid}/versions/` | New original bytes in multipart `file`; monotonic version/predecessor, preserves old source. An existing duplicate belonging to another record is 409. | upload_source |
| GET `versions/{version_uuid}/original/` | Checksum-verified original attachment, through authorization; no public URL. | read_workspace_records |
| GET `versions/{version_uuid}/image/` | Source-linked technical image inspection and optional preview URL. Pending/failed inspection reports the current job state with 202. | read_workspace_records |
| GET `versions/{version_uuid}/preview/` | Checksum-verified derived PNG preview. DICOM returns 409 external_dicom_viewer_required. | read_workspace_records |
| POST `records/{record_uuid}/review/` | Confirm/correct typed metadata using expected revision and exact current source-version ID. New immutable assertions; stale review is 409. | review_metadata |
| POST `jobs/{job_uuid}/retry/` | Explicit new attempt for latest failed/waiting job, at most five attempts; retains previous attempt. | upload_source |
| GET/POST `packets/` | List private packets / freeze exactly selected version IDs and confirmed assertion snapshots. | read_workspace_records / prepare_packet |
| GET `packets/{packet_uuid}/` | Exact approved source and metadata snapshot. | read_workspace_records |

Review JSON:

```json
{
  "source_version_id": "SOURCE_VERSION_UUID",
  "expected_revision": 0,
  "values": {
    "document_type": "lab_report",
    "document_date": {"precision": "month", "year": 2026, "month": 9, "day": null},
    "facility_name": "Fictional Cedar Clinic"
  }
}
```

Optionally add `proposal_id` to retain the corresponding AI evidence for fields whose values are unchanged. Changed fields are patient assertions, without reused contradictory model evidence. Each review confirms all three fields in one transaction; it cannot change patient/workspace, original bytes or the clinical verification level. Supported record types: lab_report, referral, consultation_note, prescription, discharge_summary, imaging_report, medical_image, other. An unknown date has precision unknown and all components null; an absent facility is null. Month/year precision remains intact. An absent assertion before review differs from an explicit unknown assertion.

Packet JSON:

```json
{"purpose": "Demo consultation", "source_version_ids": ["SOURCE_VERSION_UUID"]}
```

A consultation packet is a private immutable revision. Later source corrections/replacements do not change its chosen versions or metadata snapshots. It includes no AI-generated clinical summary or unselected record. Creating it does not itself grant access. The separate continuity routes now provide recipient grants with expiry/revocation, an independently authorized contribution inbox and named episodes; appointment/referral lifecycles remain pending. See [CONTINUITY.md](CONTINUITY.md).

## Extraction and model states

Text extraction supports PDFs with readable text on every page, at most 25 pages and 100,000 text characters. It retains page-numbered text with parser version/hash. Valid JPEG/PNG photographs of documents and PDFs with empty/unreadable pages become `needs_ocr`; medical images use the separate manual-review path below. Encrypted, malformed or oversized-complexity PDFs fail with a safe code. Originals remain available to their authorized patient in either case. MIME signatures/extension and parser checks are not clinical validation or an antivirus service. Use authored synthetic records for this demo.

Jobs transition queued → processing → waiting_model / needs_ocr / failed / review_ready / manual_review. Each refers to an exact source version and initiating account. The worker processes one record/assistant job at a time and rechecks live authority. The local CPU profile has a 300-second HTTP timeout, 360-second child bound and 420-second lease; other profiles use 90/150/210 seconds. Heartbeats remain current during generation. The extraction worker container is limited to 1 GB, one CPU and 64 processes; the separate host model has its own resource needs. Interrupted/invalid generations fail without automatic retries. Child parser/model output and exception bodies are not logged.

Without complete `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY`, text is retained locally and the job waits, without invented model data. After approval, edit only these existing ignored `.env` lines and recreate the worker:

```sh
docker compose --project-directory track_2b --file track_2b/compose.yaml up --detach --wait worker
```

The worker reconsiders waiting jobs only when configuration validates. It checks the selected Apertus v1.5 model is available, makes one bounded generation request without retries, and records model/prompt/source/text provenance and returned token usage. Output must be strict JSON with closed fields, real/partial date shape and verbatim page quotes; date/facility claims need matching tokens in their quotes. These are structural/lexical checks, not proof of clinical correctness or full semantic/injection robustness. All valid model metadata is a proposal until reviewed; late model results never overwrite patient-confirmed heads. API failures and invalid output become safe failure codes; an explicit retry creates a new preserved attempt.

For the explicit local text conversion, prompt `records-metadata-v3` uses a JSON-schema grammar requiring source locator objects. Unknown values remain unknown; a quote of an inspected excerpt does not prove missing information. Hosted profiles do not assume support for llama.cpp's schema contract. The format is retained with generation parameters. Grammar cannot bypass the date/source checks, and the earlier failed five-case text trial is preserved in the [model verification notes](../intelligence/README.md).

The protected workspace now has upload, keyword/semantic search, review, preview/download, packet creation and assistant-result screens. [Assistant routes](ASSISTANT.md) add bounded semantic reranking, exact-selected-source overview drafts and glossary-backed term explanations. A draft never modifies the original or approved packet. Image pixels are not sent to the local text model.

## Image exports and DICOM — 13 October

Use `content_kind=medical_image` for MRI/ultrasound JPEG or PNG exports; use document for a photographed report. File kinds are immutable source facts selected at intake, not verified clinical classifications. The same bytes cannot silently acquire another kind through a duplicate upload. PDF reports use document; DICOM is classified as medical_image at intake. Header patient identifiers never choose/link a workspace or user.

The bounded worker verifies/decodes a single-frame JPEG/PNG (at most 16 million pixels), creates a PNG preview with a maximum side of 512 pixels and size of 1 MB, and stores it as an immutable source-linked ImageInspection. Preview copies pixels into a fresh image without EXIF/GPS metadata; visible labels within pixels remain, so this is not de-identification. The preview is marked non-diagnostic and is not an original or a clinical viewing tool. Medical images reach manual_review without a model call or invented findings. Valid photographed reports retain a preview and enter needs_ocr until OCR is implemented. Invalid/unsupported raster images fail safely while the uploaded bytes remain downloadable.

Part 10 `.dcm`/`.dicom` files require the DICM prefix. Header inspection checks file/dataset SOP UID agreement and image dimensions, then retains an explicit whitelist: modality, study date, institution, study/series descriptions and study/series/instance UIDs with DICOM tag locators. PatientName, PatientID, birth dates and arbitrary private tags are not returned by this API. Whitelisted free-text fields can still contain sensitive information; access remains private. These are source_header_unverified values and never automatically become patient-confirmed metadata. No LLM is needed for deterministic tag extraction. A header check is not full DICOM conformance or pixel validation.

Compressed pixels and multiframe originals are preserved without decompression. This slice does not render DICOM, validate its pixels, reconstruct MRI volumes or play ultrasound cine loops; use the original with a suitable external DICOM viewer. The 10 MB per-file limit remains; a complete study can exceed it and contain many instances. Archive/bulk import, a dedicated study/series model and in-app study viewer remain pending. A private consultation packet can select an imaging original and its written report together; no clinical association is inferred automatically.

Full Apertus v1.5 8B supports image inputs. The proposed community text-only GGUF removes that capability. A future vision path must use a multimodal checkpoint/server and bounded derived images/frames with source-version, instance/frame and processing provenance; native DICOM files are not passed directly as ordinary image inputs. Vision-derived suggestions stay separate from confirmed record metadata. Automated scan diagnosis or treatment advice is outside this records prototype. Image/vision quality has not been evaluated on Apertus while access is pending. [Official model card](https://huggingface.co/swiss-ai/Apertus-v1.5-8B), [DICOM Part 10](https://dicom.nema.org/medical/dicom/current/output/chtml/part10/chapter_7.html), [pydicom pixels](https://pydicom.github.io/pydicom/stable/tutorials/pixel_data/introduction.html).

## Database safeguards and checks

PostgreSQL composite workspace FKs backstop source/job/evidence/assertion/packet boundaries. Additional triggers enforce same-record predecessor/head, same-version evidence and field lineage, confirmed metadata pointers, calendar dates, source/artifact/assertion immutability, and frozen approved packet items. A transaction locks the patient workspace and explicit capability/membership for writes; review also compares the source-version/revision. Permissions are checked per action; membership, provider claims, staff flags and missing read permission do not imply any other capability. PostgreSQL RLS is not claimed.

Verified on 10 October 2026: all 68 identity/records tests passed on native PostgreSQL. The actual running HTTP API and worker passed a synthetic upload/duplicate/download/review/packet check, including denial of an unrelated patient. These HTTP checks used local synthetic session fixtures; earlier real Keycloak browser checks are documented in the application README. Restarting PostgreSQL, Keycloak, app and worker retained the exact original checksum, extraction, approved packet snapshot and waiting job. All four services returned healthy. Migration drift and Compose configuration checks passed.

Tests distinguish mocked model-protocol outputs from live Apertus measurements. CSCS approval remains pending, but actual development generations have been recorded using the pinned local text conversion; broader quality evaluation remains unfinished. The exact clean-checkout `make run` remains unverified on this Windows host; its Docker Compose launch commands were exercised against the existing local stack.

On 13 October the Makefile moved to the repository root following the organizer's clarification. GNU Make parsed/dry-ran all targets in a disposable container; equivalent root-level bootstrap/build/start Compose commands completed with all four services healthy and existing configuration retained. This is an existing-stack launch check, not a clean-checkout result.

Later on 13 October all 83 identity/records tests passed on native PostgreSQL, including the new image/DICOM paths, source/header matching, manual-review immutability, preview isolation/EXIF removal/limits and restricted-role processing. The actual local HTTP API and real worker processed authored synthetic MRI PNG, MRI DICOM and multiframe ultrasound DICOM under continuity_app; original hashes matched, the PNG preview hash matched, all three jobs reached manual_review without AI proposals, and an unrelated synthetic actor's preview request returned 404. These fixtures validate the bounded handling pipeline, not clinical accuracy, real-study compatibility or Apertus vision performance.

Restarting all four servers retained those exact source IDs, inspections, preview/original hashes and manual-review states; all services returned healthy. The expanded text-metadata vocabulary is versioned as records-metadata-v2 and its prompt hash is recorded on each actual generation.

14 October review update: 161 PostgreSQL tests pass, including profile/medication, continuity and frozen-evaluation boundaries. Default root `make run` includes containerized Apertus; see [DEPLOYMENT.md](../intelligence/DEPLOYMENT.md). Literal keyword search now includes extracted text; Apertus candidates use lexical ranking across all authorized current versions before the bounded model snapshot. See [CLINICAL_DATA.md](CLINICAL_DATA.md) for patient-reported/confirmed/AI distinctions. Earlier dated test counts and standalone Windows setup above are historical.
