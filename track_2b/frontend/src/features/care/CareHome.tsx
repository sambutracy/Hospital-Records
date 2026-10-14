import { Link } from "react-router-dom";
import { HeartPulse, Stethoscope, Files } from "lucide-react";
import { PageHeader, Notice } from "../../design-system/primitives";
import CareNavigation from "./CareNavigation";
export default function CareHome() {
  return (
    <>
      <PageHeader
        eyebrow="MY CARE"
        title="Keep the people and pieces together."
      >
        A place for what you are investigating, who has helped, and what you
        want to bring to your next visit.
      </PageHeader>
      <CareNavigation />
      <div className="record-grid">
        <article className="record-card">
          <HeartPulse aria-hidden="true" />
          <h2>Health concerns</h2>
          <p>
            Describe an issue in your own words, even when there is no confirmed
            diagnosis.
          </p>
          <Link to="concerns">Organize health concerns</Link>
        </article>
        <article className="record-card">
          <Stethoscope aria-hidden="true" />
          <h2>Care Team</h2>
          <p>
            Remember current and historical doctors and connect them with the
            concerns they helped with.
          </p>
          <Link to="team">See your Care Team</Link>
        </article>
        <article className="record-card">
          <Files aria-hidden="true" />
          <h2>Prepare for a visit</h2>
          <p>
            Bring a private selection of original records together for a
            consultation.
          </p>
          <Link to="visits">Open visit selections</Link>
        </article>
      </div>
      <div className="form-section">
        <Notice>
          Adding someone to your Care Team grants no record access. Sharing
          always needs a separate, explicit permission.
        </Notice>
      </div>
    </>
  );
}
