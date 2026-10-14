import { z } from "zod";
let csrf = "";
export function setCsrf(token: string) {
  csrf = token;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(messageFor(status, code));
  }
}
export function messageFor(status: number, code = ""): string {
  if (status === 401)
    return "Your session has ended. Sign in again to continue.";
  if (status === 403)
    return "We could not confirm this request. Refresh the page before trying again.";
  if (status === 404)
    return "This information is unavailable or your access has ended.";
  if (status === 409)
    return "This record changed or the action is no longer available. Reload the latest details before trying again.";
  if (status === 413)
    return "This file is too large. Choose a file up to 10 MB.";
  if (status === 429) return "Please wait a moment before trying again.";
  if (status === 503)
    return "This service is unavailable. Your saved information is unchanged. Try again later.";
  if (code === "contract_mismatch")
    return "We could not read the response safely. Refresh or contact support.";
  return status === 0
    ? "We could not connect. Check your connection and try again."
    : "Check the entered details and file format, then try again.";
}
export async function api<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
): Promise<T> {
  if (!path.startsWith("/api/") || path.startsWith("//"))
    throw new Error("Only same-origin API paths are allowed");
  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        ...options.headers,
        ...(options.method && options.method !== "GET"
          ? { "X-CSRFToken": csrf }
          : {}),
      },
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError(0, "network");
  }
  if (!response.ok) {
    if (response.status === 401) {
      setCsrf("");
      window.dispatchEvent(new Event("comfort:session-ended"));
    }
    if (response.status === 404)
      window.dispatchEvent(new Event("comfort:authority-check"));
    throw new ApiError(response.status, "request_failed");
  }
  try {
    return schema.parse(await response.json());
  } catch {
    throw new ApiError(502, "contract_mismatch");
  }
}
export function post<T>(
  path: string,
  schema: z.ZodType<T>,
  data: unknown,
  signal?: AbortSignal,
) {
  return api(path, schema, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
export function upload(
  path: string,
  file: File,
  kind: string,
  onProgress: (value: number) => void,
  signal: AbortSignal,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.setRequestHeader("X-CSRFToken", csrf);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(Math.round((100 * event.loaded) / event.total));
    };
    const abort = () => xhr.abort();
    signal.addEventListener("abort", abort, { once: true });
    xhr.onloadend = () => signal.removeEventListener("abort", abort);
    xhr.onerror = () => reject(new ApiError(0, "network"));
    xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
    xhr.onload = () => {
      if (xhr.status === 401)
        window.dispatchEvent(new Event("comfort:session-ended"));
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new ApiError(502, "contract_mismatch"));
        }
      } else reject(new ApiError(xhr.status, "upload_failed"));
    };
    const form = new FormData();
    form.append("file", file);
    form.append("content_kind", kind);
    xhr.send(form);
  });
}
