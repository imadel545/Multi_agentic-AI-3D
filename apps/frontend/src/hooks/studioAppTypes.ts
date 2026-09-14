import type { Dispatch } from "react";
import type { UserActionContext } from "../AppSupport";
import type { WorkflowMachineAction } from "../state/workflowMachine";

export type WorkflowDispatch = Dispatch<WorkflowMachineAction>;

export type DocumentPackMessageStatus = "info" | "removal_confirmed" | "error";

export type LoadSurfaceResource = <T>(
  resource: string,
  loader: () => Promise<T>,
  onValue: (value: T) => void,
  context?: UserActionContext,
  onStart?: () => void
) => Promise<T>;
