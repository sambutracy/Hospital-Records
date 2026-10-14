# Private patient profile and Care circle

The patient profile stores full/preferred name, contact email/phone/address, optional gender, ID type/number/issuer and self-reported blood group. Date of birth uses the existing patient Person's partial-date components; unknown month/day remain null. The patient workspace and OAuth identity remain bound to their original person/account. Contact email, personal ID and edited names are never used to merge accounts, verify civil identity, alter the sign-in provider or broaden authority. The personal workspace greeting may use the saved preferred/full name; recipient account checks continue to show the authenticated account's name.

The **Care circle** holds relatives, next of kin, emergency contacts, caregivers, guardian contacts, clinicians or other trusted contacts. An entry may have only contact details, or an explicitly selected active Comfort account. Neither email/name matching nor automatic account creation occurs. A saved relationship is a description, not guardian verification, caregiver delegation or a patient-data grant. Phone/email contacts cannot receive electronic record access until linked to an existing authenticated account ID.

The workspace's sharing form can select a linked, active Care circle account, then resolves its real account name and requires the existing exact-scope approval. Sharing/contribution still use their own purpose, recipient, expiry, capabilities and revocation; profiles, blood group, personal IDs, contacts and medication notes are not included automatically. Archiving/editing/unlinking a contact does not change earlier grants: their recipient IDs and scopes stay fixed. Remove/revoke access explicitly in **Connect your care**.

## API and authorization

All routes are under `/api/workspaces/{workspace}/`:

- `profile/`: GET private values/revision or POST `{values, expected_revision}`. Initial unsaved revision is zero. All fields are explicit; clearing an ID requires `identifier_type=none` and empty number/issuer. Unknown birth date has null components. Values include full_name, preferred_name, email, phone, address, gender, identifier_type, identifier_number, identifier_issuer, blood_group, birth_date.
- `care-circle/`: GET active contacts (or `?include_archived=1`) or POST `{values, expected_revision:0}`. Values include full_name, relationship, email, phone, notes, is_next_of_kin, is_emergency_contact and recipient_id (UUID or null).
- `care-circle/{contact}/`: POST a complete replacement of those values with the current expected_revision.
- `care-circle/{contact}/status/`: POST `{status:active|archived, expected_revision}`. Archive is reversible; it does not delete history or revoke an independent grant.
- `care-circle/resolve/`: POST `{recipient_id}` for exact active account lookup.
- `care-circle/choices/`: minimal active linked choices for the sharing picker; no phone, email or contact notes in that response.

Each route rechecks the patient's live **manage_profile** self capability, account/person/patient/workspace state, membership, expiry and revocation. Unrelated accounts and recipients of medical-record read grants receive no profile/contact access. Mutations require CSRF. A workspace lock and revision check prevent stale edits. Active linked contacts are unique per workspace/account; a contact list allows up to 100 active entries. The combined active/archived list is bounded to 200 rows.

PostgreSQL guards keep workspace/id/creation bindings fixed, enforce editor/subject matching and consecutive revisions, protect enum/date shapes, and deny deletion through the runtime role. Profile/contact edits retain current values and actor/time/revision audit, not a full historical copy of every field. Audit records contain no ID, blood group, address, phone, contact email or medication content. Responses are private/no-store; the ID is masked in the editor by default. Runtime data resides in private local database volumes and is excluded from source control. Storage encryption/production retention, identity/guardian verification and external contact messaging are not claimed by this prototype.

These fields are outside the Apertus source-selection path; saving them does not submit them to inference. The application makes no clinical claim from the patient's reported blood group.
