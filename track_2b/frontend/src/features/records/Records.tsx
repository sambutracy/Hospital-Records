import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlus2 } from "lucide-react";
import { TextField } from "../../design-system/fields";
import { usePatient } from "../../services/auth/session";
import { post } from "../../services/api/client";
import {
  packetSchema,
  recordsSchema,
  type SourceVersion,
} from "../../services/api/contracts";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  Loading,
  Notice,
  PageHeader,
} from "../../design-system/primitives";
import { RecordCard, types } from "./RecordCard";
import Upload from "./Upload";
import Assistant from "./Assistant";
const initial = {
  q: "",
  document_type: "",
  reviewed: "",
  order: "upload",
  uploaded_from: "",
  uploaded_until: "",
  document_year: "",
};
export default function Records() {
  const patient = usePatient();
  const client = useQueryClient();
  const navigate = useNavigate();
  const base = `/api/workspaces/${patient.id}/`;
  const [showUpload, setShowUpload] = useState(false);
  const [draft, setDraft] = useState(initial);
  const [filters, setFilters] = useState(initial);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<SourceVersion[]>([]);
  const [purpose, setPurpose] = useState("");
  const records = useQuery({
    queryKey: ["records", patient.id, filters, offset],
    queryFn: ({ signal }) =>
      post(
        base + "records/search/",
        recordsSchema,
        { ...filters, offset },
        signal,
      ),
    refetchInterval: (query) =>
      query.state.data?.records.some((record) =>
        ["queued", "processing", "waiting_model"].includes(
          record.jobs[0]?.state,
        ),
      )
        ? Math.min(30000, 8000 * 2 ** Math.min(2, query.state.dataUpdateCount))
        : false,
    refetchIntervalInBackground: false,
  });
  const create = useMutation({
    mutationFn: () =>
      post(base + "packets/", packetSchema, {
        purpose,
        source_version_ids: selected.map((item) => item.id),
      }),
    onSuccess: (packet) => {
      setSelected([]);
      void client.invalidateQueries({ queryKey: ["packets"] });
      navigate(`../care/${packet.id}`);
    },
  });
  const can = (action: string) => patient.capabilities.includes(action);
  return (
    <>
      <PageHeader
        eyebrow="YOUR ORIGINALS"
        title="Records"
        action={
          can("upload_source") && (
            <Button onPress={() => setShowUpload(true)}>
              <FilePlus2 size={18} aria-hidden="true" />
              Add a record
            </Button>
          )
        }
      >
        A clear place for your health documents, from every visit.
      </PageHeader>
      {showUpload && (
        <Upload
          onSaved={() => {
            void client.invalidateQueries({ queryKey: ["records"] });
            void client.invalidateQueries({ queryKey: ["home-records"] });
          }}
        />
      )}
      <form
        className="panel form-section"
        onSubmit={(event) => {
          event.preventDefault();
          setFilters(draft);
          setOffset(0);
        }}
      >
        <div className="toolbar">
          <TextField
            id="search"
            label="Find a record"
            help="Search terms stay out of page URLs. This keyword search works without AI."
            inputProps={{
              value: draft.q,
              maxLength: 160,
              onChange: (event) =>
                setDraft({ ...draft, q: event.target.value }),
              placeholder: "Filename, facility or words in readable text",
            }}
          />
          <Button type="submit">Search records</Button>
        </div>
        <details>
          <summary>Filter and sort records</summary>
          <div className="filters">
            <div className="field">
              <label htmlFor="filter-type">Document type</label>
              <select
                id="filter-type"
                value={draft.document_type}
                onChange={(event) =>
                  setDraft({ ...draft, document_type: event.target.value })
                }
              >
                <option value="">All types</option>
                {Object.entries(types).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="filter-review">Details review</label>
              <select
                id="filter-review"
                value={draft.reviewed}
                onChange={(event) =>
                  setDraft({ ...draft, reviewed: event.target.value })
                }
              >
                <option value="">All records</option>
                <option value="yes">Details reviewed by you</option>
                <option value="no">Needs review</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="order">Sort</label>
              <select
                id="order"
                value={draft.order}
                onChange={(event) =>
                  setDraft({ ...draft, order: event.target.value })
                }
              >
                <option value="upload">Newest upload</option>
                <option value="document_date">
                  Newest known document date
                </option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="uploaded-from">Uploaded from (UTC)</label>
              <input
                type="date"
                id="uploaded-from"
                value={draft.uploaded_from}
                onChange={(event) =>
                  setDraft({ ...draft, uploaded_from: event.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="uploaded-until">Uploaded through (UTC)</label>
              <input
                type="date"
                id="uploaded-until"
                value={draft.uploaded_until}
                onChange={(event) =>
                  setDraft({ ...draft, uploaded_until: event.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="document-year">Known document year</label>
              <input
                type="number"
                id="document-year"
                min={1}
                max={9999}
                value={draft.document_year}
                onChange={(event) =>
                  setDraft({ ...draft, document_year: event.target.value })
                }
              />
              <small>
                Includes partial dates in that year; excludes unknown dates.
              </small>
            </div>
          </div>
        </details>
      </form>
      {selected.length > 0 && (
        <section
          className="selection-bar form-section"
          aria-label="Visit selection"
        >
          <div>
            <strong>{selected.length} exact versions selected</strong>
            <p>Selection stays private. Later uploads are not included.</p>
            <p>Select up to 30 exact original versions for one visit.</p>
            <ul>
              {selected.map((item) => (
                <li key={item.id}>
                  {item.original_filename} · version {item.version_number}{" "}
                  <Button
                    variant="quiet"
                    onPress={() =>
                      setSelected(
                        selected.filter((value) => value.id !== item.id),
                      )
                    }
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
            <div className="field">
              <label htmlFor="purpose">Purpose of your visit</label>
              <input
                id="purpose"
                maxLength={180}
                value={purpose}
                onChange={(event) => setPurpose(event.target.value)}
              />
            </div>
          </div>
          <ConfirmDialog
            trigger="Prepare for a visit"
            title="Save your private visit selection?"
            confirmLabel="Save private selection"
            disabled={!purpose.trim() || create.isPending}
            onConfirm={() => create.mutate()}
          >
            <p>{purpose}</p>
            <p>
              {selected.length} exact original versions will be frozen with
              their currently reviewed details. This does not share them or
              create a medical summary.
            </p>
          </ConfirmDialog>
        </section>
      )}
      {create.isError && (
        <Notice tone="error" live>
          {create.error.message}
        </Notice>
      )}
      <div className="section-heading">
        <h2>
          {records.data ? `${records.data.total} records` : "Your library"}
        </h2>
        <Link to="../care">Your visit selections</Link>
      </div>
      {records.isPending ? (
        <Loading />
      ) : records.isError ? (
        <Notice tone="error" live>
          {records.error.message}
          <div>
            <Button variant="secondary" onPress={() => void records.refetch()}>
              Try again
            </Button>
          </div>
        </Notice>
      ) : records.data.records.length ? (
        <>
          <div className="record-grid">
            {records.data.records.map((record) => (
              <RecordCard
                key={record.id}
                record={record}
                selected={selected.some(
                  (item) => item.id === record.current_version.id,
                )}
                selectionDisabled={
                  selected.length >= 30 &&
                  !selected.some(
                    (item) => item.id === record.current_version.id,
                  )
                }
                onSelect={
                  can("prepare_packet")
                    ? (checked) =>
                        setSelected((previous) =>
                          checked
                            ? [
                                ...previous.filter(
                                  (item) =>
                                    item.id !== record.current_version.id,
                                ),
                                record.current_version,
                              ]
                            : previous.filter(
                                (item) => item.id !== record.current_version.id,
                              ),
                        )
                    : undefined
                }
              />
            ))}
          </div>
          <div className="pagination">
            <Button
              variant="secondary"
              isDisabled={offset === 0}
              onPress={() => setOffset(Math.max(0, offset - 50))}
            >
              Previous
            </Button>
            <span>
              Showing {offset + 1}–{offset + records.data.records.length} of{" "}
              {records.data.total}
            </span>
            <Button
              variant="secondary"
              isDisabled={!records.data.has_more}
              onPress={() => setOffset(offset + 50)}
            >
              Next
            </Button>
          </div>
        </>
      ) : (
        <EmptyState
          title={
            Object.values(filters).some((value, key) => key !== 3 && !!value)
              ? "No records match these filters"
              : "Your library starts with one record"
          }
        >
          Add an original, or change your search. An empty result does not prove
          a medical event did not happen.
        </EmptyState>
      )}
      <Assistant query={draft.q} />
    </>
  );
}
