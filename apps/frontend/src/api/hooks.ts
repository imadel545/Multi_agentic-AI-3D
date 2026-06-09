import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { artifactUrl, apiBaseUrl, studioApi } from "./client";
import type { StudioEvent, WorkflowStatus } from "./types";

export const queryKeys = {
  health: ["health"],
  designs: ["designs"],
  design: (workflowId?: string) => ["design", workflowId],
  events: (workflowId?: string) => ["events", workflowId],
  versions: (workflowId?: string) => ["versions", workflowId],
  inventory: ["assets", "inventory"],
  packs: ["document-packs"],
  pack: (packId?: string) => ["document-pack", packId],
  capabilities: ["document-packs", "capabilities"],
};

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: studioApi.health,
    refetchInterval: 10000,
    retry: 1,
  });
}

export function useDesigns() {
  return useQuery({ queryKey: queryKeys.designs, queryFn: studioApi.listDesigns });
}

export function useDesign(workflowId?: string) {
  return useQuery({
    queryKey: queryKeys.design(workflowId),
    queryFn: () => studioApi.getDesign(workflowId as string),
    enabled: Boolean(workflowId),
    refetchInterval: (query) => {
      const status = (query.state.data as WorkflowStatus | undefined)?.status;
      return status === "pending" || status === "generating" ? 1500 : false;
    },
  });
}

export function useDesignEvents(workflowId?: string) {
  return useQuery({
    queryKey: queryKeys.events(workflowId),
    queryFn: () => studioApi.getEvents(workflowId as string),
    enabled: Boolean(workflowId),
    refetchInterval: 2500,
  });
}

export function useVersions(workflowId?: string) {
  return useQuery({
    queryKey: queryKeys.versions(workflowId),
    queryFn: () => studioApi.listVersions(workflowId as string),
    enabled: Boolean(workflowId),
  });
}

export function useAssetInventory() {
  return useQuery({ queryKey: queryKeys.inventory, queryFn: studioApi.assetInventory });
}

export function useDocumentPacks() {
  return useQuery({ queryKey: queryKeys.packs, queryFn: studioApi.listDocumentPacks });
}

export function useDocumentPack(packId?: string) {
  return useQuery({
    queryKey: queryKeys.pack(packId),
    queryFn: () => studioApi.documentPackBundle(packId as string),
    enabled: Boolean(packId),
  });
}

export function useCapabilities() {
  return useQuery({ queryKey: queryKeys.capabilities, queryFn: studioApi.capabilities });
}

export function useStudioMutations(activeWorkflowId?: string, activePackId?: string) {
  const queryClient = useQueryClient();
  const invalidateWorkflow = (workflowId?: string) => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.design(workflowId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.events(workflowId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.versions(workflowId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.designs });
  };

  return {
    createDesign: useMutation({
      mutationFn: ({ prompt, useLlm }: { prompt: string; useLlm: boolean }) =>
        studioApi.createDesign(prompt, useLlm),
      onSuccess: (response) => invalidateWorkflow(response.workflow_id),
    }),
    editDesign: useMutation({
      mutationFn: ({ prompt }: { prompt: string }) =>
        studioApi.editDesign(activeWorkflowId as string, prompt),
      onSuccess: () => invalidateWorkflow(activeWorkflowId),
    }),
    uploadPack: useMutation({
      mutationFn: (file: File) => studioApi.uploadDocumentPack(file),
      onSuccess: (pack) => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.packs });
        void queryClient.invalidateQueries({ queryKey: queryKeys.pack(pack.pack_id) });
      },
    }),
    applyCorrection: useMutation({
      mutationFn: ({ field, value, reason }: { field: string; value: string; reason: string }) =>
        studioApi.applyCorrection(activePackId as string, field, value, reason),
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.pack(activePackId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.packs });
      },
    }),
    generateFromPack: useMutation({
      mutationFn: () => studioApi.generateDesignFromPack(activePackId as string),
      onSuccess: (response) => invalidateWorkflow(response.workflow_id),
    }),
    rollback: useMutation({
      mutationFn: ({ versionId }: { versionId: string }) =>
        studioApi.rollbackVersion(activeWorkflowId as string, versionId),
      onSuccess: () => invalidateWorkflow(activeWorkflowId),
    }),
  };
}

export function openEventStream(
  workflowId: string,
  onEvent: (event: StudioEvent) => void,
  onFallback: () => void,
): () => void {
  const source = new EventSource(`${apiBaseUrl}/designs/${workflowId}/events/stream`);
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as StudioEvent);
    } catch {
      onFallback();
    }
  };
  source.onerror = () => {
    onFallback();
    source.close();
  };
  return () => source.close();
}

export { artifactUrl };
