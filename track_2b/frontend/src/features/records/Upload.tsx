import { useEffect, useRef, useState } from "react";
import { ModalOverlay, Modal, Dialog, Heading } from "react-aria-components";
import { useNavigate } from "react-router-dom";
import { usePatient } from "../../services/auth/session";
import { upload } from "../../services/api/client";
import { uploadSchema } from "../../services/api/contracts";
import { Button, Notice } from "../../design-system/primitives";
type FileState = {
  file: File;
  state: "ready" | "sending" | "saved" | "duplicate" | "error";
  progress: number;
  message?: string;
};
export function validateFile(file: File) {
  if (file.size > 10 * 1024 * 1024) return "Choose a file up to 10 MB.";
  if (!/\.(pdf|jpe?g|png|dcm|dicom)$/i.test(file.name))
    return "Choose PDF, JPEG, PNG or DICOM.";
  return undefined;
}
export default function Upload({ onSaved }: { onSaved: () => void }) {
  const patient = usePatient();
  const navigate = useNavigate();
  const [files, setFiles] = useState<FileState[]>([]);
  const [kind, setKind] = useState("document");
  const [busy, setBusy] = useState(false);
  const [warning, setWarning] = useState("");
  const [leaving, setLeaving] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const unsaved = files.some(
    (item) => !["saved", "duplicate"].includes(item.state),
  );
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!unsaved) return;
    const before = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const clicked = (event: MouseEvent) => {
      const link = (event.target as Element).closest("a");
      if (
        !link ||
        event.ctrlKey ||
        event.metaKey ||
        link.target === "_blank" ||
        link.getAttribute("href")?.startsWith("#")
      )
        return;
      const url = new URL(link.href);
      if (url.pathname === window.location.pathname) return;
      event.preventDefault();
      event.stopPropagation();
      setLeaving(url.pathname);
    };
    window.addEventListener("beforeunload", before);
    document.addEventListener("click", clicked, true);
    return () => {
      window.removeEventListener("beforeunload", before);
      document.removeEventListener("click", clicked, true);
    };
  }, [unsaved]);
  function select(input: FileList | null) {
    if (!input) return;
    if (input.length > 30) {
      setWarning(
        "Select up to 30 files at a time. Your current selection is unchanged.",
      );
      return;
    }
    setWarning("");
    setFiles(
      Array.from(input, (file) => {
        const message = validateFile(file);
        return {
          file,
          state: message ? "error" : "ready",
          progress: 0,
          message,
        };
      }),
    );
  }
  async function send(retry = false) {
    if (busy) return;
    setBusy(true);
    const abort = new AbortController();
    controller.current = abort;
    for (let index = 0; index < files.length; index++) {
      const item = files[index];
      if (retry ? item.state !== "error" : item.state !== "ready") continue;
      const validation = validateFile(item.file);
      if (validation) continue;
      const update = (patch: Partial<FileState>) =>
        setFiles((previous) =>
          previous.map((value, i) =>
            i === index ? { ...value, ...patch } : value,
          ),
        );
      update({ state: "sending", progress: 0, message: undefined });
      try {
        const result = uploadSchema.parse(
          await upload(
            `/api/workspaces/${patient.id}/records/`,
            item.file,
            kind,
            (progress) => update({ progress }),
            abort.signal,
          ),
        );
        update({
          state: result.created ? "saved" : "duplicate",
          progress: 100,
          message: result.created
            ? "Original saved. Processing continues in the background."
            : "This original is already saved. No additional copy was created.",
        });
        onSaved();
      } catch (error) {
        if (abort.signal.aborted) break;
        update({
          state: "error",
          message:
            error instanceof Error
              ? error.message
              : "This upload did not finish. Try again.",
        });
      }
    }
    if (!abort.signal.aborted) setBusy(false);
  }
  return (
    <section className="upload-box" aria-labelledby="upload-heading">
      <h2 id="upload-heading">Add your originals</h2>
      <p>
        PDF, JPEG, PNG or Part 10 DICOM · up to 10 MB each · up to 30 files per
        selection.
      </p>
      <p>
        Files are private. A saved original stays available even when text
        reading cannot finish.
      </p>
      <div className="field form-section">
        <label htmlFor="image-kind">For JPEG and PNG files</label>
        <select
          id="image-kind"
          value={kind}
          disabled={busy}
          onChange={(event) => setKind(event.target.value)}
        >
          <option value="document">
            Photograph or scan of a written report
          </option>
          <option value="medical_image">
            MRI, ultrasound or other image export
          </option>
        </select>
        <small>
          PDFs remain documents; DICOM is always a medical image. Images are not
          interpreted medically.
        </small>
      </div>
      <label className="field" htmlFor="files">
        Choose files
        <input
          id="files"
          type="file"
          multiple
          disabled={busy || unsaved}
          accept=".pdf,.jpg,.jpeg,.png,.dcm,.dicom"
          onChange={(event) => select(event.target.files)}
        />
      </label>
      {warning && (
        <Notice tone="error" live>
          {warning}
        </Notice>
      )}
      {files.length > 0 && (
        <>
          <ul className="file-list">
            {files.map((item, index) => (
              <li key={`${index}-${item.file.name}`}>
                <strong>{item.file.name}</strong>
                <p>
                  {item.state === "sending"
                    ? `Uploading · ${item.progress}%`
                    : (item.message ?? "Ready to upload")}
                </p>
                {item.state === "sending" && (
                  <progress
                    value={item.progress}
                    max={100}
                    aria-label={`Upload progress for ${item.file.name}`}
                  />
                )}
              </li>
            ))}
          </ul>
          <div className="actions">
            <Button
              isDisabled={busy || !files.some((item) => item.state === "ready")}
              onPress={() => void send()}
            >
              Save selected files
            </Button>
            {files.some((item) => item.state === "error") && (
              <Button
                variant="secondary"
                isDisabled={busy}
                onPress={() => void send(true)}
              >
                Retry failed files
              </Button>
            )}
            <Button
              variant="quiet"
              isDisabled={busy}
              onPress={() => setFiles([])}
            >
              Clear selection
            </Button>
          </div>
          <div role="status" className="form-section">
            {
              files.filter((item) =>
                ["saved", "duplicate"].includes(item.state),
              ).length
            }{" "}
            of {files.length} originals saved or already present.
          </div>
        </>
      )}
      <small>
        Leaving this page loses files that have not finished uploading. Saved
        originals stay in Comfort.
      </small>
      <ModalOverlay
        isOpen={leaving !== null}
        onOpenChange={(open) => {
          if (!open) setLeaving(null);
        }}
        className="modal-overlay"
      >
        <Modal className="modal">
          <Dialog>
            <Heading slot="title">Leave your upload?</Heading>
            <p>
              Files that have not finished uploading will need to be selected
              again. Your saved originals stay available.
            </p>
            <div className="actions">
              <Button variant="secondary" onPress={() => setLeaving(null)}>
                Keep uploading
              </Button>
              <Button
                onPress={() => {
                  const path = leaving!;
                  setLeaving(null);
                  setFiles([]);
                  controller.current?.abort();
                  if (path.startsWith("/app/")) navigate(path.slice(4));
                  else window.location.assign(path);
                }}
              >
                Leave page
              </Button>
            </div>
          </Dialog>
        </Modal>
      </ModalOverlay>
    </section>
  );
}
