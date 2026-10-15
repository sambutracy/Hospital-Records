import { lazy, Suspense, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { cancelPrivateRequests } from "../services/api/client";
import {
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  House,
  Files,
  BookOpen,
  HeartHandshake,
  ChartNoAxesCombined,
  ShieldCheck,
  ArrowUpRight,
} from "lucide-react";
import { useSession, usePatient, ContextScope } from "../services/auth/session";
import {
  Button,
  EmptyState,
  Loading,
  Notice,
  PageHeader,
} from "../design-system/primitives";
import Home from "../features/home/Home";
const Records = lazy(() => import("../features/records/Records"));
const Detail = lazy(() => import("../features/records/Detail"));
const Consultation = lazy(() => import("../features/care/Consultation"));
const CareHome = lazy(() => import("../features/care/CareHome"));
const Relationships = lazy(() => import("../features/care/Relationships"));
const Journal = lazy(() => import("../features/journal/Journal"));
function ContextRoute() {
  const { workspaceId } = useParams();
  const session = useSession();
  const context = session.contexts.find(
    (item) => item.workspace_id === workspaceId,
  );
  if (!context)
    return (
      <main className="auth-page">
        <EmptyState
          title="This workspace is unavailable"
          action={<Link to="/">Return to your contexts</Link>}
        >
          You may not have access, or access may have ended.
        </EmptyState>
      </main>
    );
  return (
    <ContextScope
      key={`${context.id}:${context.capabilities.join(",")}`}
      context={context}
    >
      <Shell />
    </ContextScope>
  );
}
const navigation = [
  ["home", "Home", House],
  ["records", "Records", Files],
  ["journal", "Journal", BookOpen],
  ["care", "My Care", HeartHandshake],
  ["insights", "Insights", ChartNoAxesCombined],
  ["account", "Account & privacy", ShieldCheck],
] as const;
function Shell() {
  const client = useQueryClient();
  const [signingOut, setSigningOut] = useState(false);
  const patient = usePatient();
  const session = useSession();
  const navigate = useNavigate();
  const root = `/workspaces/${patient.workspace_id}`;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="navigation-rail">
        <Link className="brand" to={`${root}/home`} aria-label="Comfort home">
          comfort<span aria-hidden="true">.</span>
        </Link>
        <p className="rail-intro">A little more continuity.</p>
        <nav aria-label="Main navigation">
          {navigation.map(([path, label, Icon]) => (
            <NavLink key={path} to={`${root}/${path}`}>
              <Icon aria-hidden="true" size={20} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="rail-foot">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>You choose what to share.</span>
        </div>
      </aside>
      <div className="shell-body">
        <header className="top-bar">
          <div className="context-control">
            <label htmlFor="context">Acting context</label>
            <select
              id="context"
              value={patient.id}
              onChange={(event) => {
                if (
                  window.dispatchEvent(
                    new Event("comfort:leave-context", { cancelable: true }),
                  )
                )
                  navigate(`/workspaces/${event.target.value}/home`);
              }}
            >
              {session.contexts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} · {item.patient_display_name}
                </option>
              ))}
            </select>
            <span className="context-capacity">
              {patient.capacity} · {patient.patient_display_name}
            </span>
          </div>
          <form
            method="post"
            action="/auth/logout/"
            onSubmit={(event) => {
              if (
                !window.dispatchEvent(
                  new Event("comfort:leave-context", { cancelable: true }),
                )
              ) {
                if (
                  !window.confirm(
                    "Recent Journal changes have not been saved. Sign out and discard those unsaved changes? Your last acknowledged server draft will remain private.",
                  )
                ) {
                  event.preventDefault();
                  return;
                }
              }
              // Keep this native POST form connected until navigation starts.
              // Removing the whole session shell here can cancel form submission.
              cancelPrivateRequests(patient.workspace_id);
              void client.cancelQueries();
              client.clear();
              setSigningOut(true);
            }}
          >
            <input
              type="hidden"
              name="csrfmiddlewaretoken"
              value={session.csrf_token}
            />
            <Button type="submit" variant="quiet">
              Sign out
            </Button>
          </form>
        </header>
        <nav className="mobile-navigation" aria-label="Mobile main navigation">
          {navigation.slice(0, 4).map(([path, label, Icon]) => (
            <NavLink key={path} to={`${root}/${path}`}>
              <Icon size={20} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
          <NavLink to={`${root}/account`}>More</NavLink>
        </nav>
        <main id="main-content" className="main-content" tabIndex={-1}>
          {signingOut ? (
            <Loading>Signing out securely…</Loading>
          ) : (
            <Suspense fallback={<Loading />}>
              <Outlet />
            </Suspense>
          )}
        </main>
        <footer className="app-footer">
          Comfort helps organize your information. It does not provide a
          diagnosis.
        </footer>
      </div>
    </div>
  );
}
function Contexts() {
  const session = useSession();
  if (session.default_context_id)
    return (
      <Navigate replace to={`/workspaces/${session.default_context_id}/home`} />
    );
  return (
    <main className="auth-page">
      <PageHeader title="Choose your context" />
      {session.contexts.map((context) => (
        <Link key={context.id} to={`/workspaces/${context.id}/home`}>
          {context.label} · {context.patient_display_name}
        </Link>
      ))}
      {!session.contexts.length && (
        <Notice>
          No workspace is currently available for this account. Contact your
          administrator if you expected access.
        </Notice>
      )}
    </main>
  );
}
function Pending({ title, children }: { title: string; children: string }) {
  return (
    <>
      <PageHeader title={title} />
      <EmptyState title="This part of Comfort is being developed">
        {children}
      </EmptyState>
      <Link to="../records">Go to your records</Link>
    </>
  );
}
function Account() {
  const patient = usePatient();
  return (
    <>
      <PageHeader title="Account & privacy">
        Your identity and your permissions stay separate.
      </PageHeader>
      <section className="panel">
        <h2>Your current context</h2>
        <p>
          {patient.patient_display_name} · {patient.capacity}
        </p>
        <p>
          Caregiver and guardian access needs verified authority and separate
          permissions. A care contact alone does not grant access.
        </p>
        <h2>Existing account tools</h2>
        <p>
          These tools currently open the earlier interface while their new
          Comfort journeys are built.
        </p>
        <div className="stack">
          <Link to="../insights">Insights · in development</Link>
          <a href={`/workspaces/${patient.id}/profile/`}>
            Personal profile and care circle{" "}
            <ArrowUpRight size={16} aria-hidden="true" />
          </a>
          <a href={`/workspaces/${patient.id}/medications/`}>
            Reported prescriptions and medication records{" "}
            <ArrowUpRight size={16} aria-hidden="true" />
          </a>
          <a href="/received/">
            Information shared with this account{" "}
            <ArrowUpRight size={16} aria-hidden="true" />
          </a>
        </div>
      </section>
    </>
  );
}
export default function App() {
  return (
    <Routes>
      <Route index element={<Contexts />} />
      <Route path="workspaces/:workspaceId" element={<ContextRoute />}>
        <Route index element={<Navigate replace to="home" />} />
        <Route path="home" element={<Home />} />
        <Route path="records" element={<Records />} />
        <Route path="records/:recordId" element={<Detail />} />
        <Route path="care" element={<CareHome />} />
        <Route
          path="care/concerns"
          element={<Relationships page="concerns" />}
        />
        <Route path="care/team" element={<Relationships page="team" />} />
        <Route path="care/visits" element={<Consultation />} />
        <Route path="care/:packetId" element={<Consultation />} />
        <Route path="journal" element={<Journal />} />
        <Route
          path="insights"
          element={
            <Pending title="Insights">
              A source-linked care timeline will be added after care events and
              journal entries are available.
            </Pending>
          }
        />
        <Route path="account" element={<Account />} />
        <Route
          path="*"
          element={
            <Pending title="Page unavailable">
              Choose a page from the main navigation.
            </Pending>
          }
        />
      </Route>
      <Route path="*" element={<Contexts />} />
    </Routes>
  );
}
