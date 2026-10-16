import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { useSession } from "../../services/auth/session";
import { api, post, ApiError } from "../../services/api/client";
import { Button, ConfirmDialog, Notice } from "../../design-system/primitives";
import {
  TextField,
  TextAreaField,
  SelectField,
} from "../../design-system/fields";
import type { Concern } from "../care/contracts";
import {
  draftSchema,
  journalAIRequestSchema,
  journalAIRequestsSchema,
  dateLabel,
  eventSchema,
  toValues,
  type Draft,
  type Fields,
  type JournalEvent,
} from "./contracts";

export default function Editor({
  base,
  initial,
  eventId = null,
  baseRevision = 0,
  recovery,
  concerns,
  onDone,
  onClose,
}: {
  base: string;
  initial: Fields;
  eventId?: string | null;
  baseRevision?: number;
  recovery?: Draft;
  concerns: Concern[];
  onDone: (event: JournalEvent) => void;
  onClose: () => void;
}) {
  const session = useSession();
  const cache = useQueryClient();
  const recoveryBindingMatches =
    recovery?.event_id === eventId && recovery?.base_revision === baseRevision;
  const [fields, setFields] = useState(initial);
  const [revision, setRevision] = useState(baseRevision);
  const [status, setStatus] = useState(
    recovery &&
      recoveryBindingMatches &&
      JSON.stringify(initial) === JSON.stringify(recovery.fields)
      ? "Private draft saved"
      : "Changes are not yet saved",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(
    recovery && recoveryBindingMatches
      ? JSON.stringify(initial) !== JSON.stringify(recovery.fields)
      : Boolean(initial.description),
  );
  const [latest, setLatest] = useState<JournalEvent | null>(null);
  const [otherDraft, setOtherDraft] = useState<Draft | null>(null);
  const [expiry, setExpiry] = useState(false);
  const [aiRequest, setAiRequest] = useState<z.infer<typeof journalAIRequestSchema> | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiApplying, setAiApplying] = useState(false);
  const [aiError, setAiError] = useState("");
  const [aiSelected, setAiSelected] = useState<Record<string, boolean>>({});
  const latestFields = useRef(fields),
    draftRevision = useRef(recovery?.revision ?? 0),
    baseRev = useRef(revision);
  const ack = useRef(
    recovery && recoveryBindingMatches ? JSON.stringify(recovery.fields) : "",
  );
  const acknowledgedDraft = useRef(recovery);
  const remember = useCallback(() => {
    cache.setQueryData([base, "editor"], {
      fields: latestFields.current,
      eventId,
      revision: baseRev.current,
      recovery: acknowledgedDraft.current,
    });
  }, [base, cache, eventId]);
  const pending = useRef<Promise<void> | null>(null),
    mounted = useRef(true),
    published = useRef(false);
  const message = useRef<HTMLDivElement>(null);
  useEffect(() => {
    cache.setQueryDefaults([base, "editor"], { gcTime: Infinity });
    remember();
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, [base, cache, remember]);
  useEffect(() => {
    let active = true;
    void api(base + "ai/requests/", journalAIRequestsSchema)
      .then(({ requests }) => {
        const saved = requests.find((item) => item.draft_revision === draftRevision.current);
        if (active && saved) setAiRequest(saved);
      })
      .catch(() => { /* AI history is optional; the manual editor remains available. */ });
    return () => { active = false; };
  }, [base]);
  useEffect(() => {
    if (!aiRequest || !["queued", "processing", "waiting_model"].includes(aiRequest.state)) return;
    let active = true;
    const timer = setTimeout(() => {
      void api(base + `ai/requests/${aiRequest.id}/`, journalAIRequestSchema)
        .then((value) => { if (active) setAiRequest(value); })
        .catch((failure) => { if (active) setAiError(failure instanceof Error ? failure.message : "We could not check the request."); });
    }, 2000);
    return () => { active = false; clearTimeout(timer); };
  }, [base, aiRequest]);
  const flush = useCallback(async () => {
    while (pending.current) await pending.current;
    const snapshot = JSON.stringify(latestFields.current);
    if (ack.current === snapshot && draftRevision.current > 0) return;
    const operation = (async () => {
      if (mounted.current) setStatus("Saving private draft…");
      const response = await post(base + "draft/", draftSchema, {
        fields: latestFields.current,
        expected_revision: draftRevision.current,
        event_id: eventId,
        base_revision: baseRev.current,
      });
      draftRevision.current = response.draft!.revision;
      acknowledgedDraft.current = response.draft!;
      ack.current = snapshot;
      remember();
      if (mounted.current) {
        setStatus("Private draft saved");
        setDirty(JSON.stringify(latestFields.current) !== snapshot);
      }
    })();
    pending.current = operation;
    try {
      await operation;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        try {
          const current = await api(base + "draft/", draftSchema);
          if (mounted.current) setOtherDraft(current.draft);
        } catch {
          /* Live authority or connectivity may have ended. Never replace a draft blindly. */
        }
      }
      throw error;
    } finally {
      if (pending.current === operation) pending.current = null;
    }
  }, [base, eventId, remember]);
  const failure = useCallback((failure: unknown) => {
    if (!mounted.current) return;
    setError(
      failure instanceof Error
        ? failure.message
        : "We could not save. Your writing is still in this editor.",
    );
    setStatus("Recent changes are not saved. Keep this page open and retry.");
  }, []);
  useEffect(() => {
    if (!dirty || busy || otherDraft) return;
    const timer = setTimeout(() => {
      void flush().catch(failure);
    }, 600);
    return () => clearTimeout(timer);
  }, [fields, dirty, busy, otherDraft, flush, failure]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty && !published.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    const leave = (event: Event) => {
      if (dirty || pending.current) {
        event.preventDefault();
        setError(
          "Save your draft or discard it before leaving this patient context.",
        );
      }
    };
    const leaveLink = (event: MouseEvent) => {
      if (
        (dirty || pending.current) &&
        (event.target as Element).closest?.("a[href]")
      ) {
        event.preventDefault();
        event.stopPropagation();
        setError(
          "Your latest writing has not been saved. Use Keep draft and close, or discard the draft, before leaving.",
        );
        message.current?.focus();
      }
    };
    window.addEventListener("beforeunload", warn);
    window.addEventListener("comfort:leave-context", leave);
    document.addEventListener("click", leaveLink, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      window.removeEventListener("comfort:leave-context", leave);
      document.removeEventListener("click", leaveLink, true);
    };
  }, [dirty]);
  useEffect(() => {
    const time = Math.max(0, session.expires_at * 1000 - Date.now() - 45000);
    const timer = setTimeout(() => {
      setExpiry(true);
      if (dirty) void flush().catch(failure);
    }, time);
    return () => clearTimeout(timer);
  }, [session.expires_at, dirty, flush, failure]);
  const update = (key: keyof Fields, value: string) => {
    const next = { ...latestFields.current, [key]: value } as Fields;
    if (key === "category" && value === "note") next.severity = "";
    if (key === "time") next.fold = "";
    latestFields.current = next;
    remember();
    setFields(next);
    setDirty(true);
    setError("");
  };
  const input = (key: keyof Fields) => ({
    value: fields[key],
    onChange: (
      event: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >,
    ) => update(key, event.target.value),
  });
  const publish = async () => {
    setError("");
    setBusy(true);
    try {
      const values = toValues(latestFields.current);
      await flush();
      const result = await post(
        base + (eventId ? `${eventId}/` : ""),
        eventSchema,
        {
          values,
          expected_revision: baseRev.current,
          draft_revision: draftRevision.current,
        },
      );
      published.current = true;
      onDone(result);
    } catch (error) {
      failure(error);
      if (error instanceof ApiError && error.status === 409 && eventId) {
        try {
          setLatest(await api(base + eventId + "/", eventSchema));
        } catch {
          /* The draft remains visible; live access may have ended. */
        }
      }
      message.current?.focus();
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  const organizeWithAI = async () => {
    setAiError("");
    setAiBusy(true);
    try {
      await flush();
      if (ack.current !== JSON.stringify(latestFields.current)) throw new Error("Wait for your private draft to finish saving, then try again.");
      const response = await post(base + "ai/requests/", journalAIRequestSchema, {
        draft_revision: draftRevision.current,
      });
      setAiRequest(response);
      setAiSelected({});
    } catch (failure) {
      setAiError(failure instanceof Error ? failure.message : "Apertus could not start this request.");
    } finally {
      if (mounted.current) setAiBusy(false);
    }
  };
  const applyAIProposal = async () => {
    if (!aiRequest?.proposal || aiRequest.stale || aiRequest.expired) return;
    setAiBusy(true);
    setAiApplying(true);
    setAiError("");
    try {
      const next = { ...latestFields.current };
      const proposed = aiRequest.proposal.fields;
      const evidence = aiRequest.proposal.evidence;
      if (evidence.category && (aiSelected.category ?? true)) next.category = proposed.category;
      if (evidence.occurrence && (aiSelected.occurrence ?? true)) {
        next.precision = proposed.precision;
        next.year = proposed.year;
        next.month = proposed.month;
        next.day = proposed.day;
      }
      if (evidence.time && (aiSelected.time ?? true)) { next.time = proposed.time; next.fold = ""; }
      if (evidence.severity && (aiSelected.severity ?? true)) next.severity = proposed.severity;
      if (next.category === "note") next.severity = "";
      const outcome = JSON.stringify(next) === JSON.stringify(proposed) ? "accepted" : "edited";
      const reviewed = await post(base + `ai/requests/${aiRequest.id}/`, journalAIRequestSchema, {
        outcome,
        fields: next,
      });
      const saved = await api(base + "draft/", draftSchema);
      if (saved.draft) {
        latestFields.current = saved.draft.fields;
        setFields(saved.draft.fields);
        draftRevision.current = saved.draft.revision;
        acknowledgedDraft.current = saved.draft;
        ack.current = JSON.stringify(saved.draft.fields);
        setDirty(false);
        remember();
      }
      setAiRequest(reviewed);
      setStatus("Suggestions copied to your private draft. Review them, then save when ready.");
    } catch (failure) {
      setAiError(failure instanceof Error ? failure.message : "We could not apply those suggestions.");
    } finally {
      if (mounted.current) { setAiBusy(false); setAiApplying(false); }
    }
  };
  const reviewAIProposal = async (outcome: "rejected" | "abandoned") => {
    if (!aiRequest) return;
    setAiBusy(true);
    setAiError("");
    try {
      setAiRequest(await post(base + `ai/requests/${aiRequest.id}/`, journalAIRequestSchema, { outcome }));
    } catch (failure) {
      setAiError(failure instanceof Error ? failure.message : "We could not save your review.");
    } finally {
      if (mounted.current) setAiBusy(false);
    }
  };
  return (
    <section
      className="panel journal-editor"
      aria-labelledby="journal-editor-title"
    >
      <p className="eyebrow">Private · patient-reported</p>
      <h2 id="journal-editor-title">
        {eventId ? "Correct your observation" : "A moment for your health"}
      </h2>
      <p>A few words are enough. Optional details can be added later.</p>
      {expiry && (
        <Notice tone="warning" live>
          Your session ends soon. Acknowledged drafts can be recovered after
          signing in. Changes still marked unsaved may be lost if you leave.
        </Notice>
      )}
      <div ref={message} tabIndex={-1}>
        {error && (
          <Notice tone="error" live>
            {error}
          </Notice>
        )}
      </div>
      {otherDraft && (
        <section className="journal-conflict" aria-label="Saved draft conflict">
          <h3>A different draft is already saved</h3>
          <p>
            Saved {new Date(otherDraft.updated_at).toLocaleString()} · revision{" "}
            {otherDraft.revision}. It has not been overwritten. Your current
            writing is still in the editor below.
          </p>
          <blockquote className="journal-writing">
            {otherDraft.fields.description || "No text saved in that draft."}
          </blockquote>
          <div className="actions">
            <ConfirmDialog
              trigger="Keep saved draft instead"
              title="Keep the saved draft?"
              confirmLabel="Keep saved draft"
              onConfirm={() => {
                published.current = true;
                onClose();
              }}
            >
              <p>
                Your current unsaved writing will be discarded. The existing
                saved draft remains available to resume.
              </p>
            </ConfirmDialog>
            <ConfirmDialog
              trigger="Replace with my writing"
              title="Replace the saved private draft?"
              confirmLabel="Replace draft"
              onConfirm={() => {
                draftRevision.current = otherDraft.revision;
                acknowledgedDraft.current = otherDraft;
                ack.current = "";
                setOtherDraft(null);
                setError("");
                setDirty(true);
                remember();
              }}
            >
              <p>
                The displayed saved draft will be replaced by your current
                writing. No observation is published by replacing a draft.
              </p>
            </ConfirmDialog>
          </div>
        </section>
      )}
      {latest && (
        <div className="journal-conflict">
          <h3>Compare with revision {latest.revision}</h3>
          <blockquote>{latest.values.description}</blockquote>
          <dl>
            <dt>Entry type</dt>
            <dd>{latest.values.category}</dd>
            <dt>Occurrence</dt>
            <dd>
              {dateLabel(latest.values.occurrence)}
              {latest.values.time ? ` · ${latest.values.time}` : ""} ·{" "}
              {latest.values.timezone}
              {latest.values.fold === 1 ? " · second occurrence" : ""}
            </dd>
            <dt>Severity</dt>
            <dd>
              {latest.values.severity === null
                ? "Not recorded"
                : `${latest.values.severity} / 10`}
            </dd>
            <dt>Health concern</dt>
            <dd>
              {latest.values.concern_id
                ? (concerns.find((item) => item.id === latest.values.concern_id)
                    ?.values.title ?? "Saved concern; details unavailable")
                : "No linked concern"}
            </dd>
            <dt>Status</dt>
            <dd>{latest.status}</dd>
          </dl>
          <p>
            Your writing is still below. Review all of these details before
            applying your correction. Saving will use the fields in your editor;
            changes are not merged automatically.
          </p>
          <Button
            variant="secondary"
            onPress={() => {
              baseRev.current = latest.revision;
              remember();
              setRevision(latest.revision);
              ack.current = "";
              setDirty(true);
              setLatest(null);
              setError("");
            }}
          >
            Use revision {latest.revision} as the starting point
          </Button>
        </div>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void publish();
        }}
      >
        <fieldset className="care-fields" disabled={busy || aiApplying}>
          <SelectField
            id="journal-category"
            label="What would you like to record?"
            options={[
              { value: "note", label: "Personal note" },
              { value: "symptom", label: "Symptom" },
            ]}
            selectProps={input("category")}
          />
          <TextAreaField
            id="journal-description"
            label={
              fields.category === "symptom"
                ? "What did you experience?"
                : "Your note"
            }
            inputProps={{
              ...input("description"),
              maxLength: 2000,
              rows: 5,
              required: true,
              autoFocus: true,
            }}
          />
          <small>{fields.description.length} / 2,000 characters</small>
          <section className="journal-ai-review" aria-label="Optional Apertus assistance">
            <Button variant="secondary" isDisabled={aiBusy || busy || !fields.description.trim()} onPress={() => void organizeWithAI()}>
              {aiBusy ? "Working…" : "Organize with Apertus"}
            </Button>
            <p>Only the text in this saved draft is sent to your configured Apertus model. It will suggest fields for you to review; it will not save a Journal observation.</p>
            {aiError && <Notice tone="error" live>{aiError}</Notice>}
            {aiRequest && <p role="status">Apertus request: {aiRequest.state === "waiting_model" ? "waiting for the local model" : aiRequest.state.replaceAll("_", " ")}{aiRequest.latency_seconds !== null ? ` · ${aiRequest.latency_seconds.toFixed(1)} seconds` : ""}{aiRequest.error_code ? ` · ${aiRequest.error_code}` : ""}</p>}
            {aiRequest?.proposal && aiRequest.proposal.review === null && (
              <div className="journal-ai-proposal">
                <h3>Suggestions to review</h3>
                {aiRequest.stale ? <Notice tone="warning">Your draft changed after this request. Keep the current writing and ask Apertus to organize it again.</Notice> : null}
                {aiRequest.expired ? <Notice tone="warning">This proposal has expired. Ask Apertus again to review a fresh result.</Notice> : null}
                <p>Your original text is preserved: “{aiRequest.proposal.fields.description}”</p>
                <p>Dates, clock times and numerical severity are checked against explicit text. Unsupported or conflicting suggestions stay unknown. Copying suggestions keeps your other draft fields.</p>
                {aiRequest.proposal.ambiguities.length > 0 && <p>Needs your judgment: {aiRequest.proposal.ambiguities.join("; ")}</p>}
                {Object.entries({ category: "Entry type", occurrence: "Date or time period", time: "Time", severity: "Severity" }).filter(([key]) => Boolean(aiRequest.proposal!.evidence[key])).map(([key, label]) => (
                  <label key={key} className="journal-ai-choice">
                    <input type="checkbox" checked={aiSelected[key] ?? true} onChange={(event) => setAiSelected((current) => ({ ...current, [key]: event.target.checked }))} disabled={aiRequest.stale || aiRequest.expired || aiBusy} />
                    Use suggested {label.toLowerCase()}: {key === "category" ? aiRequest.proposal!.fields.category : key === "occurrence" ? `${aiRequest.proposal!.fields.precision} ${aiRequest.proposal!.fields.year}${aiRequest.proposal!.fields.month ? `-${aiRequest.proposal!.fields.month}` : ""}${aiRequest.proposal!.fields.day ? `-${aiRequest.proposal!.fields.day}` : ""}` : key === "time" ? aiRequest.proposal!.fields.time : `${aiRequest.proposal!.fields.severity}/10`}
                    <span>Supported by “{aiRequest.proposal!.evidence[key].quote}”</span>
                    {aiRequest.proposal!.evidence[key].origin === "source_extraction" && <span>Copied from your source text. Confirm this value before applying.</span>}
                  </label>
                ))}
                {aiRequest.proposal.unknown.length > 0 && <p>Not recorded because it was not clear: {aiRequest.proposal.unknown.join("; ")}</p>}
                {!aiRequest.stale && !aiRequest.expired && <div className="actions">
                  <Button variant="secondary" isDisabled={aiBusy} onPress={() => void applyAIProposal()}>Copy selected suggestions to draft</Button>
                  <Button variant="secondary" isDisabled={aiBusy} onPress={() => void reviewAIProposal("rejected")}>Reject suggestions</Button>
                </div>}
              </div>
            )}
            {aiRequest?.review && <p role="status">You {aiRequest.review} these suggestions. Your Journal entry is still unpublished.</p>}
          </section>
          <fieldset className="care-date">
            <legend>When it happened</legend>
            <SelectField
              id="journal-precision"
              label="How much of the date do you know?"
              options={[
                { value: "day", label: "Exact day" },
                { value: "month", label: "Month and year" },
                { value: "year", label: "Year only" },
                { value: "unknown", label: "Date unknown" },
              ]}
              selectProps={input("precision")}
            />
            {fields.precision === "day" ? (
              <TextField
                id="journal-date"
                label="Date"
                inputProps={{
                  type: "date",
                  value: `${fields.year}-${fields.month.padStart(2, "0")}-${fields.day.padStart(2, "0")}`,
                  required: true,
                  onChange: (event) => {
                    const [year = "", month = "", day = ""] =
                      event.target.value.split("-");
                    const next = { ...latestFields.current, year, month, day };
                    latestFields.current = next;
                    remember();
                    setFields(next);
                    setDirty(true);
                  },
                }}
              />
            ) : (
              fields.precision !== "unknown" && (
                <div className="form-grid">
                  <TextField
                    id="journal-year"
                    label="Year"
                    inputProps={{
                      ...input("year"),
                      inputMode: "numeric",
                      maxLength: 4,
                      required: true,
                    }}
                  />
                  {fields.precision === "month" && (
                    <TextField
                      id="journal-month"
                      label="Month (1–12)"
                      inputProps={{
                        ...input("month"),
                        inputMode: "numeric",
                        maxLength: 2,
                        required: true,
                      }}
                    />
                  )}
                </div>
              )
            )}
          </fieldset>
          <details className="journal-optional">
            <summary>Optional details</summary>
            {fields.category === "symptom" && (
              <TextField
                id="journal-severity"
                label="Severity (optional)"
                help="0 means no severity; 10 means the most severe you can imagine. Blank means not recorded."
                inputProps={{
                  ...input("severity"),
                  type: "number",
                  min: 0,
                  max: 10,
                  step: 1,
                }}
              />
            )}
            <SelectField
              id="journal-concern"
              label="Related health concern (optional)"
              help="A link records your association; it does not establish a cause."
              options={[
                { value: "", label: "No linked concern" },
                ...concerns
                  .filter(
                    (c) => c.status === "active" || c.id === fields.concern_id,
                  )
                  .map((c) => ({
                    value: c.id,
                    label:
                      c.values.title +
                      (c.status === "archived" ? " (archived)" : ""),
                  })),
              ]}
              selectProps={input("concern_id")}
            />
            {fields.precision === "day" && (
              <TextField
                id="journal-time"
                label="Time (optional)"
                inputProps={{ ...input("time"), type: "time" }}
              />
            )}
            <TextField
              id="journal-timezone"
              label="Time zone"
              help="For example Africa/Nairobi or Europe/Zurich. The local date stays as entered."
              inputProps={{
                ...input("timezone"),
                maxLength: 64,
                required: true,
              }}
            />
            {fields.time && (
              <SelectField
                id="journal-fold"
                label="If clocks repeat this time"
                options={[
                  { value: "", label: "Not specified" },
                  { value: "0", label: "First occurrence" },
                  { value: "1", label: "Second occurrence" },
                ]}
                selectProps={input("fold")}
              />
            )}
          </details>
        </fieldset>
        <p className="journal-draft-status" role="status">
          {status}. Drafts are private and are not Journal entries until you
          save.
        </p>
        <div className="actions">
          <Button type="submit" isDisabled={busy || Boolean(otherDraft)}>
            {busy
              ? "Saving…"
              : eventId
                ? "Save correction"
                : "Save observation"}
          </Button>
          <Button
            variant="secondary"
            isDisabled={busy || Boolean(otherDraft)}
            onPress={() => {
              setBusy(true);
              void flush()
                .then(onClose)
                .catch(failure)
                .finally(() => {
                  if (mounted.current) setBusy(false);
                });
            }}
          >
            Keep draft and close
          </Button>
          <ConfirmDialog
            trigger="Discard draft"
            title="Discard this private draft?"
            confirmLabel="Discard draft"
            disabled={busy}
            onConfirm={() => {
              setBusy(true);
              const operation = pending.current ?? Promise.resolve();
              void operation
                .then(async () => {
                  if (draftRevision.current)
                    await post(
                      base + "draft/discard/",
                      z.object({ discarded: z.literal(true) }),
                      { expected_revision: draftRevision.current },
                    );
                  published.current = true;
                  onClose();
                })
                .catch(failure)
                .finally(() => {
                  if (mounted.current) setBusy(false);
                });
            }}
          >
            <p>
              This removes the recovery draft. Saved observations and their
              history remain.
            </p>
          </ConfirmDialog>
        </div>
      </form>
    </section>
  );
}
