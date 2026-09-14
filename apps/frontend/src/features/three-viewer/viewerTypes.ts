import type { ViewerBundle } from "../../api/schemas";

export type CameraScope = "initial" | "global";

export type ViewerHealth =
  | "idle"
  | "loading_glb"
  | "model_loaded"
  | "camera_fitted"
  | "camera_fit_error"
  | "render_visible"
  | "render_blank"
  | "glb_error";

export type TelecomGlbViewerProps = {
  bundle: ViewerBundle | null;
  loadError?: string | null;
  loading?: boolean;
  onReloadBundle?: () => void | Promise<void>;
  probeWebGL?: () => boolean;
  selectedSemanticRoot?: string | null;
  selectedComponentLabel?: string | null;
  focusSemanticRoots?: readonly string[];
  knownSemanticRoots?: readonly string[];
  onSelectSemanticRoot?: (root: string | null) => void;
  expanded?: boolean;
  onToggleExpanded?: () => void;
  toAbsoluteUrl: (url: string | null | undefined) => string | null;
};
