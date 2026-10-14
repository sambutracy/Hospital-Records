import type { ActingContext, RecordDetail } from "../services/api/contracts";
export const workspaceId = "11111111-1111-4111-8111-111111111111";
export const recordId = "22222222-2222-4222-8222-222222222222";
export const versionId = "33333333-3333-4333-8333-333333333333";
export const context: ActingContext = {
  id: workspaceId,
  workspace_id: workspaceId,
  kind: "patient",
  label: "My health",
  patient_display_name: "Fictional patient",
  capacity: "Self",
  capabilities: [
    "read_workspace_records",
    "upload_source",
    "review_metadata",
    "prepare_packet",
  ],
};
export const record: RecordDetail = {
  id: recordId,
  current_version: {
    id: versionId,
    record_id: recordId,
    version_number: 1,
    original_filename: "fictional-lab.pdf",
    media_type: "application/pdf",
    byte_size: 1200,
    sha256: "a".repeat(64),
    uploaded_at: "2026-10-14T09:00:00Z",
    content_kind: "document",
    supersedes_id: null,
    download_url: `/api/workspaces/${workspaceId}/versions/${versionId}/original/`,
    image_details_url: null,
  },
  metadata: {
    revision: 0,
    values: { document_type: null, document_date: null, facility_name: null },
    facility_maps_url: null,
    verification: "patient-confirmed, not clinician-verified",
  },
  jobs: [],
  versions: [],
  proposals: [],
  metadata_history: [],
};
