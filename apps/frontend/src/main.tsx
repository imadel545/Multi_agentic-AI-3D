import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import WorkspaceShell from "./components/WorkspaceShell";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <WorkspaceShell />
  </StrictMode>,
);
