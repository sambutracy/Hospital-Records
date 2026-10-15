# Comfort synthetic ecosystem v1

Purpose: exercise continuity of patient-owned records, provenance, independent
permissions and bounded Apertus behavior. These are synthetic development
fixtures, not a clinical benchmark, patient registry or diagnostic dataset.

## Sources and selection

| Source | Pinned revision | Declared source license | Selection and changes |
|---|---|---|---|
| [NHS England synthetic clinical notes](https://huggingface.co/datasets/NHSEDataScience/synthetic_clinical_notes/tree/368a5bd2a55090a0bae3436f2823d606c5077158) | `368a5bd2a55090a0bae3436f2823d606c5077158` | MIT | Silver patient/admission/note CSVs; coherent original patient joins; exact duplicate patient rows deduplicated; five documented mojibake replacements; deterministic PDF wrappers with original text and provenance. |
| [Miłosz Orzeł / morzel.net synthetic medical document benchmark](https://huggingface.co/datasets/morzel85/synthetic-medical-document-recognition-benchmark/tree/906494ea091a54b81e6254f457fbffd219f2a8ef) | `906494ea091a54b81e6254f457fbffd219f2a8ef` | CC BY 4.0 | Eight original Adam Hirthe PDFs; unchanged bytes, including an image-only scanned representation. A matching Synthea-based FHIR bundle is reference-only. Variants are not independent encounters. |
| Comfort-authored extensions | Versioned repository source and manifest | CDLA-Permissive-2.0 | Clearly fictional routine, reproductive, conflicting/uncertain and administrative examples, plus auxiliary workflow documents. No clinical verification is asserted. |

Upstream NHS provenance credits William Poulett, Alice Waterhouse, Ben Wallace,
Scarlett Kynoch, Amaia Imaz Blanco, Michael Spence and Jonathan Pearson;
[associated paper](https://arxiv.org/abs/2606.26879). NHS notes are fully synthetic
and the silver subset is not individually clinician-checked. Its 69 patient CSV
rows represent 50 unique patients: 19 exact duplicate rows are removed only after
full-row equality checks. All 69 admissions and 1,602 unique notes were inspected
for identity joins. Conflicting duplicate IDs fail validation.

NHS copyright: **Copyright (c) 2026 Crown Copyright NHS England.** Its MIT
permission notice is reproduced in `LICENSE_NHS_MIT.txt`, obtained from the
[upstream license](https://github.com/nhsengland/synthetic_clinical_notes/blob/main/LICENSE).
The dataset card declares MIT; that declaration and the separate code-license
notice are recorded distinctly in the license receipt.

Benchmark attribution: **Miłosz Orzeł (morzel85), morzel.net, synthetic medical
document recognition benchmark**, based on Synthea-generated records.
[License: Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
Original selected PDFs are unchanged; Comfort adds external fixture mappings,
checksums and evaluation annotations. No endorsement is implied.

Authored fixture material is offered under
[CDLA-Permissive-2.0](https://cdla.dev/permissive-2-0/). Upstream documents retain
their own licenses. This mixed-provenance collection is **not** represented as
entirely relicensed under CDLA. Apache-2.0 repository code and Liberation font
licensing are separate from dataset licensing. The font's full notice is stored
next to the embedded TTF in `src/ecosystem/assets/`.

## Coherence, privacy and reproducibility

`population.json` maps every document to one source patient and every fictional
account to a separate fixture identifier. Source patient reuse across workspaces
is rejected. Original patient identifiers stay in provenance; clinical facts are
never grafted from another source patient. Authored extensions are labelled per
instance and do not claim to have come from an upstream admission.

The functional cohort has 15 patients, 10 additional actors and 308 initial
documents. Smoke selects three patients/three actors/23 documents. Stress
contains 50 planned patients and is separately gated. P13's 100 records comprise
90 actual source notes and ten authored administrative follow-ups. P14 has zero
initial documents, then one onboarding auxiliary. All actors also receive their
own canonical patient workspace; there are 25 accounts in the functional setup.

No real patient data is introduced, and no real identity/consent documents are
collected. Plausible names, identifiers and contact information in the upstream
fixtures are synthetic. Credentials, raw files and per-user detailed results
remain ignored locally; public manifests expose synthetic fixture provenance.
The child scenario uses a canonical fictional self account solely to test
installed APIs; real guardian-mediated onboarding and capacity/authority
verification remain unsupported. This does not establish a usable child-care
consent journey.

Reported caregiver/guardian/nurse/practitioner labels never establish trusted
identity or delegated authority. Menstrual and reproductive examples stay private
in their normal owner workspaces unless the owner explicitly selects a version
for a separate grant.

`sources.lock.json` pins every downloaded file's revision, path, size, checksum
and license. `text.lock.json` pins logical UTF-8 reference text. Preparation checks
PDF page, text and upload-size limits; an image-only PDF should become
`needs_ocr`, not invented text. The original benchmark FHIR is never presented as
an imported native clinical resource. Public data stays below the track's 100 MB
limit; generated and downloaded artifacts stay in ignored runtime storage.

## Annotation quality and limitations

The separate evaluation defines expected facts before model runs. Exact source
quotes and physical PDF page locations are verified mechanically. Literal-term
labels are limited retrieval references, not clinician-reviewed relevance labels.
NHS encoding repair is explicit and bounded; remaining source artifacts are not
silently corrected. Historical dates, unknown dates, conflicting information and
prescriptions versus reported use remain distinct.

Model schema and verbatim-quote validity, phrase screens, human semantic review,
clinical validation and usability are different evidence categories. The latter
three cannot be inferred from successful APIs or readable generated prose.
OCR, trusted delegation, verified professional roles, journal event services and
voice operation are unsupported in this assignment; scenario planning does not
pretend those features exist.
