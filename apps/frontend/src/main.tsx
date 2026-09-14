import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import WorkspaceShell from "./components/WorkspaceShell";
import { AuthGate } from "./components/AuthGate";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthGate>
      <WorkspaceShell />
    </AuthGate>
  </StrictMode>,
);
