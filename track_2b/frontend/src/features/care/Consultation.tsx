import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { usePatient } from "../../services/auth/session";
import { api } from "../../services/api/client";
import { packetSchema, packetsSchema } from "../../services/api/contracts";
import {
  EmptyState,
  Loading,
  Notice,
  PageHeader,
} from "../../design-system/primitives";
import { partialDate, typeLabel } from "../records/RecordCard";
import Assistant from "../records/Assistant";
import CareNavigation from "./CareNavigation";
import CareIntelligence from "../care-intelligence/CareIntelligence";
export default function Consultation() {
  const patient = usePatient();
  const { packetId } = useParams();
  const base = `/api/workspaces/${patient.id}/`;
  const list = useQuery({
    queryKey: ["packets"],
    queryFn: ({ signal }) => api(base + "packets/", packetsSchema, { signal }),
  });
  const detail = useQuery({
    queryKey: ["packet", packetId],
    enabled: !!packetId,
    queryFn: ({ signal }) =>
      api(base + `packets/${packetId}/`, packetSchema, { signal }),
  });
  return (
    <>
      <PageHeader
        eyebrow="MY CARE"
        title={detail.data?.purpose ?? "Prepare for a visit"}
      >
        Bring together the information you may want for a conversation with a
        clinician. It stays private until you separately approve access.
      </PageHeader>
      <CareNavigation />
      {packetId ? (
        detail.isPending ? (
          <Loading />
        ) : detail.isError ? (
          <Notice tone="error">{detail.error.message}</Notice>
        ) : (
          detail.data && (
            <>
              <Notice>
                This private visit collection contains {detail.data.items.length}{" "}
                saved record versions. New uploads and later corrections are not
                added automatically.
              </Notice>
              <div className="record-grid form-section">
                {detail.data.items.map((item) => (
                  <article className="record-card" key={item.source_version.id}>
                    <h3>{item.source_version.original_filename}</h3>
                    <p>
                      {typeLabel(item.metadata.document_type)} ·{" "}
                      {partialDate(item.metadata.document_date)}
                    </p>
                    <p>
                      {item.metadata.facility_name ??
                        "Issuing facility unknown"}
                    </p>
                    <a href={item.source_version.download_url}>
                      Download selected original · version{" "}
                      {item.source_version.version_number}
                    </a>
                  </article>
                ))}
              </div>
              <Assistant packetId={packetId} />
              {patient.capabilities.includes("manage_profile")&&patient.capabilities.includes("prepare_packet")&&<CareIntelligence key={packetId} packetId={packetId} />}
            </>
          )
        )
      ) : (
        <>
          <Link className="button button--primary" to="../records">
            Choose records for a visit
          </Link>
          <div className="section-heading">
            <h2>Records you have set aside for a visit</h2>
          </div>
          {list.isPending ? (
            <Loading />
          ) : list.isError ? (
            <Notice tone="error">{list.error.message}</Notice>
          ) : list.data.packets.length ? (
            <div className="record-grid">
              {list.data.packets.map((packet) => (
                <article key={packet.id} className="record-card">
                  <h3>
                    <Link to={`../care/${packet.id}`}>{packet.purpose}</Link>
                  </h3>
                  <p>
                    Private · saved{" "}
                    {new Date(packet.created_at).toLocaleDateString()}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="Prepare with what matters">
              Choose records in Records, add a short note about the visit, then
              save your private collection.
            </EmptyState>
          )}
          <section className="quiet-section">
            <h2>Sharing information for a visit</h2>
            <p>
              Existing time-limited sharing and contribution tools remain
              available in the earlier interface.
            </p>
            <a href={`/workspaces/${patient.id}/`}>
              Open existing sharing tools
            </a>
          </section>
        </>
      )}
    </>
  );
}
