# Comfort synthetic ecosystem — functional results

## Repository changes and compatibility

Added a separate resumable population, pinned-source manifests, guarded bounded worker/capture commands, integration evaluation, regression tests and developer instructions. Local CPU assistant generation now supports bounded extractive selection, reusing the normal immutable source snapshots, authority checks and citation validation. Authentication, database constraints, existing app data and frozen evaluation v1/v2 remain intact. The abandoned branch was removed after explicit user approval with SHA-guarded remote deletion.

Verification: 193 PostgreSQL backend tests, 21 frontend tests and 22 fixture contract tests passed. Frontend production build: passed. Root make run: passed on existing persistent stack; not a fresh checkout; root make test: passed on PostgreSQL. An existing-stack launch is not a fresh-checkout claim.

Ordinary app update: mode=extractive, protocol=local-evidence-v4, existing record/version/workspace counts preserved=True, health HTTP=200. Current-protocol source-request equivalence verified=True; see the paired receipts for cases and hashes. These are not additional model samples.

## Synthetic population

15 patient scenarios, 10 additional actors; 25 bound canonical accounts. 308/308 initial documents seeded. Every actor also has their own patient workspace.

| Patient | Initial documents |
|---|---:|
| P01 | 7 |
| P02 | 38 |
| P03 | 35 |
| P04 | 21 |
| P05 | 8 |
| P06 | 10 |
| P07 | 20 |
| P08 | 17 |
| P09 | 14 |
| P10 | 8 |
| P11 | 12 |
| P12 | 8 |
| P13 | 100 |
| P14 | 0 |
| P15 | 10 |

Auxiliary uploads: A10-AUX, P07-accepted-AUX, P14-AUX. Accepted contributions are additional records, with their own original and submitter attribution.

Sources: pinned NHS synthetic silver notes (MIT), original morzel.net/Synthea benchmark PDFs (CC BY 4.0), and explicitly authored fixtures (CDLA-Permissive-2.0). See [data card and attribution](DATA_CARD.md), [scenario matrix](SCENARIOS.md), population/source/text locks. Source patients are never mixed across workspaces.

## Workflow and security results

Original integrity/pagination: 323 checks, passed=True. Functional authorization/journey checks: 83, all passed=True, complete=True.
Additional record/filter/provider journeys: 25 checks, all passed=True.
Checks cover fresh authentication/onboarding, exact packet scope, cross-recipient/source denials, actual expiry/revocation, independently granted contribution, pending/accepted/rejected boundaries, original integrity/submitter attribution, reported-role negative permissions and dual own/received contexts. Relationship labels establish no delegation or professional verification.

## Actual Apertus results

Runtime: community text-only Q4_K_M conversion of Apertus v1.5 8B (`Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF`), served locally by the pinned llama.cpp container. This is not the unchanged multimodal checkpoint. Exact weight/revision hashes, prompts, configurations and source snapshots are recorded per attempt.
Schema and source-quote validity: 18/23 attempted cases. This is not a measure of semantic or clinical correctness.

Run scopes: `{"functional_case": {"planned_cases": 17, "attempted": 7, "valid_outputs": 3, "failed": 4, "retrieval": {"successful_positive_case_denominator": 0, "conditional_recall_at_5": null, "successful_absent_cases": 0, "correct_absent_abstentions": 0}}, "compact_control": {"planned_cases": 3, "attempted": 3, "valid_outputs": 2, "failed": 1, "retrieval": {"successful_positive_case_denominator": 1, "conditional_recall_at_5": 1.0, "successful_absent_cases": 0, "correct_absent_abstentions": 0}}, "local_cpu_followup": {"planned_cases": 6, "attempted": 6, "valid_outputs": 6, "failed": 0, "retrieval": {"successful_positive_case_denominator": 2, "conditional_recall_at_5": 1.0, "successful_absent_cases": 1, "correct_absent_abstentions": 1}}, "local_cpu_v2_followup": {"planned_cases": 3, "attempted": 3, "valid_outputs": 3, "failed": 0, "retrieval": {"successful_positive_case_denominator": 1, "conditional_recall_at_5": 1.0, "successful_absent_cases": 0, "correct_absent_abstentions": 0}}, "local_cpu_v3_followup": {"planned_cases": 3, "attempted": 3, "valid_outputs": 3, "failed": 0, "retrieval": {"successful_positive_case_denominator": 0, "conditional_recall_at_5": null, "successful_absent_cases": 0, "correct_absent_abstentions": 0}}, "local_cpu_v4_followup": {"planned_cases": 1, "attempted": 1, "valid_outputs": 1, "failed": 0, "retrieval": {"successful_positive_case_denominator": 0, "conditional_recall_at_5": null, "successful_absent_cases": 0, "correct_absent_abstentions": 0}}}`. Compact single-source controls and CPU extractive follow-ups are separate from the initial functional cases. Extractive outputs are selected verbatim passages, not newly written summaries. Earlier failures remain in their original rows. Unexecuted larger cases remain labelled with their runtime-gate reason; they are not successful evaluations.

| Case | Scope | Kind | State / error | Structural/source quotes |
|---|---|---|---|---|
| metadata-P01-X-001 | functional_case | metadata | review_ready  | True |
| metadata-P01-X-002 | functional_case | metadata | review_ready  | True |
| metadata-P15-X-008 | functional_case | metadata | failed invalid_model_output | False |
| metadata-P15-X-009 | functional_case | metadata | review_ready  | True |
| q01 | functional_case | search | failed model_access_failed | False |
| q02 | functional_case | search | not_attempted  | None |
| q03 | functional_case | search | not_attempted  | None |
| q04 | functional_case | search | not_attempted  | None |
| q05 | functional_case | search | not_attempted  | None |
| q06 | functional_case | search | not_attempted  | None |
| o01 | functional_case | packet_overview | failed model_access_failed | False |
| o02 | functional_case | packet_overview | not_attempted  | None |
| o03 | functional_case | packet_overview | not_attempted  | None |
| q07 | functional_case | search | not_attempted  | None |
| o04 | functional_case | packet_overview | not_attempted  | None |
| o05 | functional_case | packet_overview | not_attempted  | None |
| q08 | functional_case | search | failed model_access_failed | False |
| cq01 | compact_control | search | completed  | True |
| co01 | compact_control | packet_overview | failed invalid_model_output | False |
| co02 | compact_control | packet_overview | completed  | True |
| cpu-q01 | local_cpu_followup | search | completed  | True |
| cpu-o01 | local_cpu_followup | packet_overview | completed  | True |
| cpu-q08 | local_cpu_followup | search | completed  | True |
| cpu-co01 | local_cpu_followup | packet_overview | completed  | True |
| cpu-co02 | local_cpu_followup | packet_overview | completed  | True |
| cpu-q06 | local_cpu_followup | search | completed  | True |
| cpu2-o01 | local_cpu_v2_followup | packet_overview | completed  | True |
| cpu2-q08 | local_cpu_v2_followup | search | completed  | True |
| cpu2-co01 | local_cpu_v2_followup | packet_overview | completed  | True |
| cpu3-o01 | local_cpu_v3_followup | packet_overview | completed  | True |
| cpu3-co01 | local_cpu_v3_followup | packet_overview | completed  | True |
| cpu3-o02 | local_cpu_v3_followup | packet_overview | completed  | True |
| cpu4-co01 | local_cpu_v4_followup | packet_overview | completed  | True |

### Local CPU comparisons

| Reference case | Original protocol | Extractive v1 | Extractive v2 | Extractive v3 | Extractive v4 |
|---|---|---|---|---|---|
| q01 | failed | completed (217.9s) | not run | not run | not run |
| o01 | failed | completed (111.5s) | completed (108.9s) | completed (37.2s) | not run |
| q08 | failed | completed (170.9s) | completed (103.5s) | not run | not run |
| co01 | failed | completed (57.4s) | completed (47.2s) | completed (16.3s) | completed (27.6s) |
| co02 | completed (151.4s) | completed (46.8s) | not run | not run | not run |
| q06 | not_attempted | completed (152.1s) | not run | not run | not run |
| o02 | not_attempted | not run | not run | completed (45.7s) | not run |

These are separate saved attempts, not replacements. CPU v1 reduced output to evidence IDs but omitted the medication qualification in o01 and selected a bare heading in co01. CPU v2 added per-source selections and tighter search bounds but still selected administrative text. Its co01 result collection was interrupted by an SSO refresh branch; the finished task was subsequently recovered through the normal API with zero model replays. The client now uses a fresh local cookie jar and verifies the same identity on reauthentication. CPU v3 added a lexical clinical-passage prior, dated evidence and a narrative fallback. CPU v4 retains mixed clinical/administrative narrative that the earlier prior suppressed. These priors can omit important content and do not establish clinical relevance or complete coverage. These are reused development references, not an unseen test set. Timings share the development machine and are not isolated hardware benchmarks.

Metadata exact field accuracy, counting failed attempts: `{"attempts": 4, "accepted_output_field_accuracy": {"document_type": {"correct": 3, "attempted_denominator": 4, "accuracy_counting_failed_attempts": 0.75}, "document_date": {"correct": 3, "attempted_denominator": 4, "accuracy_counting_failed_attempts": 0.75}, "facility_name": {"correct": 3, "attempted_denominator": 4, "accuracy_counting_failed_attempts": 0.75}}, "raw_candidate_field_accuracy": {"document_type": {"correct": 4, "attempted_denominator": 4}, "document_date": {"correct": 3, "attempted_denominator": 4}, "facility_name": {"correct": 4, "attempted_denominator": 4}}}`.

Retrieval metrics on successful responses only: `{"recall_at_5": {"mean": 1.0, "successful_case_denominator": 4}, "precision_at_5": {"mean": 0.24000000000000002, "successful_case_denominator": 5}, "returned_precision": {"mean": 1.0, "successful_case_denominator": 4}, "reciprocal_rank": {"mean": 1.0, "successful_case_denominator": 4}, "correct_absent_abstentions": {"correct": 1, "successful_absent_cases": 1}, "attempted_searches": 7, "failed_or_missing_search_responses": 8, "failed_search_requests": 2, "not_run_search_cases": 6, "end_to_end_recall_at_5": {"mean": 0.6666666666666666, "attempted_positive_case_denominator": 6, "scope": "whole pipeline; failed requests count as zero, not as model ranking errors"}}`.
Precision@5 keeps denominator five; this app returns at most three model matches. Returned precision is separate. Failed requests never count as correct absent-answer abstention. Keyword baseline, lexical preselection and full reference-span visibility are recorded separately per case.

Generation time seconds: `{"metadata": {"n": 4, "min": 68.521896, "median": 110.741656, "max": 147.777007}, "search": {"n": 5, "min": 103.49175412800105, "median": 152.14047516000574, "max": 217.94348991099105}, "packet_overview": {"n": 10, "min": 16.30439201799163, "median": 46.9568685954946, "max": 151.42675463599153}}`. Completion tokens: `{"n": 20, "min": 13, "median": 28.5, "max": 336}`. Input size, token usage, prompt/configuration hashes, timing and valid answers are in the paired JSON. First two metadata envelopes were not captured; their validated artifacts/configuration remain available.

Persisted processing wall time (including failure handling, distinct from successful-response latency): `{"n": 19, "min": 18.896173, "median": 114.035488, "max": 302.800336}`. Null failed-task generation latencies remain null; read-only task timestamps are labelled separately.

## Resources and limitations

Extraction states across bounded receipts: `{"waiting_model": 310, "needs_ocr": 1}`. The image-only benchmark should remain needs_ocr. Extracted text is not pixel interpretation.

Resource observations: `[{"Name": "comfort-ecosystem-worker-run-6e26b5554bb8", "CPUPerc": "0.35%", "MemUsage": "133.4MiB / 1GiB", "PIDs": "2"}, {"Name": "health-continuity-inference-1", "CPUPerc": "638.45%", "MemUsage": "7.791GiB / 8GiB", "PIDs": "20"}]`. point samples during shared CPU inference, not peaks or throughput; no isolated cold start. Resource figures are point samples and cannot establish capacity, peaks or causal latency differences.

The 50-patient stress mapping was prepared. Original functional requests repeatedly reached the timeout; bounded CPU follow-ups now complete, but full functional quality/capacity stability has not been established, so stress remains unexecuted. Synthetic notes include encoding artifacts and repeated representations. P10 metadata defaults are conservative fixture review values, not a comprehensive annotated metadata gold standard. This small evaluation is not representative of all clinical language, dialects or conditions.

## Evidence-based engineering priorities

1. Apertus/output handling: review failed/incomplete attempts metadata-P15-X-008, q01, o01, q08, co01. Preserve their responses/configuration; do not hide failed runs in accuracy denominators.
   Observed failures include a December month invented from a year-only 2025 document date, and a blocked overview candidate describing a document date as a patient-confirmed visit date. The overview also used escaped text that failed quotation validation. Preserve date roles and exact source quotes before presenting these outputs. These are deterministic source comparisons, not completed human or clinical judgments. Raw field matches and usable-output accuracy are reported separately.
2. Retrieval architecture: preselection omitted expected documents in (none recorded). Full reference spans were absent from supplied context in cpu-q08, cpu2-q08, cpu3-co01. Address source ranking and passage selection separately from generation.
3. Clinical information handling: inspect phrase-screen concerns in cpu-o01, cpu-co01, cpu2-o01, cpu2-co01, cpu3-co01. Screens are not entailment judgments. Complete independent statement-level human review before asserting factual-preservation or unsupported-claim rates.
   Passage-boundary warnings: cpu3-o02. In cpu3-o02 a selected quote ended 'current strength is', before the next source line 'unconfirmed'. Exact quotation alone does not preserve the whole qualification. Preserve contiguous wrapped statements and evaluate omissions before using an excerpt draft as a clinical handoff. The boundary heuristic is a screening aid, not human review.
4. Backend integration/authorization: retain explicit permissions and negative tests. Fixture execution exposed receipt-write concurrency and Keycloak loopback protocol behavior; operation locking and exact-subject provisioning now cover these. Supported guardian/caregiver labels remain distinct from an unimplemented trusted acting context.
5. Frontend/accessibility and missing capabilities: there is no new browser usability evidence in this protocol run. The audit found no voice operation, trusted delegation, professional verification, journal service or OCR. Develop and test these as explicit product capabilities; do not represent the authored scenarios as existing features.
6. Resource utilization: collect isolated warmed and cold runs at multiple controlled input sizes before choosing hardware or making throughput claims. Current inference shares the development machine.

## Scope of conclusions

Human semantic review: 0 summary cases assessed; 1 review responses were inconclusive. Remaining cases stay unreviewed, and an unable-to-assess response is not a correctness label. Actual usability testing and clinician validation were not performed. The worksheet is private and preserves annotations. These are measured software/model-development results using synthetic information, not evidence of clinically validated outcomes or production readiness.
