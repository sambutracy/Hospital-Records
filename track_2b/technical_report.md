# Comfort — technical report draft

**Track:** Hack Apertus 2B, Own Project. **Working project name:** Comfort. **Repository:** https://github.com/sambutracy/Hospital-Records. Official team roster, final public commit and demo-video URL remain to be supplied. This is the 14 October implementation draft, not the final six-page PDF.

## 1. Summary

Comfort helps a patient organize records across providers, select evidence for a consultation and receive a contributed note while retaining control over access. Apertus proposes metadata, reranks relevant documents, drafts a source-linked overview and selects reviewed general term definitions. Originals and patient-confirmed details remain separate from AI suggestions. The prototype organizes and communicates information; it does not diagnose or recommend treatment.

## 2. Architecture and sovereign target

The target is **on-premise**, under the organization's administration. Docker starts PostgreSQL 18, self-hosted Keycloak 26.8.0, Django 5.2.17/Gunicorn, a serial worker and pinned local CPU inference. Schema migrations use a separate owner service; the application uses a restricted database role. Originals are stored in a private named volume with version/hash lineage and authorized downloads.

Inference runs as UID 10001 on an internal Docker network, with a read-only filesystem/weights, dropped capabilities, a private key file and no published model port. The default local profile disables public hospital lookup; an organization-administered Nominatim endpoint can be configured. Explicit Google Maps links open an external service. Image/package/weight downloads occur during setup. No air-gapped certification or Swiss-cloud residency is claimed. HTTP localhost and Keycloak development mode are synthetic demo settings; production TLS, key/backup/restore/deletion and administrative controls need further review.

## 3. Purposeful use of Apertus

Model identity is **Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF**, a community text-only Q4_K_M conversion of `swiss-ai/Apertus-v1.5-8B` through `andreasmartin/apertus-v1.5-8b-text`. It does not retain the official model's image/audio components. The 5,059,027,136-byte model is pinned to revision `248ec68a63e219e3f061e4c946fc8a20d63b9975` and SHA-256 `a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299`. The official llama.cpp `server-b11429` amd64 image is pinned by digest in `compose.local.yaml`.

Serving uses a 16,384-token context, one slot, six CPU threads and disabled thinking. Assistant requests use temperature 0, task token caps of 700/1000/300 for search/overview/term, a 300-second local request bound and no automatic retries. They run asynchronously. Search performs lexical ranking across all authorized current versions before supplying at most 30 source contexts to Apertus (default local search: ten); coverage/truncation is shown. This is not an embedding index or exhaustive semantic search. Packet drafts use exact selected versions and frozen confirmed metadata. Every item needs a checked verbatim source quotation; correct quotation alone does not prove a paraphrase is supported. Glossary output comes from reviewed authored definitions rather than model-written medical advice. No other model or LLM judge is used.

## 4. Data and continuity

Readable PDFs, photographed JPEG/PNG reports, medical-image exports and Part 10 DICOM originals are accepted at up to 10 MB each; multiple selections are uploaded separately. DICOM inspection reads bounded technical headers. OCR, large studies and diagnostic pixel interpretation are unfinished.

Document dates, visit dates and upload times remain separate, with partial/unknown precision preserved. Episodes group explicit source versions. Personal profiles, Care circle contacts and per-visit medication entries remain private and are not automatically shared or sent to Apertus. Prescribed, reportedly taken, not taken and unknown are distinct medication states; an original prescription is unchanged.

Patient-approved packet reads are recipient-bound, expiring and revocable. Note-submission authority is independent and episode-scoped. A contributed original stays pending and outside records/search/packets until patient acceptance, retaining submitter attribution. Patient confirmation/acceptance does not establish clinical or professional verification. Contact/guardian labels grant no authority. Validated OIDC issuer/subject, rather than names/emails, binds accounts to workspaces.

The frozen evaluation contains 30 authored fictional short texts, 20 retrieval queries and 10 overview screens. These are not actual PDFs, patient uploads, representative cases or a clinician-reviewed gold standard. Content is licensed CDLA-Permissive-2.0. Private runtime data, secrets and weights remain ignored; public `data/` is below 100 MB. The separate data/demo directory includes four one-page fictional PDF originals for the upload flow. No human-subject dataset or Hugging Face release is claimed.

## 5. Evaluation

| Check | Measured result / scope |
| --- | --- |
| Backend contracts | 161 tests passed on PostgreSQL 18 in Docker in 58.15 s. Successful model replies here are mocked; this is not AI accuracy. |
| Frozen literal-keyword baseline | Mean recall@5 0.5588 on 17 positive queries; correct abstention 3/3 on supplied no-match cases. |
| Frozen live Apertus suite | Running; retain attempted/selected/total counts, partial failures and actual latencies. No completed-suite result is claimed yet. |
| Earlier metadata-text-v1 trial | Strict combined result 0/5; unchanged by later prompt revisions. |
| Earlier three development checks | Search 126.24 s, overview 114.88 s, glossary 65.80 s under competing CPU load; not p95 or clinical validation. |
| Exact root launch | `make run` completed against the existing stack; app/database/Keycloak/worker/authenticated inference were healthy. Fresh-package launch is a separate check. |

The harness saves raw responses, fixture/prompt/context/harness hashes, model identity, usage and latency. Invalid attempted positive-query responses count as zero recall; abstention uses a separate denominator. Overview phrase screens cover negation, uncertainty, prescribed versus taken, stopped medicine, conflicts, partial/specimen/report dates, numbers/units/ranges, embedded instructions and incomplete history. They are lexical checks, not clinical or semantic validation. Human review remains necessary.

## 6. Value, cost, scalability and limitations

The connected demo is upload/review → find/select originals → freeze a packet → approve temporary reads → independently authorize a return note → accept/reject it. This supports continuity without giving a recipient generic workspace membership.

Local inference needs no paid API or CSCS credentials, but consumes hardware, power and storage. The model has an 8 GB/six-CPU container bound; the full stack needs approximately 12 GB Docker memory and 12 GB free disk. CPU latency and one generation slot constrain concurrency. No per-patient cost, production capacity, clinical usefulness or health-outcome benefit is claimed. Computed lexical scans need indexing/measurement before larger workloads.

Clinical assertion extraction, a true event timeline, FHIR/IPS exchange, verified professional/guardian authority, delegated assistance, voice/preferences accessibility, OCR and multimodal interpretation remain unfinished. Structural quote/date checks do not establish medical correctness, comprehensive injection resistance or complete-history absence. See [information-status contract](src/records/CLINICAL_DATA.md).

## 7. Reproducibility

Use an x86-64 host, Docker Linux containers, Compose v2 with `--wait`, GNU Make, free localhost ports 8000/8081 and the resources above. Run **`make run` from the repository root**. It generates private synthetic credentials, verifies/reuses weights and starts local inference/application services while retaining existing volumes. Read credentials locally; do not commit them. Initial setup requires network access. Run `make test`, `make trial-test`, `make evaluate` and `make evaluate-live` for separate software, harness and model checks. Results remain in ignored `.runtime/evaluation/`. `MODEL_MODE=external` is an explicit alternative using `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY` and separately assessed endpoint residency/administration. See [deployment](src/intelligence/DEPLOYMENT.md) and [evaluation](src/intelligence/EVALUATION.md).

Final submission still needs its public commit, ≤6-page PDF, ≤2-minute demo URL and portal receipt.

## 8. Next steps and licenses

Obtain clinician/patient feedback, independently annotate information preservation, improve entailment/abstention and retrieval, introduce reviewed clinical assertions and chronology, and verify accessibility/delegation/production operations. Code is Apache-2.0; authored fixture data is CDLA-Permissive-2.0; this report is CC-BY-4.0. Model/runner/map licenses and attribution must be retained; exact organizer licensing obligations remain to be verified.

References: [Track 2B template](https://github.com/HackApertus/project-template/tree/main/track_2b), [source Apertus model](https://huggingface.co/swiss-ai/Apertus-v1.5-8B), [community conversion](https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF), [official llama.cpp Docker documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md), [organizer terms](https://hackapertus.ch/terms-and-conditions).
