import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, ApiError, setCsrf } from "../api/client";
import {
  sessionSchema,
  type ActingContext,
  type Session,
} from "../api/contracts";
import { Button, Loading, Notice } from "../../design-system/primitives";
const SessionContext = createContext<Session | null>(null);
const PatientContext = createContext<ActingContext | null>(null);
export const useSession = () => {
  const value = useContext(SessionContext);
  if (!value) throw new Error("Missing session");
  return value;
};
export const usePatient = () => {
  const value = useContext(PatientContext);
  if (!value) throw new Error("Missing acting context");
  return value;
};
function csrfCookie() {
  return (
    document.cookie
      .split("; ")
      .find((value) => value.startsWith("csrftoken="))
      ?.split("=")[1] ?? ""
  );
}
export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [state, setState] = useState<
    "loading" | "ready" | "signed-out" | "error"
  >("loading");
  useEffect(() => {
    const controller = new AbortController();
    let mounted = true;
    let sequence = 0;
    const load = async () => {
      const current = ++sequence;
      try {
        const result = await api("/api/session/", sessionSchema, {
          signal: controller.signal,
        });
        if (mounted && current === sequence) {
          setCsrf(result.csrf_token);
          setSession(result);
          setState("ready");
        }
      } catch (error) {
        if (!mounted || controller.signal.aborted || current !== sequence)
          return;
        setSession(null);
        setCsrf("");
        setState(
          error instanceof ApiError && error.status === 401
            ? "signed-out"
            : "error",
        );
      }
    };
    const ended = () => {
      sequence++;
      setCsrf("");
      setSession(null);
      setState("signed-out");
    };
    const refresh = () => {
      if (document.visibilityState === "visible") void load();
    };
    void load();
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener("comfort:session-ended", ended);
    window.addEventListener("comfort:authority-check", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      mounted = false;
      controller.abort();
      clearInterval(timer);
      window.removeEventListener("comfort:session-ended", ended);
      window.removeEventListener("comfort:authority-check", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  useEffect(() => {
    if (!session) return;
    const remaining = session.expires_at * 1000 - Date.now();
    const id = setTimeout(
      () => window.dispatchEvent(new Event("comfort:session-ended")),
      Math.max(0, remaining),
    );
    return () => clearTimeout(id);
  }, [session]);
  if (state === "loading")
    return (
      <div className="auth-page">
        <Loading>Opening Comfort securely…</Loading>
      </div>
    );
  if (state !== "ready" || !session)
    return (
      <main className="auth-page">
        <div className="brand">
          comfort<span aria-hidden="true">.</span>
        </div>
        <p className="eyebrow">Your health, connected</p>
        <h1>Your records. Your next step.</h1>
        <p>Keep your history together and choose what you share.</p>
        {state === "error" ? (
          <Notice tone="error">
            We could not check your session.{" "}
            <Button
              variant="secondary"
              onPress={() => window.location.reload()}
            >
              Try again
            </Button>
          </Notice>
        ) : (
          <>
            <Notice>Your information is hidden until you sign in.</Notice>
            <form action="/auth/login/" method="post">
              <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={csrfCookie()}
              />
              <Button type="submit">Sign in securely</Button>
            </form>
          </>
        )}
      </main>
    );
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  );
}
export function ContextScope({
  context,
  children,
}: {
  context: ActingContext;
  children: ReactNode;
}) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            staleTime: 0,
            gcTime: 60000,
            refetchOnWindowFocus: true,
          },
          mutations: { retry: false },
        },
      }),
  );
  useEffect(
    () => () => {
      void client.cancelQueries();
      client.clear();
    },
    [client],
  );
  return (
    <PatientContext.Provider value={context}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </PatientContext.Provider>
  );
}
