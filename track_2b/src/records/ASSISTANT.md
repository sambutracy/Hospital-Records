# Comfort record assistant

The protected workspace now exposes upload, source/preview access, metadata review, keyword search, private packet creation and explicit Apertus assistant requests. Metadata suggestions continue through the ingestion worker. Search, packet overview and term explanation use a separate asynchronous task queue on the same serial, resource-limited worker. No assistant generation runs on page load/sign-in; GETs never create model requests.

API base: `/api/workspaces/{workspace_uuid}/`.

| Method/path | Request or result |
| --- | --- |
| GET `assistant/status/` | Configured model identity and text-only status; does not perform inference or reveal keys |
| POST `assistant/tasks/` | `{kind, parameters}` below; 202 with task ID/state |
| GET `assistant/tasks/` | Latest ten requests belonging to this acting account, subject to continuing authority |
| GET `assistant/tasks/{task_uuid}/` | State, coverage, model/prompt provenance, result/citations if completed |
| POST `assistant/tasks/{task_uuid}/cancel/` | Stop queued/waiting work or prevent publication of an in-flight result; original task/sources retained |

Every route requires the existing session, live `read_workspace_records` capability and task ownership. Packet overviews additionally require `prepare_packet` at creation, processing and result access. Source IDs, worker inputs and returned citations are confined to the workspace and explicit selection. POST retains CSRF. Missing/unavailable/other-account IDs are the same 404; anonymous access is 401. One active request per acting account/workspace/kind is allowed. Failed work is never automatically retried; cancel a waiting request to replace it, or make a new request after failure. Cancellation/revocation cannot retract a provider request already in flight, but stops result publication/access and future calls.

## Search

```json
{"kind":"search","parameters":{"query":"Find my blood count report"}}
```

Apertus ranks at most ten matches from a snapshot of at most the 30 most recently uploaded current records. Inputs include uploaded filenames, patient-confirmed metadata, available text excerpts and selected unverified DICOM technical fields. No image pixels, arbitrary private tags or global patient index are sent. Per-source text is limited to 2,000 characters and total supplied chunk text to 48,000 characters. Coverage records the included/accessible source counts, shortened contexts and extraction availability. This is bounded semantic reranking, not exhaustive vector search or a complete-history claim. Upload order is not a clinical date. Keyword search remains a separately labelled baseline that works without inference.

The model can select only supplied source labels. Each match must cite a chunk from that exact source with a verbatim quote; fabricated IDs, mismatched-source quotes, missing evidence, extra fields and incomplete output fail. Canonical original-download links and version/hash locators are constructed by the server, not the model. Matching/relevance and the natural-language reason require live evaluation; a valid quote alone does not prove relevance or clinical correctness.

## Consultation overview

```json
{"kind":"packet_overview","parameters":{"packet_id":"PACKET_UUID"}}
```

Uses only exact source versions selected in that private packet and its frozen confirmed assertion values. Later metadata corrections do not silently replace the packet's snapshot. Available original text can support up to eight short attributed overview items. Every item requires a checked source quote. The result is a separate draft for patient review; it never modifies the approved packet, original, metadata head or clinical verification level. No diagnosis, treatment recommendation or inference from imaging pixels is requested. Structural citation checks are not semantic/clinical validation of generated prose. Image-only packets have limited technical/metadata context and no automatically inferred findings.

## Term explanations

```json
{"kind":"explain_term","parameters":{"source_version_id":"VERSION_UUID","term":"CBC"}}
```

The term must occur in the selected source context and be in the reviewed initial glossary: MRI/MR, ultrasound/US, CT, CBC and hemoglobin/Hb/Hgb. General definitions are authored paraphrases of linked MedlinePlus sources, checked 13 October 2026; see `glossary.py`. The model selects an allowed definition ID and a matching source quote, or abstains. It cannot return its own definition/advice text or invent a reference URL. The server renders the approved definition and link. Ambiguous context must produce abstention; actual disambiguation quality remains to evaluate. Unknown/absent terms are rejected before generation, without silently answering from general model memory. Definitions do not interpret personal results.

## Provenance and execution

AssistantTask retains actor/workspace, kind/parameters, packet scope, coverage, queue/lease state and generation trace. AssistantSource retains immutable version/extraction linkage, source-label/chunk snapshots, reviewed-metadata revision and snapshot hash. PostgreSQL composite FKs, packet/term/extraction source guards, immutable bindings, closed state transitions and terminal/source history guards supplement API authorization. Runtime permissions prohibit deleting tasks or overwriting/deleting source snapshots. No RLS claim.

Worker checks current authority and original/source-snapshot integrity before inference, again before configuring the generation and under locks before publishing. Output is closed JSON, citations resolve only against the saved chunks, and truncated/provider failures produce safe codes with no partial answer. Source/provider bodies and credentials are not logged. Model ID, community conversion/precision (where relevant), source/input/prompt hashes, version, bounded parameters, latency and returned token usage are recorded without keys. Results flag current-version/metadata changes since request rather than silently pretending to be current.

Missing model configuration yields waiting_model with no result. The explicit local Q4_K_M text profile allows a 300-second HTTP request, 360-second child and 420-second lease; other profiles retain 90-second HTTP, 150-second child and 210-second lease. Heartbeat stays current during processing. Parent discards child stdout/stderr and kills overdue children. All application API/web/worker services remain in Docker; the optional pinned Windows llama.cpp model server runs on the same host. Its weight download and startup are described in the intelligence README; model weights, keys and local artifacts stay ignored. Multimodal image inference/OCR/DICOM viewing remain outside this text assistant slice.

13 October reliability update: local assistant prompts are version 2 and use a source-bound JSON-schema grammar with allowed source/chunk IDs. Original quote/selection/abstention checks still apply; grammar cannot make invented evidence valid. Completed real synthetic checks cover search, a written-report overview and a glossary selection (126.24/114.88/65.80 seconds, with competing CPU requests). The receipt is ignored `.runtime/assistant-v2-live-result.json`. This is three development cases, not a broad quality benchmark.

Image-only packets with no readable report text return an immediate `no_readable_report_text` input limitation. They perform no model generation, retain provenance/snapshots and leave the packet unchanged. Original integrity and live authority are checked. The worker applies the same preflight to older queued requests. The UI requests a written imaging report and no longer presents this case as a generic model failure. Other errors distinguish invalid output, model access, timeout and cancellation. Unsupported/absent glossary terms have specific input messages. Search displays how many sources had extracted report text at request time; later extraction does not retroactively enrich an immutable saved request.

The workspace uses local static JavaScript with same-origin fetch, CSRF, no-store responses and textContent rendering. No patient data is placed in localStorage. CSP permits scripts/connect only from the same origin; it does not permit inline scripts or arbitrary hosts. UI polling reads saved task status and does not retry generation. A page can retain already displayed data in browser memory after authorization changes; subsequent requests/citation downloads still require live authority.
