# Apertus queue and CPU performance follow-up

## What was repaired

Two user requests remained queued on the isolated port-8010 installation because
its evaluation configuration deliberately had no continuous worker. The ordinary
port-8000 worker was healthy and its earlier requests had completed. An explicit
`interactive` profile now runs **assistant jobs only** in the isolated installation;
its hundreds of metadata jobs remain under bounded evaluation control.

The worker publishes non-patient liveness information in its private storage
volume. The authenticated status endpoint reports whether processing is available.
The client distinguishes an unavailable worker from a live queue, refreshes pending
tasks every three seconds while visible, refreshes on focus/reconnect, offers a
manual refresh, and shows each saved query, request time and completed processing
time. A pending request prevents accidental duplicate submissions. Normal workers
give interactive requests a turn ahead of bulk ingestion, with a metadata turn
after at most three assistant jobs.

The old six-record overview captured its immutable snapshots before extraction,
so only filenames and manually reviewed dates were available. New overviews with
no readable report text finish with an explicit input limitation, without a model
call. Existing terminal results and snapshots are never rewritten.

## Current local protocol

`local-evidence-v7` uses the same pinned Apertus text weights. The model receives
compact numbered excerpts and returns at most 64 tokens containing selected
numbers. The server maps them back to original source chunks and applies the
existing authorization, original-byte, snapshot and citation checks.

Search retains at most five lexically relevant candidate documents and two
excerpts per document (within the existing 1,800-character/16-excerpt ceiling).
An unsupported query gets a small fallback context and may abstain; absence from
that context does not establish absence from the medical history.

Overviews retain up to two distinct passages per source within the existing
2,400-character/24-excerpt ceiling. Adjacent PDF lines stay together, including
wrapped qualifications. A passage can contain up to 420 characters. Longer
passages expand into two adjacent, exact citations of at most 300 characters
each, displayed together. This preserves every selected word while respecting
the existing API bounds; no database or citation safeguards were relaxed.
The output remains **partial source excerpts**, not a complete clinical summary.

The runtime retains its 16,384-token context, six-CPU/eight-GiB limits, pinned
llama.cpp b11429 image and Q4_K_M weights. It now uses six batch threads, flash
attention and Q8 KV caches. Observed idle container memory changed from about
7.67 GiB to 6.94 GiB. These are point observations, not peak-memory guarantees.
Startup still verifies the approximately five-GB weight file and warms the model.

## Actual local runs, 15 October 2026

These are individual development cases on the same i7-1265U CPU host, with warm
model weights. No API service, GPU or mocked model output supplied these results.
Times below are **processing**, excluding queue wait and client polling.

| Run | Protocol | Processing | Prompt tokens / cached prefix | Result |
|---|---|---:|---:|---|
| Earlier ordinary diabetes search | v4 | 108.48 s | 902 / not captured | Completed, source-supported family-history excerpts |
| Previously queued isolated search | v5 | 17.52 s | 250 / 0 | Completed after the worker was enabled |
| Previously queued isolated overview | v5 | 19.40 s | 367 / 131 | Completed; quotations checked against original PDF pages |
| Ordinary diabetes search, first compact run | v5 | 6.11 s | 189 / 131 | Completed; two original-page quotations verified |
| Lab/prescription overview, final version | v7 | 10.00 s | 248 / 145 | Completed; units, specimen date and medication uncertainty retained |
| Six-record overview, fully cached repeat | v7 | 2.22 s | 737 / 736 | Completed; not representative of a new input |
| Six-record overview after a different input | v7 | 54.73 s | 737 / 145 | Completed; substantive mobility/discharge passages, three exact citations verified |
| Ordinary diabetes search, final version | v7 | 7.11 s | 189 / 131 | Completed; both source quotations retain the father's family-history attribution |

The earlier six-record v4 overview took 170.08 seconds but returned only dates.
Its missing-text snapshots differ from the fresh, readable sources in the new
run, so this is not a controlled like-for-like summarization-quality comparison.
Two intermediate overview attempts (v5/v6) failed validation at the existing
300-character quotation boundary; they remain recorded as failures. The final
fix preserves the longer passage in two citations instead of truncating it.

The final two-document check independently screened `12.1 g/dL`, specimen date
`2026-02-27`, prescription status and unknown medication use. Every returned
quote in the successful follow-ups was checked against the actual cited PDF
page. Literal support and correct JSON do not establish clinical completeness,
semantic correctness for other inputs, or professional review.

## Validation and limits

- 208 native PostgreSQL backend regression tests passed, including restricted
  database roles, immutable provenance, longer quotations, worker scheduling,
  stopped/stale heartbeat handling and missing-text preflight.
- 24 frontend tests passed, including saved-request refresh and grouping the two
  parts of a longer quotation together. Production TypeScript/build checks passed.
- 26 fixture contract tests passed, including rejection of controlled evaluation
  before any requests are created while an interactive worker is running.
- The six-record result and its timing were verified in the actual client.
- Final preservation checks retained every pre-existing workspace, record and
  source version and verified their original bytes. Both application workers
  and the shared local inference service were healthy after deployment.
- Private input/output receipts, failures, cache statistics, source checks and
  screenshots remain in ignored `.runtime/apertus-performance/`. Earlier frozen
  evaluation files were not modified or pooled with these development cases.

Cache reuse materially affects latency. Larger or unfamiliar inputs, other
users' queued jobs and host load can take longer. No sub-ten-second guarantee
is made. A bounded excerpt can still omit relevant surrounding context, and
only two of the six sources were cited by this overview. Review the originals.
Image interpretation and OCR remain outside this text-model improvement.
