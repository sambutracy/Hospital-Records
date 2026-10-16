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
      <p className="eyebrow">Journal overview</p>
      <h2 id="observations-heading">Symptom observations</h2>
      <p>
        Journal · {data.from} to {data.to} · by reported date.
      </p>
      <dl className="insights-stats">
        <div>
          <dt>Entries</dt>
          <dd>{data.exact_dated_observations}</dd>
        </div>
        <div>
          <dt>Days with entries</dt>
          <dd>
            {data.days_with_observations} <span>of {data.days_in_range}</span>
          </dd>
        </div>
        <div>
          <dt>Days without entries</dt>
          <dd>
            {data.days_without_entries}
          </dd>
        </div>
      </dl>
      {data.chart_ready ? (
        <figure className="insights-chart">
          <figcaption>Entries by day</figcaption>
          <p>Bar height counts entries, not severity.</p>
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
        </figure>
      ) : (
        <Notice>
          Fewer than three dates have entries, so no trend is shown.
        </Notice>
      )}
      {(data.partial_date_observations_excluded > 0 || data.undated_observations_excluded > 0) && (
        <p>
          {data.partial_date_observations_excluded > 0 && `${data.partial_date_observations_excluded} partial-date ${data.partial_date_observations_excluded === 1 ? "entry overlaps" : "entries overlap"} this range; ${data.partial_date_observations_excluded === 1 ? "it is" : "they are"} excluded from daily counts.`}
          {data.partial_date_observations_excluded > 0 && data.undated_observations_excluded > 0 ? " " : ""}
          {data.undated_observations_excluded > 0 && `${data.undated_observations_excluded} undated ${data.undated_observations_excluded === 1 ? "entry cannot" : "entries cannot"} be placed in this range.`}
        </p>
      )}
      {data.unscored_observations > 0 && (
        <p>
          {data.unscored_observations} {data.unscored_observations === 1 ? "entry has" : "entries have"} no severity score. Scores aren't averaged across symptoms.
        </p>
      )}
      <details className="insights-data">
        <summary>Daily counts and scores</summary>
        <div className="insights-table-wrap">
          <table>
            <caption>
              Journal symptom entries by date
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
        Counts are entries, not separate episodes. Blank days don't mean
        symptom-free. No diagnosis or cause is inferred.
      </p>
    </section>
  );
}
