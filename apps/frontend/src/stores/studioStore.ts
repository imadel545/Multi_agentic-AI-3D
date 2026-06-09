import { create } from "zustand";

export type InspectorTab = "qa" | "assets" | "versions" | "diff" | "downloads";
export type BottomTab = "documents" | "provenance" | "events" | "memory";

type ViewerToggles = {
  beams: boolean;
  cables: boolean;
  labels: boolean;
  boundingBoxes: boolean;
  sectors: boolean;
};

type StudioState = {
  activeWorkflowId?: string;
  activePackId?: string;
  selectedVersionId?: string;
  selectedObject?: string;
  inspectorTab: InspectorTab;
  bottomTab: BottomTab;
  viewerToggles: ViewerToggles;
  setActiveWorkflowId: (workflowId?: string) => void;
  setActivePackId: (packId?: string) => void;
  setSelectedVersionId: (versionId?: string) => void;
  setSelectedObject: (objectName?: string) => void;
  setInspectorTab: (tab: InspectorTab) => void;
  setBottomTab: (tab: BottomTab) => void;
  toggleViewerLayer: (layer: keyof ViewerToggles) => void;
};

export const useStudioStore = create<StudioState>((set) => ({
  inspectorTab: "qa",
  bottomTab: "documents",
  viewerToggles: {
    beams: true,
    cables: true,
    labels: true,
    boundingBoxes: false,
    sectors: true,
  },
  setActiveWorkflowId: (workflowId) =>
    set({ activeWorkflowId: workflowId, selectedVersionId: undefined }),
  setActivePackId: (packId) => set({ activePackId: packId }),
  setSelectedVersionId: (versionId) => set({ selectedVersionId: versionId }),
  setSelectedObject: (objectName) => set({ selectedObject: objectName }),
  setInspectorTab: (tab) => set({ inspectorTab: tab }),
  setBottomTab: (tab) => set({ bottomTab: tab }),
  toggleViewerLayer: (layer) =>
    set((state) => ({
      viewerToggles: {
        ...state.viewerToggles,
        [layer]: !state.viewerToggles[layer],
      },
    })),
}));
