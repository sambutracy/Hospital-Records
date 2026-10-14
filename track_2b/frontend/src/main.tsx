import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SessionProvider } from "./services/auth/session";
import App from "./app/App";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import "./design-system/tokens.css";
createRoot(document.getElementById("root")!).render(
  <BrowserRouter basename="/app">
    <SessionProvider>
      <App />
    </SessionProvider>
  </BrowserRouter>,
);
