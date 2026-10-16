import type { VisitBriefResult } from "../../services/api/contracts";

const sectionOrder = [
  "purpose",
  "medications",
  "history",
  "symptoms",
  "findings",
  "followup",
  "function",
  "coordination",
  "preferences",
  "basics",
];

function provenanceLabel(value: string) {
  const labels: Record<string, string> = {
    document_sourced: "Recorded in document",
    patient_reported: "Patient reported",
  };
  return labels[value] ?? value;
}

export default function VisitBrief({ result }: { result: VisitBriefResult }) {
  const coverage = result.coverage_summary;
  const sections = result.sections
    .filter((section) => section.items.length > 0)
    .sort((left, right) => {
      const position = (id: string) => {
        const index = sectionOrder.indexOf(id);
        return index === -1 ? sectionOrder.length : index;
      };
      return position(left.id) - position(right.id);
    });
  return (
    <section className="visit-brief" aria-label="Apertus visit brief">
      {result.abstained && (
        <p role="status">
          Apertus did not select supported source evidence. Your own visit notes
          remain below.
        </p>
      )}
      {result.packet_purpose && (
        <p className="visit-brief-purpose">
          <strong>Visit:</strong> {result.packet_purpose}
        </p>
      )}
      <p className="visit-brief-meta">
        {coverage.represented_documents} of {coverage.selected_documents}{" "}
        selected records represented
        {result.patient_context ? " · includes chosen private context" : ""}.
      </p>
      {result.critical_gaps.length > 0 && (
        <aside className="visit-brief-gaps" aria-label="Things to confirm">
          <h4>Things to confirm</h4>
          <ul>
            {result.critical_gaps.map((gap) => (
              <li key={gap.id}>{gap.text}</li>
            ))}
          </ul>
        </aside>
      )}
      {sections.map((section) => (
        <section className="visit-brief-section" key={section.id}>
          <h4>{section.title}</h4>
          <ul className="visit-brief-items">
            {section.items.map((item, index) => (
              <li key={index}>
                <p className="visit-brief-statement">{item.text}</p>
                {item.caution && (
                  <p className="visit-brief-caution">{item.caution}</p>
                )}
                <ul className="visit-brief-attribution" aria-label="Sources">
                  {item.citations
                    .filter(
                      (citation, index, citations) =>
                        citations.findIndex(
                          (other) =>
                            other.label === citation.label &&
                            other.date_label === citation.date_label &&
                            other.download_url === citation.download_url &&
                            other.href === citation.href,
                        ) === index,
                    )
                    .map((citation, sourceIndex) => (
                      <li key={sourceIndex}>
                        {citation.download_url || citation.href ? (
                          <a href={citation.download_url ?? citation.href}>
                            {citation.label}
                          </a>
                        ) : (
                          <span>{citation.label}</span>
                        )}
                        {citation.date_label && ` · ${citation.date_label}`}
                        {citation.provenance &&
                          ` · ${provenanceLabel(citation.provenance)}`}
                      </li>
                    ))}
                </ul>
                {item.citations.length > 0 && (
                  <details className="visit-brief-evidence">
                    <summary>Supporting excerpts</summary>
                    {item.citations.map((citation, sourceIndex) => (
                      <blockquote className="quote" key={sourceIndex}>
                        <p>{citation.quote}</p>
                        <cite>{citation.label}</cite>
                      </blockquote>
                    ))}
                  </details>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
      <details className="visit-brief-scope">
        <summary>Sources and limits</summary>
        <p>
          Drafted{" "}
          <time dateTime={result.generated_at}>
            {new Date(result.generated_at).toLocaleString()}
          </time>
          . Review the source dates and confirm what still applies.
        </p>
        {result.patient_context && (
          <p>
            Your chosen profile, medicines, Journal or care details remain
            private. They have not been added to shared records.
          </p>
        )}
        <dl className="visit-brief-coverage">
          <div>
            <dt>Private context items</dt>
            <dd>{coverage.context_items}</dd>
          </div>
          <div>
            <dt>Records with shortened text</dt>
            <dd>{coverage.truncated_documents}</dd>
          </div>
          <div>
            <dt>Passages omitted</dt>
            <dd>{coverage.omitted_passages ?? 0}</dd>
          </div>
          <div>
            <dt>Repeated passages combined</dt>
            <dd>{coverage.duplicate_passages_merged}</dd>
          </div>
        </dl>
        {result.limitations.length > 0 && (
          <ul>
            {result.limitations.map((limitation, index) => (
              <li key={index}>{limitation}</li>
            ))}
          </ul>
        )}
      </details>
    </section>
  );
}
