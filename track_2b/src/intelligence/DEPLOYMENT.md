# On-premise local Apertus deployment

The repository-root `make run` now prepares and verifies the pinned text weights, then starts PostgreSQL, Keycloak, migrations, private storage, Django, the serial worker and **containerized Apertus inference**. No separately started Windows process is required by this launch path. The `track_2b/` layout is retained.

Prerequisites: GNU Make, Docker with Linux containers and Compose v2 supporting `--wait`, x86-64 host, free localhost ports 8000/8081, approximately 16 GB available host memory with at least 12 GB allocated to Docker, and at least 12 GB free disk for model/images. The model container is bounded to 8 GB and 6 CPUs; other services need additional memory. CPU generation is asynchronous and may take more than a minute. Resource limits are not measured production capacity guarantees.

```sh
make run
make evaluate
make evaluate-live
make stop
```

Initial setup downloads images, Python dependencies and 5,059,027,136 bytes of model weights. The model downloader resumes a partial download and verifies the entire file against SHA-256 before activation. Repeated startup verifies/reuses the local model, keeps existing `.env`, realm, database and document volumes, and retains the inference key. Do not delete volumes to update the app.

For an isolated demonstration, set `COMPOSE_PROJECT_NAME`, `APP_PORT` and `KEYCLOAK_PORT` before the first launch. `APP_HOST=127.0.0.1` can keep its browser cookies separate from a primary `localhost` demo. The generated realm binds exact callback/logout origins to that host/port; existing realms cannot silently change origin. `MODEL_CACHE_DIR` can point to an existing verified local model directory so a separate source package does not download another 5 GB. This shares only the local model/key cache, never the patient database or original-document volume. A fresh-package check using a warm cache is distinct from repeating the first network download.

Local app search preselects ten sources by default (`ASSISTANT_SEARCH_SOURCE_LIMIT`, maximum 30). The result exposes actual coverage. Search output is capped at three short matches; overview output at four short items. These bounds keep the CPU prototype's generation cost finite; no interactive or production latency guarantee is made.

For the local text model, `LOCAL_ASSISTANT_MODE=extractive` is the default.
Apertus selects evidence identifiers from at most 24 excerpts and 2,400 source
text characters, with a 128-token output limit. Comfort expands only exact
immutable source passages and applies the usual source/citation validation.
Search results and overviews identify these as selected source excerpts; they
are not rewritten clinical summaries. This reduces input/output work while
retaining explicit limits on coverage. `LOCAL_ASSISTANT_MODE=generative`
reproduces the earlier local prose protocol; hosted Apertus behavior is unchanged.
Changing the mode affects new requests, not saved results or patient metadata.
Current search uses at most 16 excerpts and 1,800 source-text characters.
Overview passage selection uses a lexical clinical-content prior and retains
dated evidence, with a narrative fallback for unfamiliar vocabulary. This is
partial selection: wrapped qualifications can be omitted at passage boundaries.
Review the linked originals; these drafts are not complete clinical handoffs.
For measured baseline failures and separately recorded follow-ups, see the
[synthetic ecosystem report](../../data/ecosystem-v1/RESULTS-functional.md).

Serving uses the official llama.cpp `server-b11429` Linux amd64 image pinned to manifest digest `sha256:a7c742ec2070a17d715c02d4329c049a984c81c3234f9ab14bdb14e46b077317`. Model SHA-256 is `a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299`, from repository revision `248ec68a63e219e3f061e4c946fc8a20d63b9975`. Identity remains **Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF**, a community Q4_K_M conversion of `swiss-ai/Apertus-v1.5-8B` through `andreasmartin/apertus-v1.5-8b-text`. It contains text capabilities only; it is not the unchanged official multimodal checkpoint.

The server runs as UID 10001 with read-only weights/root filesystem, no published model port, dropped capabilities and an internal Docker network. Only the app/worker/evaluation containers join that network. `LLM_API_KEY_FILE` supplies a private key file rather than placing its value in the compose file. Existing hosted credentials are retained in ignored configuration but overridden for this local launch.

Public Nominatim search is disabled by default in the local deployment. Facility names can still be entered manually. To use an organization-administered Nominatim service, set `ON_PREMISE_FACILITY_SEARCH_URL` and restart the app. A saved Google Maps link opens an external service only on an explicit click. The model's internal network is not a claim that every other container is air-gapped. Build/setup network downloads are separate from runtime processing.

For a separately configured trusted Apertus endpoint, use `make run MODEL_MODE=external` and the standard `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY` values in ignored `.env`. This uses the original compose configuration, including its explicitly configured facility endpoint. Verify endpoint residency/administration before asserting a sovereign target. The older Windows runner remains a development alternative documented in [README.md](README.md).

This is a synthetic **development deployment**: HTTP localhost listeners and Keycloak `start-dev` remain. On-premise deployability does not establish production readiness, clinical validation, verified guardianship/professional credentials, encryption of backups, or regulatory compliance. TLS, operational key management, restore/deletion procedures and administrative controls need a separate production deployment review.

Sources: [official llama.cpp Docker documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md), [pinned runner release](https://github.com/ggml-org/llama.cpp/releases/tag/b11429), [quantization repository](https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF), [source model](https://huggingface.co/swiss-ai/Apertus-v1.5-8B).
