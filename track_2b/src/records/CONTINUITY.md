# Selected records and the return note

Comfort supports an authenticated recipient opening an explicitly approved packet, and independently submitting an original note into a named patient-created episode. An invited account is not a verified professional identity. Account names and account IDs are never proof of clinical credentials. Every signed-in account can maintain its own patient workspace and separately act as an invited recipient for somebody else; this does not create membership in that patient's workspace.

## Patient flow

1. Upload/review originals and create a private packet containing the exact source versions to share. Create an episode when a return note is expected; optionally link selected originals to it. Episodes are organizational groupings, not inferred diagnoses, appointments or referrals.
2. Ask the recipient for their Comfort account ID, available on **Received access**. Resolve that exact ID to check the account name; no searchable patient/provider directory is exposed. Verify the person through a trusted channel yourself.
3. Approve **Read an approved packet**, specifying purpose and expiry (one minute to seven days). The immutable packet revision fixes the originals and the patient-confirmed metadata assertions visible to the recipient. New versions, unrelated records, source proposals and AI drafts are excluded.
4. Separately approve **Submit a note to an episode** if required. This creates an independent provider contribution authority with its own purpose, expiry and revocation. It grants no history reads. Revoking one permission leaves the other unchanged.
5. Review an incoming original, then accept or reject it. Acceptance preserves the original bytes/checksum and submitting account attribution, creates a new source record in the episode and queues patient-authorized processing. It does not overwrite earlier records or mark the contents clinically verified. Each decision is final for that submission.

## Recipient flow

**Received access** lists only currently authorized invitations. The read view and every original download recheck the intended recipient, account/patient/authorizer status, authorizing self-membership and capability, time window and revocation. Access to the patient's ordinary workspace routes remains denied. The screen refreshes availability every 15 seconds; server checks apply on every new request. Revocation cannot recall downloaded or displayed copies, and an already authorized download can finish.

With separate contribution authority, upload one PDF/JPEG/PNG/Part 10 DICOM original up to 10 MB per request. The submitter receives only their receipt/status through the active invitation. Pending/rejected contributions are stored separately from accepted SourceRecords/SourceVersions, so ordinary retrieval, processing, packet creation and AI source selection cannot include them. Acceptance reuses the preserved private object and records the patient review decision. An already received submission remains reviewable after authority expiry/revocation. Duplicate accepted bytes require explicit rejection of the duplicate submission; they never overwrite an existing record.

## Contracts and database guards

Patient-scoped routes under `/api/workspaces/{workspace}/`:

- `episodes/`: GET list or POST `{title}`.
- `episodes/{episode}/sources/`: POST `{source_version_ids}` (one to 30); append exact-version links. A version can belong to multiple episodes.
- `recipients/resolve/`: POST `{recipient_id}`; exact active account lookup behind live patient authorization.
- `grants/`: GET list or POST `{kind, target_id, recipient_id, purpose, expires_in_minutes}`; `kind=read` targets an approved packet revision, `kind=contribute` targets an episode.
- `grants/{kind}/{grant}/revoke/`: POST `{}`; terminal revocation.
- `contributions/`: GET inbox; `contributions/{submission}/original/`: protected GET; `contributions/{submission}/review/`: POST `{decision: accept|reject}`.
- `records/?order=document_date&episode={episode}`: optional exact-current-version episode filter. Date order uses known year/month/day components, newest first, with unknown dates last. Partial dates retain their precision; this is a document-date view, not a precise care-event chronology.

Account/recipient routes under `/api/continuity/`:

- `account/`: own account name/ID; `received/`: currently usable invitations.
- `shares/{grant}/`: approved originals and metadata snapshot; `shares/{grant}/versions/{version}/original/`: exact selected original only.
- `contribution-authorities/{authority}/submit/`: multipart `{file, content_kind?}`; read-grant IDs are not accepted here.

All mutations require a live OIDC session and CSRF token. Patient actions use separate installed self capabilities (`manage_episode_links`, `create_share`, `revoke_share`, `review_contribution`, `authorize_provider_contribution`). No generic role flag enables them. Authorizer and workspace locks serialize grant use against patient mutations, and row locks serialize contribution review. Denied continuity requests are audited outside rolled-back service transactions; content, passwords and tokens are not copied into audit entries.

PostgreSQL migrations enforce same-workspace foreign keys, fixed recipient/authorizer/scope/purpose/expiry/provenance bindings, append-only episode links, approved immutable packet references, intended submission actor, pending-to-terminal patient-only decisions and exact original provenance on acceptance. Runtime role cannot delete these histories or update episode/source links. Application authorization still supplies current capability checks; these guards are not row-level security or a substitute for those checks.

## Limits

This release uses explicit patient approval recorded directly in each independent grant and the append-only audit trail. It has no generalized consent-policy engine or bulk withdrawal control. Guardians, caregiver delegation, visit assistants, professional verification, organization-wide access, appointment/referral lifecycles, episode editing/unlinking, OCR, diagnostic image interpretation and voice controls are not delivered by this slice. Accessibility and assisted-operation requirements remain in the private frontend plan; labelled controls/status messages and browser confirmation dialogs are not evidence of complete accessibility validation. Portable inference, frozen quality evaluation and clean-checkout submission reproduction remain separate work.
