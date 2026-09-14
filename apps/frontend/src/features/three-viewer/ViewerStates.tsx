import { Html } from "@react-three/drei";
import { AlertTriangle, Box, Image as ImageIcon, Layers3, Loader2 } from "lucide-react";
import { Component, useEffect, useState, type ReactNode } from "react";
import type { ModelObjectSummary } from "./viewerMath";
import type { ViewerHealth } from "./viewerTypes";

export function PreviewFallback({
  busy = false,
  url,
  message,
  onRetry
}: {
  busy?: boolean;
  url: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="preview-fallback">
      <BackendPreviewImage src={url} />
      <p>
        <ImageIcon size={16} aria-hidden="true" /> {message}
      </p>
      {onRetry ? (
        <button className="viewer-retry" disabled={busy} onClick={onRetry} type="button">
          {busy ? "Resynchronisation…" : "Réessayer la 3D"}
        </button>
      ) : null}
    </div>
  );
}

export function ViewerEmpty({ message }: { message: string }) {
  return (
    <div className="viewer-empty">
      <Box size={32} aria-hidden="true" />
      <p>{message}</p>
    </div>
  );
}

export function ViewerError({
  busy = false,
  message,
  onRetry,
  previewUrl
}: {
  busy?: boolean;
  message: string;
  onRetry?: () => void;
  previewUrl: string | null;
}) {
  if (previewUrl) {
    return (
      <div className="viewer-degraded-preview">
        <BackendPreviewImage src={previewUrl} />
        <div className="viewer-state-banner" role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          <div>
            <strong>Aperçu du design</strong>
            <span>{message}</span>
          </div>
          {onRetry ? (
            <button disabled={busy} onClick={onRetry} type="button">
              {busy ? "Resynchronisation…" : "Réessayer la 3D"}
            </button>
          ) : null}
        </div>
      </div>
    );
  }
  return (
    <div className="viewer-empty viewer-error">
      <AlertTriangle size={32} aria-hidden="true" />
      <p>{message}</p>
      {onRetry ? (
        <button className="viewer-retry" disabled={busy} onClick={onRetry} type="button">
          {busy ? "Resynchronisation…" : "Réessayer"}
        </button>
      ) : null}
    </div>
  );
}

export function ViewerLoading() {
  return (
    <Html center>
      <div className="viewer-loading viewer-loading-overlay" role="status">
        <Loader2 size={22} aria-hidden="true" />
        <span>Chargement du modèle 3D…</span>
      </div>
    </Html>
  );
}

export function GlbObjectSummary({
  health,
  summary
}: {
  health: ViewerHealth;
  summary: ModelObjectSummary | null;
}) {
  if (!summary) {
    return null;
  }
  return (
    <div className="viewer-object-summary" aria-label="Résumé du modèle 3D">
      <strong>
        <Layers3 size={14} aria-hidden="true" /> Modèle technique 3D
      </strong>
      <small>
        {summary.evidenceMode === "semantic_extras"
          ? `${summary.physicalEntityCount} ensembles 3D détectés`
          : "Structure 3D inspectable"} · {viewerHealthLabel(health)}
      </small>
    </div>
  );
}

function viewerHealthLabel(health: ViewerHealth): string {
  if (health === "render_visible") return "rendu visible";
  if (health === "render_blank") return "aperçu de secours";
  if (health === "camera_fitted") return "caméra cadrée";
  if (health === "loading_glb") return "chargement";
  return "chargé";
}

export class GlbErrorBoundary extends Component<
  { children: ReactNode; previewUrl: string | null; onError: () => void; onRetry: () => void },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError();
  }

  render() {
    if (this.state.failed) {
      return (
        <ViewerError
          message="Le modèle 3D n’a pas pu être chargé."
          onRetry={this.props.onRetry}
          previewUrl={this.props.previewUrl}
        />
      );
    }
    return this.props.children;
  }
}

function BackendPreviewImage({ src }: { src: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  if (failed) {
    return (
      <div className="preview-image-error" role="status">
        <AlertTriangle size={20} aria-hidden="true" />
        <span>L’aperçu n’a pas pu être chargé.</span>
      </div>
    );
  }
  return (
    <img
      src={src}
      alt="Aperçu du design généré"
      onError={() => setFailed(true)}
    />
  );
}
