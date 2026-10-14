import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, FilePlus2, HeartHandshake } from "lucide-react";
import { usePatient } from "../../services/auth/session";
import { post } from "../../services/api/client";
import { recordsSchema } from "../../services/api/contracts";
import { Loading, Notice, PageHeader } from "../../design-system/primitives";
import { RecordCard } from "../records/RecordCard";
export default function Home() {
  const patient = usePatient();
  const query = useQuery({
    queryKey: ["home-records", patient.id],
    queryFn: ({ signal }) =>
      post(
        `/api/workspaces/${patient.id}/records/search/`,
        recordsSchema,
        { q: "" },
        signal,
      ),
  });
  return (
    <>
      <PageHeader
        eyebrow="MY HEALTH"
        title={`Hello, ${patient.patient_display_name}.`}
      >
        Your history, kept together. Start with what you need today.
      </PageHeader>
      <div className="home-intro">
        <div>
          <p className="eyebrow">A calmer next visit</p>
          <h2>Bring your health story with you.</h2>
          <p>
            Save your originals, review their details and choose the information
            that matters for a visit.
          </p>
          <Link className="button button--primary" to="../records">
            <FilePlus2 size={18} aria-hidden="true" />
            Add a record
          </Link>
        </div>
        <div className="intro-illustration" aria-hidden="true">
          <div className="illustration-sheet">
            <span />
            <span />
            <span />
            <HeartHandshake size={55} />
          </div>
        </div>
      </div>
      <div className="section-heading">
        <h2>Recent records</h2>
        <Link to="../records">
          See records <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </div>
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <Notice tone="error">{query.error.message}</Notice>
      ) : query.data.records.length ? (
        <div className="record-grid">
          {query.data.records.slice(0, 3).map((record) => (
            <RecordCard key={record.id} record={record} />
          ))}
        </div>
      ) : (
        <section className="panel">
          <h3>Ready when you are</h3>
          <p>
            You have no saved records yet. Add a report, prescription, image
            export or DICOM original.
          </p>
        </section>
      )}
      <section className="quiet-section">
        <h2>You stay in control</h2>
        <p>
          Saving a record does not share it. Reviewing document details does not
          make them clinically verified.
        </p>
        <Link to="../care">
          Prepare for a visit <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </section>
    </>
  );
}
