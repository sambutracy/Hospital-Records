# Apertus access and first text trial

This command-line trial sends only the five authored synthetic development fixtures in `trial_cases.json`. It does not query the patient database, accept document uploads, or run automatically on sign-in. It measures document type, full document date, facility name, abstention and supporting quotes. It is separate from the planned frozen 30-document evaluation and does not validate PDF/image extraction or clinical use.

The trial's full-date field abstains on partial dates; the source retains the original month/year. The later records extractor must preserve date precision according to the reviewed data model rather than silently discard partial dates.

The authored fixtures are provided under CDLA-Permissive-2.0; the full agreement accompanies them in `DATA_LICENSE.txt`. Trial code remains under the repository's Apache-2.0 license.

## Obtain access

The hackathon brief directs participants to [CSCS access sign-up](https://hackapertus.ch/online-hack/cscs/getapi), using the same email as their Devpost registration. On 10 October the owner confirmed they have applied and are waiting for approval. Retain the access email. No email or form submission is automated by the prototype.

[CSCS's published inference documentation](https://docs.cscs.ch/services/inference/api/) describes `/v1/models` and `/v1/chat/completions`, and currently lists `swiss-ai/Apertus-v1.5-8B` and `swiss-ai/Apertus-v1.5-70B`. Its general base URL is `https://api.inference.cscs.ch/v1`. The [Swiss AI evaluation repository](https://github.com/swiss-ai/evals-post-train) also shows a different Swiss AI serving URL. Use the endpoint issued with **your** key rather than assuming the general CSCS URL is the hackathon endpoint. Availability is checked with your key before generation; no automatic model substitution occurs.

Keep the existing generated `.env` and edit only these three lines locally:

```dotenv
LLM_NAME=swiss-ai/Apertus-v1.5-8B
LLM_BASE_URL=YOUR_ACCESS_EMAIL_BASE_URL_ENDING_IN_/v1
LLM_API_KEY=YOUR_PRIVATE_KEY
```

Do not replace `.env` with `.env.example`: that would discard the working identity/database secrets. Do not paste the key in chat, terminal commands, screenshots or public artifacts. The trial loads `.env` itself; no shell export is needed. Explicit process environment values take precedence for managed deployments. For local inference inside Docker, `host.docker.internal` reaches a model server on the host; `localhost` refers to the trial container. Use a separate model port such as 9001, since the web application uses 8000. A local unauthenticated server can use a blank `LLM_API_KEY`; hosted endpoints require a key and HTTPS. TLS verification stays enabled and redirects are rejected.

## Run from the repository root

```sh
make trial-check
make trial-models
make trial
```

Without GNU Make, the equivalent commands are:

```sh
docker compose --project-directory track_2b --file track_2b/compose.yaml run --rm --no-deps trial python src/intelligence/trial.py check
docker compose --project-directory track_2b --file track_2b/compose.yaml run --rm --no-deps trial python src/intelligence/trial.py models
docker compose --project-directory track_2b --file track_2b/compose.yaml run --rm --no-deps trial
```

`check` validates configuration without a network request. `models` checks the key and selected model. `run` makes one model-list request and at most five generation requests (512 output tokens each, temperature 0, no retries). It stops on connection, access or credit failures. This uses the existing small Python Docker image; no GPU packages or weights are downloaded.

Results go to ignored `.runtime/apertus-trials/` with raw responses, usage where supplied, request latency, model/endpoint, prompt and fixture hashes, Python version, exact field-match counts and failure details. Console output contains only the private artifact path and aggregate metrics. Exit 0 means all five passed, 1 means a saved incomplete/failed trial, and 2 means configuration/access failed before generation. Fixed decoding does not guarantee identical live outputs. The small sample's median latency is exploratory; no production p95 or cost is asserted. Supporting-quote grading is intentionally strict: a quoted source line must support the correct field, including the matching reference line; a quote of injected instructions cannot pass simply because it occurs in the source.

Run the offline harness checks with `make trial-test` or:

```sh
docker compose --project-directory track_2b --file track_2b/compose.yaml run --rm --no-deps trial python -m unittest discover -s src/intelligence/tests -v
```

These tests use mocked protocol responses and are **not** measured Apertus results. Only a live trial artifact constitutes evidence of model generation.

## Local Windows text model — 13 October

Comfort now has a local CPU text server. It uses [Colby's Q4_K_M conversion](https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF), derived through [the text-only conversion](https://huggingface.co/andreasmartin/apertus-v1.5-8b-text) from `swiss-ai/Apertus-v1.5-8B`. The adapter records this community identity explicitly; it does not label it as the unchanged official checkpoint. Vision/audio towers are removed and quantization can affect accuracy. MRI/ultrasound pixels are not inputs to this server.

The pinned repository revision is `248ec68a63e219e3f061e4c946fc8a20d63b9975`. The file `apertus-v1.5-8b-text-q4_k_m.gguf` is 5,059,027,136 bytes, SHA-256 `a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299`. Download/verify it from the repository root:

```sh
python track_2b/src/tools/download_local_model.py
```

The script uses a pinned public URL, resumes partial downloads when supported and checks size/hash before activation. Weights go to ignored `track_2b/.runtime/local-model/`; no hosted API credential is needed for this public conversion. Source/model usage terms remain with the model distribution.

Install the official [llama.cpp b11429 Windows CPU x64 archive](https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-win-cpu-x64.zip) in ignored `.dev-tools/llama-b11429/`, retaining its DLLs. The archive SHA-256 is `1283323272b04cd07905816a597a0da810918102de958f4ff6f7bbaa70ed2efe`. Verify it before extraction, for example with PowerShell `Get-FileHash -Algorithm SHA256`. The tested runner reports build 11429, commit `d81235049`. This optional setup is Windows x64 specific; a Linux inference container remains submission work.

After the ordinary app bootstrap has created its private configuration:

```sh
python track_2b/src/tools/start_local_model.py --configure-app
docker compose --project-directory track_2b --file track_2b/compose.yaml up --detach --wait app worker
```

The launcher verifies the model hash again, starts a hidden CPU process bound to `127.0.0.1:9001`, checks `/v1/models` and changes only the existing three ignored LLM settings. It creates an ignored local server key; never copy that key into the report. Docker Desktop reaches this loopback service through `host.docker.internal`. It uses one slot, six inference threads, a 16,384-token context and disabled thinking. The host process is separate from Docker and must be started again after a Windows restart. `make run` starts the application services, not this host model process. Initial downloads need the network; generation itself is local.

Hardware tested: approximately 32 GB RAM, Core i7-1265U, Intel Iris Xe, no NVIDIA GPU. CPU inference is development capacity; live fixture latency and validation failures must be recorded rather than promising production speed. The local profile permits 300-second requests and a bounded 360-second worker child with a 420-second lease. Hosted profiles keep their shorter limits. See [assistant execution](../records/ASSISTANT.md).

## Full-model deployment decision still open

Start with the non-thinking 8B model for this development trial. Try 70B only if 8B quality is insufficient and access permits, preserving both results and documenting the choice. The adapter uses the same API contract for hosted or self-hosted inference.

The local text conversion provides an alternative while CSCS access is pending. It does not supply the full multimodal checkpoint or establish production hardware capacity.

The [official Apertus 1.5 model card](https://huggingface.co/swiss-ai/Apertus-v1.5-8B) requires gated weight access and currently directs local serving to the Swiss AI vLLM image/fork, rather than assuming the ordinary upstream release supports 1.5. For a later on-premise target, record a tested model revision and container digest, hardware/precision, bounded context length, network and resource requirements. The usual hosted CSCS service is development access for the currently selected on-premise target; a Swiss-cloud submission target would require a deliberate architecture decision and evidence covering the whole application and its dependencies. Neither API access nor the auth Docker stack alone proves full sovereign deployability.

Updated on 13 October 2026: local model/runner hashes verified, server started and Docker-to-host discovery verified. Three authored assistant requests completed with checked citations: search (72.96 s), packet overview (95.54 s), glossary selection (69.17 s). These timings include competing requests on the single CPU slot, not a production benchmark. The original five-case metadata trial (`metadata-text-v1`) returned five responses but **0/5 passed** its strict evidence grading; four had matching type/date/facility values, and the injection case failed schema. This is recorded in `.runtime/apertus-trials/20261013T180025Z-c879be88.json` and is not presented as successful evaluation.

The records worker separately uses `records-metadata-v3`, partial-date components and a local JSON-schema grammar; its one authored month-date diagnostic passed source/date checks in 31.36 s after two rejected earlier shapes. Grammar does not prove source truth; the original evidence checks still reject fabricated quotes. This development adjustment does not retroactively change the five-case results or establish unseen-case quality. CSCS credentials remain pending and can replace the endpoint later without changing identity/database secrets.

The same authored PDF then passed the real HTTP retry/background-worker flow in 21.50 s, reaching review_ready with three source-backed proposals while retaining the patient's existing confirmed metadata unchanged. Evidence is saved in ignored `.runtime/metadata-live-result.json`. All 111 native backend tests and 14 offline harness tests passed; application, database, Keycloak and worker were healthy after recreation. An unauthenticated model-list request returned 401. These are local integration checks, not broad accuracy or clean-checkout deployment proof.
