import type { RefObject } from "react";
import { PanelLeftClose, Plus, RadioTower } from "lucide-react";
import type { WorkflowStatus } from "../api/schemas";

type WorkspaceBrandProps = {
  sidebarControl: RefObject<HTMLButtonElement | null>;
  sidebarOpen: boolean;
  onToggle: () => void;
};

export function WorkspaceBrand({
  sidebarControl,
  sidebarOpen,
  onToggle,
}: WorkspaceBrandProps) {
  return (
    <div className="workspace-brand">
      <div className="workspace-brand-identity">
        <span className="workspace-brand-logo-frame">
          <img
            alt="Circet — Créateur de réseaux"
            className="workspace-brand-logo"
            src="/brand/circet-logo.jpg"
          />
        </span>
        <span className="workspace-brand-subtitle">Studio 3D assisté par IA</span>
      </div>
      <button
        ref={sidebarControl}
        aria-controls="workspace-sidebar"
        aria-expanded={sidebarOpen}
        aria-label="Replier les projets"
        className="sidebar-toggle"
        onClick={onToggle}
        type="button"
      >
        <PanelLeftClose aria-hidden="true" size={18} />
      </button>
    </div>
  );
}

type WorkspaceHistoryProps = {
  designs: WorkflowStatus[];
  navigationLocked: boolean;
  onAttach: (design: WorkflowStatus) => void;
  onClose: () => void;
};

export function WorkspaceHistory({
  designs,
  navigationLocked,
  onAttach,
  onClose,
}: WorkspaceHistoryProps) {
  return (
    <section className="workspace-history">
      <h1>Retrouver un design</h1>
      <p>
        Rattachez un résultat existant à une conversation de ce projet. Ses
        versions et messages sont conservés.
      </p>
      <button type="button" onClick={onClose}>
        Fermer
      </button>
      {designs.map((design) => (
        <button
          type="button"
          disabled={navigationLocked}
          key={design.workflow_id}
          onClick={() => onAttach(design)}
        >
          <span>
            {new Date(design.created_at ?? "").toLocaleString("fr-FR")}
          </span>
          <span>
            {design.status === "completed"
              ? "Résultat disponible"
              : design.status === "running"
                ? "En cours"
                : "À examiner"}
          </span>
        </button>
      ))}
      {designs.length === 0 ? (
        <p>Aucun design non classé n’est disponible.</p>
      ) : null}
    </section>
  );
}

type WorkspaceWelcomeProps = {
  hasProject: boolean;
  navigationLocked: boolean;
  onStart: () => void;
};

export function WorkspaceWelcome({
  hasProject,
  navigationLocked,
  onStart,
}: WorkspaceWelcomeProps) {
  return (
    <section className="workspace-welcome">
      <RadioTower aria-hidden="true" size={42} />
      <p>Votre espace de conception</p>
      <h1>
        {hasProject ? "Une conversation, un design." : "Du projet au modèle 3D."}
      </h1>
      <p>
        {hasProject
          ? "Décrivez votre intention, ajoutez vos documents et faites évoluer le modèle au fil de la conversation."
          : "Organisez vos sites et vos échanges, puis concevez et modifiez vos modèles dans un même espace."}
      </p>
      <button type="button" disabled={navigationLocked} onClick={onStart}>
        <Plus aria-hidden="true" size={18} />
        {hasProject ? "Commencer une conversation" : "Créer mon premier projet"}
      </button>
    </section>
  );
}
