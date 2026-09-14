import { api } from "./api/client";
import { StudioApp } from "./StudioApp";
import type { AppProps } from "./StudioApp.types";

export type { AppProps } from "./StudioApp.types";

export {
  documentPackFilesSizeError,
  documentPackSizeError,
  latestEventCursor,
  latestEventSequence,
  needsPolling,
  reconcileAfterAmbiguousMutation,
  revisionOutcomeMessage,
  selectViewerBundleForDisplay,
  selectWorkflowToRestore,
  shouldForgetDocumentPackSession,
  userFacingError
} from "./AppSupport";

export default function App(props: AppProps) {
  return <StudioApp {...props} apiClient={props.apiClient ?? api} />;
}
