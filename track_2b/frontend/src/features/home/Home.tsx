import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  ChartNoAxesCombined,
  FilePlus2,
  HeartHandshake,
} from "lucide-react";
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
      />
      <section className="home-intro" aria-labelledby="home-intro-title">
        <div>
          <p className="eyebrow">Your personal health workspace</p>
          <h2 id="home-intro-title">Bring your health story with you.</h2>
          <p>
            Keep your records and observations together, ready for your next
            visit.
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
      </section>
      <nav className="home-next-steps" aria-label="What you can do next">
        <Link to="../journal">
          <BookOpen size={21} aria-hidden="true" />
          <span>
            <strong>Write a Journal note</strong>
            <small>Capture how you feel, in your own words.</small>
          </span>
          <ArrowRight size={18} aria-hidden="true" />
        </Link>
        <Link to="../insights">
          <ChartNoAxesCombined size={21} aria-hidden="true" />
          <span>
            <strong>Explore your health history</strong>
            <small>Follow your records and observations over time.</small>
          </span>
          <ArrowRight size={18} aria-hidden="true" />
        </Link>
        <Link to="../care/visits">
          <HeartHandshake size={21} aria-hidden="true" />
          <span>
            <strong>Prepare for a visit</strong>
            <small>Bring the information that matters to you.</small>
          </span>
          <ArrowRight size={18} aria-hidden="true" />
        </Link>
      </nav>
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
        <section className="panel home-empty-records">
          <h3>Ready when you are</h3>
          <p>
            Your first record can be a report, prescription or medical image.
          </p>
        </section>
      )}
      <p className="home-privacy-note">
        Your saved records stay private until you choose to share them.
      </p>
    </>
  );
}
