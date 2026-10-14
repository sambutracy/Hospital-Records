# Information status and care chronology contract

Comfort stores records and patient-reported information. The following distinctions are part of the installed application, not clinical verification claims.

| Information | Source / authority | Meaning |
| --- | --- | --- |
| Original document version | Immutable uploaded bytes and checksum | Evidence of what was uploaded; not proof of authenticity or clinical accuracy |
| Extracted PDF text / DICOM headers | Exact version and page or tag | Source-derived text/technical fields; no diagnostic pixel interpretation |
| Apertus metadata / overview | Versioned generation and source quotations | Unverified suggestion/draft; never overwrites confirmed details |
| Confirmed document metadata | Explicit patient review with revision/history | Patient-confirmed organization; not a clinician-verified diagnosis |
| Medication entry | Patient author; optional prescription version | Prescribed, reportedly taken, not taken or unknown remain separate states |
| Personal profile / blood group | Patient-reported, private | Not clinically verified; not automatically included in packets or inference |
| Accepted submitted note | Original submitter preserved; patient acceptance | Acceptance adds the original to the record collection; does not verify the submitter's professional status |
| Care circle relationship | Patient-authored contact label | Guardian/next of kin/caregiver label grants no access or legal authority |

Document dates, patient-entered visit dates, source specimen dates and upload times are different concepts. Document ordering uses only confirmed document-date components, with unknown components preserved. Medication visit dates preserve their independent partial/unknown precision. Named episodes group explicitly selected versions; they do not establish that all sources came from one encounter or cause one another. No full clinical event timeline is claimed.

AI search uses lexical ranking over all authorized current-version filenames, confirmed type/facility and extracted text, followed by a maximum of 30 source contexts for Apertus. It uses PostgreSQL's simple multilingual token configuration, not embeddings or a persisted full-text index. The result exposes total/included records and truncation. It cannot establish that an illness, medication or encounter is absent from the patient's whole history. Keyword search also reads extracted report text.

The model's quotation validator checks source ownership, exact version and verbatim quotation. A valid quotation does not establish that generated prose is entailed by it. Patients must inspect overview drafts; the evaluation explicitly screens this distinction. No conditions, allergy lists, normalized lab observations, dose calculations or medication reconciliation are silently inferred into patient-owned structured records.

Future clinical extraction needs independently labelled source, assertion certainty (including negated/suspected), temporal precision and verification status, plus explicit human review before promotion to a new clinical assertion. Prescription mentions must not default to current use; an absent allergy must not default to no known allergies. Such extraction and FHIR/IPS import/export are **not implemented**. The existing record/provenance model is retained rather than claiming a standards-compliant patient summary from a document list.
