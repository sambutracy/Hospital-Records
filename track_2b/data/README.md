# Authored synthetic evaluation data

The current suite is `comfort-evaluation-v2.json`; `comfort-evaluation-v1.json` is retained as the original frozen version. Each contains 30 authored short text sources, 20 queries and 10 overview cases. They are fictional engineering fixtures rather than actual PDFs, patient uploads or clinician-reviewed reference data. Every source has its own provenance and CDLA-Permissive-2.0 label. There are no human subjects or consent-bearing records.

Version 2's annotation corrections are stated in `changes_from_v1`. Do not silently modify a version after measuring it. The harness records exact fixture/harness/prompt/context hashes and case/response counts. See [evaluation contract](../src/intelligence/EVALUATION.md), [data license](../src/intelligence/DATA_LICENSE.txt) and `make evaluate` / `make evaluate-live` from the repository root.

Runtime model responses remain ignored until reviewed for synthetic-only content and absence of credentials. These fixtures do not establish clinical safety, real-world accuracy, professional verification or complete-history absence. Dataset publication on Hugging Face is optional and has not been performed. The whole directory remains below 100 MB.
