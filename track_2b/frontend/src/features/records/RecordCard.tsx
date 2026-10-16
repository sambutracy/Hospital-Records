import { Link } from "react-router-dom";
import { FileText, CheckCircle2, Clock3 } from "lucide-react";
import type { PartialDate, RecordItem } from "../../services/api/contracts";
export const types = {
  lab_report: "Lab report",
  referral: "Referral",
  consultation_note: "Consultation note",
  prescription: "Prescription",
  discharge_summary: "Discharge summary",
  imaging_report: "Imaging report",
  medical_image: "Medical image",
  other: "Other record",
};
export const typeLabel = (type: string | null) =>
  type
    ? (types[type as keyof typeof types] ?? "Other record")
    : "Type not reviewed";
export function partialDate(value: PartialDate | null): string {
  if (!value) return "Date not reviewed";
  if (value.precision === "unknown") return "Date unknown";
  if (value.precision === "year") return String(value.year);
  const month = new Intl.DateTimeFormat("en", {
    month: "long",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(2000, (value.month ?? 1) - 1, 1)));
  return value.precision === "month"
    ? `${month} ${value.year}`
    : `${value.day} ${month} ${value.year}`;
}
export const processingLabel = (state: string) =>
  ({
    queued: "Queued for reading",
    processing: "Reading document",
    waiting_model: "Waiting for AI access",
    needs_ocr: "Original saved · text reading unavailable",
    failed: "Original saved · reading could not finish",
    review_ready: "AI suggestions ready for review",
    manual_review: "Original saved · manual review needed",
  })[state] ?? "Original saved";
export function RecordCard({
  record,
  selected,
  onSelect,
  selectionDisabled = false,
}: {
  record: RecordItem;
  selected?: boolean;
  onSelect?: (checked: boolean) => void;
  selectionDisabled?: boolean;
}) {
  const reviewed = record.metadata.revision > 0;
  const values = record.metadata.values;
  const title =
    reviewed && values.document_type
      ? typeLabel(values.document_type)
      : "Health record";
  const filename = record.current_version.original_filename;
  return (
    <article className="record-card">
      <div className="record-card-top">
        <div className="record-card-icon">
          <FileText size={22} aria-hidden="true" />
        </div>
        <span className="badge">
          {reviewed ? (
            <>
              <CheckCircle2 size={14} aria-hidden="true" />
              Details reviewed
            </>
          ) : (
            <>
              <Clock3 size={14} aria-hidden="true" />
              Needs review
            </>
          )}
        </span>
      </div>
      <h3 className="record-card-title">
        <Link
          to={`../records/${record.id}`}
          aria-label={`${title} · ${filename}`}
        >
          {title}
        </Link>
      </h3>
      <p className="record-card-date">
        {partialDate(reviewed ? values.document_date : null)}
      </p>
      <p className="record-card-facility">
        {(reviewed ? values.facility_name : null) ??
          "Issuing facility not recorded"}
      </p>
      <p className="record-card-filename" title={filename}>
        {filename}
      </p>
      <p className="record-card-status">
        {processingLabel(record.jobs[0]?.state ?? "")}
      </p>
      {onSelect && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={selected}
            disabled={selectionDisabled}
            onChange={(event) => onSelect(event.target.checked)}
          />
          Select for a visit
        </label>
      )}
    </article>
  );
}
