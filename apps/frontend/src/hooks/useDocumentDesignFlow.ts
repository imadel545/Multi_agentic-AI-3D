import { useCallback, useEffect, useState, type MutableRefObject } from "react";
import type { TelecomStudioApi } from "../api/client";
import type {
  DocumentPackCapabilities,
  DocumentPackSummary,
  MultimodalConsent,
  ParseRequirementsResponse
} from "../api/schemas";
import {
  clearDocumentPackSession,
  readDocumentPackSession,
  writeDocumentPackSession
} from "../state/documentPackSession";
import type { WorkflowMachineState } from "../state/workflowMachine";
import {
  documentPackBrowserStorage,
  documentPackFilesSizeError,
  shouldForgetDocumentPackSession,
  userFacingError
} from "../AppSupport";
import type { LoadSurfaceResource, WorkflowDispatch } from "./studioAppTypes";

const ActivePromptDetail = "high" as const;

type UseDocumentDesignFlowOptions = {
  apiClient: TelecomStudioApi;
  beginCreatedWorkflow: (workflowId: string) => Promise<void>;
  chatId?: string;
  clearRevisionMessages: () => void;
  closeEventStream: () => void;
  dispatch: WorkflowDispatch;
  documentCapabilities: DocumentPackCapabilities | null;
  initialDocumentPackId?: string | null;
  initialWorkflowId?: string | null;
  invalidateBootstrapRestore: () => void;
  loadSurfaceResource: LoadSurfaceResource;
  onDocumentPackDetached?: (packId: string) => Promise<void>;
  onDocumentPackLinked?: (id: string) => Promise<void>;
  onDraftChange?: (value: string) => void;
  onWorkflowCreated?: (id: string, submittedPrompt: string) => Promise<void>;
  state: WorkflowMachineState;
  submissionInFlightRef: MutableRefObject<boolean>;
};

export function useDocumentDesignFlow({
  apiClient,
  beginCreatedWorkflow,
  chatId,
  clearRevisionMessages,
  closeEventStream,
  dispatch,
  documentCapabilities,
  initialDocumentPackId,
  initialWorkflowId,
  invalidateBootstrapRestore,
  loadSurfaceResource,
  onDocumentPackDetached,
  onDocumentPackLinked,
  onDraftChange,
  onWorkflowCreated,
  state,
  submissionInFlightRef
}: UseDocumentDesignFlowOptions) {
  const [documentPackSummary, setDocumentPackSummary] = useState<DocumentPackSummary | null>(null);
  const [documentPackMessage, setDocumentPackMessage] = useState<string | null>(null);
  const [documentPackBusy, setDocumentPackBusy] = useState(false);
  const [requirementsAnalysis, setRequirementsAnalysis] = useState<ParseRequirementsResponse | null>(null);
  const [analyzedPrompt, setAnalyzedPrompt] = useState<string | null>(null);
  const [submittedRequirementsHash, setSubmittedRequirementsHash] = useState<string | null>(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [submissionBusy, setSubmissionBusy] = useState(false);
  const [creationPath, setCreationPath] = useState<"telecom" | "free">("telecom");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [multimodalConsent, setMultimodalConsent] = useState<MultimodalConsent>("disabled");

  const multimodalIntelligence = state.summary?.runtime_capabilities?.multimodal_intelligence ??
    state.viewerBundle?.runtime_capabilities?.multimodal_intelligence ?? null;
  const multimodalConsentAvailable = multimodalIntelligence?.enabled === true &&
    (multimodalIntelligence.status === "configured_unverified" || multimodalIntelligence.status === "operational");

  useEffect(() => {
    if (!multimodalConsentAvailable && multimodalConsent !== "disabled") {
      setMultimodalConsent("disabled");
    }
  }, [multimodalConsent, multimodalConsentAvailable]);

  const clearAnalysis = useCallback(() => {
    setRequirementsAnalysis(null);
    setAnalyzedPrompt(null);
    setSubmittedRequirementsHash(null);
    setAnalysisError(null);
  }, []);

  const loadDocumentPackSummary = useCallback(async (packId: string) => loadSurfaceResource(
    "document_review",
    () => apiClient.documentPackSummary(packId),
    (summary) => {
      setDocumentPackSummary(summary);
      const storage = documentPackBrowserStorage();
      if (storage && initialWorkflowId === undefined) writeDocumentPackSession(storage, summary.pack_id);
    },
    "documents"
  ), [apiClient, initialWorkflowId, loadSurfaceResource]);

  useEffect(() => {
    const storage = documentPackBrowserStorage();
    const packId = initialWorkflowId !== undefined
      ? initialDocumentPackId
      : storage ? readDocumentPackSession(storage) : null;
    if (!packId) return;
    let cancelled = false;
    setDocumentPackBusy(true);
    void loadDocumentPackSummary(packId).then((summary) => {
      if (!cancelled) setDocumentPackMessage(
        `${summary.document_count} ${summary.document_count === 1 ? "pièce jointe restaurée" : "pièces jointes restaurées"}. Ajoutez votre demande pour continuer.`
      );
    }).catch((error) => {
      const missingPack = shouldForgetDocumentPackSession(error);
      if (missingPack && storage) clearDocumentPackSession(storage);
      if (!cancelled) {
        setDocumentPackSummary(null);
        setDocumentPackMessage(missingPack
          ? "Les pièces précédentes ne sont plus disponibles. Importez-les de nouveau."
          : "Les pièces jointes n’ont pas pu être resynchronisées. Réessayez dans un instant.");
      }
    }).finally(() => {
      if (!cancelled) setDocumentPackBusy(false);
    });
    return () => { cancelled = true; };
  }, [initialDocumentPackId, initialWorkflowId, loadDocumentPackSummary]);

  const retryDocumentPackSummary = useCallback(async () => {
    const storage = documentPackBrowserStorage();
    const packId = documentPackSummary?.pack_id ?? (storage ? readDocumentPackSession(storage) : null);
    if (!packId) return;
    setDocumentPackBusy(true);
    setDocumentPackMessage(null);
    try {
      const summary = await loadDocumentPackSummary(packId);
      setDocumentPackMessage(`${summary.document_count} pièce(s) jointe(s) à cette conversation.`);
    } catch (error) {
      setDocumentPackMessage(userFacingError(error, "documents"));
    } finally {
      setDocumentPackBusy(false);
    }
  }, [documentPackSummary?.pack_id, loadDocumentPackSummary]);

  const detachDocumentPack = useCallback(async () => {
    const storage = documentPackBrowserStorage();
    const packId = documentPackSummary?.pack_id ?? initialDocumentPackId ??
      (storage ? readDocumentPackSession(storage) : null);
    if (!packId) return;
    setDocumentPackBusy(true);
    setDocumentPackMessage(null);
    try {
      await apiClient.deleteDocumentPack(packId, chatId);
      await onDocumentPackDetached?.(packId);
      if (storage) clearDocumentPackSession(storage);
      setDocumentPackSummary(null);
      clearAnalysis();
      setDocumentPackMessage(chatId
        ? "Cahier de charge retiré de cette conversation. Vous pouvez joindre d’autres pièces."
        : "Cahier de charge retiré de cette session. Vous pouvez joindre d’autres pièces.");
    } catch (error) {
      setDocumentPackMessage(userFacingError(error, "documents"));
    } finally {
      setDocumentPackBusy(false);
    }
  }, [apiClient, chatId, clearAnalysis, documentPackSummary?.pack_id, initialDocumentPackId, onDocumentPackDetached]);

  const finishDesignCreation = useCallback(async (workflowId: string, prompt: string) => {
    await onWorkflowCreated?.(workflowId, prompt);
    await beginCreatedWorkflow(workflowId);
  }, [beginCreatedWorkflow, onWorkflowCreated]);

  const submitFreeIntent = useCallback(async () => {
    if (submissionInFlightRef.current || !state.prompt.trim()) return;
    const prompt = state.prompt.trim();
    invalidateBootstrapRestore();
    submissionInFlightRef.current = true;
    setSubmissionBusy(true);
    closeEventStream();
    dispatch({ type: "SUBMIT_STARTED" });
    clearAnalysis();
    try {
      const created = await apiClient.createDesign({
        chat_id: chatId,
        document_pack_id: documentPackSummary?.pack_id,
        requirements_text: prompt,
        options: {
          detail_level: ActivePromptDetail,
          use_llm: true,
          multimodal_consent: multimodalConsentAvailable ? multimodalConsent : "disabled"
        }
      });
      await finishDesignCreation(created.workflow_id, prompt);
    } catch (error) {
      dispatch({ type: "REQUEST_FAILED", message: userFacingError(error, "generation") });
    } finally {
      submissionInFlightRef.current = false;
      setSubmissionBusy(false);
    }
  }, [apiClient, chatId, clearAnalysis, closeEventStream, dispatch, documentPackSummary?.pack_id, finishDesignCreation, invalidateBootstrapRestore, multimodalConsent, multimodalConsentAvailable, state.prompt, submissionInFlightRef]);

  const analyzePrompt = useCallback(async () => {
    if (!state.prompt.trim()) return;
    const prompt = state.prompt.trim();
    setSubmittedRequirementsHash(null);
    setAnalysisBusy(true);
    setAnalysisError(null);
    try {
      const analysis = await apiClient.parseRequirements({
        chat_id: chatId,
        document_pack_id: documentPackSummary?.pack_id,
        requirements_text: prompt,
        detail_level: ActivePromptDetail,
        use_llm: null
      });
      setRequirementsAnalysis(analysis);
      setAnalyzedPrompt(prompt);
      if (!analysis.requirements) {
        setAnalysisError("La demande n’a pas pu être structurée pour confirmation. Précisez les contraintes puis réessayez.");
      }
    } catch (error) {
      setRequirementsAnalysis(null);
      setAnalyzedPrompt(null);
      setAnalysisError(userFacingError(error, "analysis"));
    } finally {
      setAnalysisBusy(false);
    }
  }, [apiClient, chatId, documentPackSummary?.pack_id, state.prompt]);

  const submitPrompt = useCallback(async () => {
    if (submissionInFlightRef.current) return;
    const prompt = state.prompt.trim();
    if (!prompt || analyzedPrompt !== prompt || !requirementsAnalysis?.requirements || !requirementsAnalysis.requirements_hash) {
      setAnalysisError("Analysez puis confirmez la demande actuelle avant de générer le design.");
      return;
    }
    if (!requirementsAnalysis.analysis_receipt) {
      setAnalysisError("La provenance vérifiée de cette analyse n’est pas disponible. Réanalysez la demande avant de générer le design.");
      return;
    }
    if (documentPackSummary && !requirementsAnalysis.document_context_hash) {
      setAnalysisError("Le contexte des pièces jointes n’a pas été attesté. Relancez l’analyse avant de générer le design.");
      return;
    }
    if (requirementsAnalysis.requirements.requires_confirmation) {
      setAnalysisError("La demande contient des valeurs contradictoires. Corrigez les champs signalés puis relancez l’analyse.");
      return;
    }
    if (submittedRequirementsHash === requirementsAnalysis.requirements_hash && state.phase !== "failed") {
      setAnalysisError("Cette compréhension a déjà lancé le design actif. Modifiez ou réanalysez la demande avant de créer un autre workflow.");
      return;
    }
    invalidateBootstrapRestore();
    submissionInFlightRef.current = true;
    setSubmissionBusy(true);
    closeEventStream();
    clearRevisionMessages();
    dispatch({ type: "SUBMIT_STARTED" });
    try {
      const created = await apiClient.createDesign({
        chat_id: chatId,
        document_pack_id: documentPackSummary?.pack_id,
        document_context_hash: requirementsAnalysis.document_context_hash ?? undefined,
        requirements_text: prompt,
        confirmed_requirements: requirementsAnalysis.requirements,
        confirmed_requirements_hash: requirementsAnalysis.requirements_hash,
        confirmed_analysis_receipt: requirementsAnalysis.analysis_receipt,
        options: {
          detail_level: ActivePromptDetail,
          use_llm: null,
          multimodal_consent: multimodalConsentAvailable ? multimodalConsent : "disabled"
        }
      });
      setSubmittedRequirementsHash(requirementsAnalysis.requirements_hash);
      await finishDesignCreation(created.workflow_id, prompt);
    } catch (error) {
      dispatch({ type: "REQUEST_FAILED", message: userFacingError(error, "generation") });
    } finally {
      submissionInFlightRef.current = false;
      setSubmissionBusy(false);
    }
  }, [analyzedPrompt, apiClient, chatId, clearRevisionMessages, closeEventStream, dispatch, documentPackSummary, finishDesignCreation, invalidateBootstrapRestore, multimodalConsent, multimodalConsentAvailable, requirementsAnalysis, state.phase, state.prompt, submissionInFlightRef, submittedRequirementsHash]);

  const changePrompt = useCallback((prompt: string) => {
    clearAnalysis();
    onDraftChange?.(prompt);
    dispatch({ type: "PROMPT_CHANGED", prompt });
  }, [clearAnalysis, dispatch, onDraftChange]);

  const uploadDocumentPack = useCallback(async (files: File[]) => {
    const sizeError = documentPackFilesSizeError(files, documentCapabilities);
    if (sizeError) {
      setDocumentPackMessage(sizeError);
      return false;
    }
    setDocumentPackBusy(true);
    setDocumentPackMessage(null);
    try {
      const summary = await apiClient.createDocumentPack(files, chatId);
      await onDocumentPackLinked?.(summary.pack_id);
      setDocumentPackSummary(summary);
      clearAnalysis();
      setDocumentPackMessage(`${summary.document_count} ${summary.document_count === 1 ? "pièce ajoutée" : "pièces ajoutées"}. Décrivez maintenant ce que vous souhaitez concevoir.`);
      return true;
    } catch (error) {
      setDocumentPackMessage(userFacingError(error, "documents"));
      return false;
    } finally {
      setDocumentPackBusy(false);
    }
  }, [apiClient, chatId, clearAnalysis, documentCapabilities, onDocumentPackLinked]);

  const analysisIsCurrent = analyzedPrompt === state.prompt.trim() &&
    requirementsAnalysis?.requirements != null && requirementsAnalysis.requirements_hash != null;
  const analysisWasSubmitted = analysisIsCurrent &&
    submittedRequirementsHash === requirementsAnalysis?.requirements_hash;

  return {
    analysisBusy, analysisError, analysisIsCurrent, analysisWasSubmitted, analyzePrompt,
    changePrompt, clearAnalysis, creationPath, detachDocumentPack, documentPackBusy,
    documentPackMessage, documentPackSummary, multimodalConsent, multimodalConsentAvailable,
    multimodalIntelligence, requirementsAnalysis, retryDocumentPackSummary, setCreationPath,
    setMultimodalConsent, submissionBusy, submitFreeIntent, submitPrompt, uploadDocumentPack
  };
}
