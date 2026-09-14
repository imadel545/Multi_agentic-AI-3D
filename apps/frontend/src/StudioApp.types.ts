import type { TelecomStudioApi } from "./api/client";

export type AppProps = {
  apiClient?: TelecomStudioApi;
  chatId?: string;
  initialWorkflowId?: string | null;
  initialPrompt?: string;
  initialDocumentPackId?: string | null;
  onDraftChange?: (value: string) => void;
  onWorkflowCreated?: (id: string, submittedPrompt: string) => Promise<void>;
  onDocumentPackLinked?: (id: string) => Promise<void>;
  onDocumentPackDetached?: (packId: string) => Promise<void>;
  onBusyChange?: (busy: boolean) => void;
  onMutationBusyChange?: (busy: boolean) => void;
  onNewChat?: (draft?: string) => void;
};
