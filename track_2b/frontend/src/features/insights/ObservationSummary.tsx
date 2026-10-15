import { useState } from "react";
import { Button, Notice } from "../../design-system/primitives";
import type { Observations } from "./contracts";

export default function ObservationSummary({ data }: { data: Observations }) {
  const [page, setPage] = useState(0);
  const recorded = data.bins.filter((row) => row.observations > 0);
  const maximum = Math.max(1, ...recorded.map((row) => row.observations));
  const slice = data.bins.slice(page * 14, page * 14 + 14);
  return (
    <section
      className="panel insights-summary"
      aria-labelledby="observations-heading"
    >
      <p className="eyebrow">Your recorded experience</p>
      <h2 id="observations-heading">Symptom observations</h2>
      <p>
        From {data.from} to {data.to}. Counts use exact local dates and active
        symptom entries in Journal.
      </p>
      <dl className="insights-stats">
        <div>
          <dt>Observations recorded</dt>
          <dd>{data.exact_dated_observations}</dd>
        </div>
        <div>
          <dt>Days with observations</dt>
          <dd>
            {data.days_with_observations} <span>of {data.days_in_range}</span>
          </dd>
        </div>
        <div>
          <dt>Days without entries</dt>
          <dd>
            {data.days_without_entries} <span>· how you felt is unknown</span>
          </dd>
        </div>
      </dl>
      {data.chart_ready ? (
        <figure className="insights-chart">
          <figcaption>Recorded observations by date</figcaption>
          <p>
            Dates with entries only; unrecorded dates are omitted. Bar height
            counts entries, not severity.
          </p>
          <div className="insights-bars" aria-hidden="true">
            {recorded.map((row) => (
              <div className="insights-bar-column" key={row.date}>
                <strong>{row.observations}</strong>
                <div className="insights-bar-track">
                  <span
                    style={{ height: `${(row.observations / maximum) * 100}%` }}
                  />
                </div>
                <span>{row.date.slice(5)}</span>
              </div>
            ))}
          </div>
          <p>
            The same numbers and any reported scores are available in the table
            below.
          </p>
        </figure>
      ) : (
        <Notice>
          There are not yet observations on three different dates in this range.
          Your entries remain available below; there is no trend to infer.
        </Notice>
      )}
      <p>
        {data.partial_date_observations_excluded} partially dated observations
        overlap this range and are excluded from daily counts.{" "}
        {data.undated_observations_excluded} undated observations cannot be
        assigned to this range.
      </p>
      <p>
        {data.unscored_observations} observations have no severity score.
        Different entries may describe different symptoms; their scores are not
        averaged.
      </p>
      <details className="insights-data">
        <summary>View observation data, including unrecorded days</summary>
        <div className="insights-table-wrap">
          <table>
            <caption>
              Patient-reported symptom entries · daily counts and reported
              severity
            </caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Entries recorded</th>
                <th scope="col">Entries with a score</th>
                <th scope="col">Reported severity (0–10)</th>
              </tr>
            </thead>
            <tbody>
              {slice.map((row) => (
                <tr key={row.date}>
                  <th scope="row">{row.date}</th>
                  <td>{row.observations || "No entries recorded"}</td>
                  <td>{row.scored_observations}</td>
                  <td>
                    {row.severity_min === null
                      ? "Not recorded"
                      : row.severity_min === row.severity_max
                        ? row.severity_min
                        : `${row.severity_min}–${row.severity_max}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <nav className="actions" aria-label="Observation data pages">
          <Button
            variant="quiet"
            isDisabled={page === 0}
            onPress={() => setPage(page - 1)}
          >
            Earlier data
          </Button>
          <span>
            Days {page * 14 + 1}–{Math.min((page + 1) * 14, data.bins.length)}{" "}
            of {data.bins.length}
          </span>
          <Button
            variant="quiet"
            isDisabled={(page + 1) * 14 >= data.bins.length}
            onPress={() => setPage(page + 1)}
          >
            Later data
          </Button>
        </nav>
      </details>
      <p className="care-access">
        These are counts of what was recorded, not unique symptom episodes.
        Blank days do not mean symptom-free days. This view does not infer a
        diagnosis, a cause or medication adherence.
      </p>
    </section>
  );
}
