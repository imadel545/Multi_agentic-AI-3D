import "@testing-library/jest-dom/vitest";
import { createElement } from "react";
import type { ReactNode } from "react";
import { vi } from "vitest";

vi.mock("react-resizable-panels", () => ({
  Group: ({ children, className }: { children: ReactNode; className?: string }) => (
    createElement("div", { className }, children)
  ),
  Panel: ({ children }: { children: ReactNode }) => createElement("div", null, children),
  Separator: ({ className }: { className?: string }) => createElement("div", { className }),
}));
