import { useCallback, useRef, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { useViewerExpansion } from "./useViewerExpansion";

afterEach(cleanup);

function Workspace() {
  const [expanded, setExpanded] = useState(false);
  const [inspector, setInspector] = useState(false);
  const ref = useRef<HTMLElement>(null);
  const close = useCallback(() => setExpanded(false), []);
  useViewerExpansion(ref, expanded, close);
  return (
    <main>
      <nav aria-label="Projects"><button>Project</button></nav>
      <article>
        <section ref={ref} aria-label="Viewer">
          <button data-viewer-expansion onClick={() => setExpanded(!expanded)}>
            {expanded ? "Reduce" : "Expand"}
          </button>
          <button onClick={() => setInspector(!inspector)}>Details</button>
          {inspector && <div className="context-drawer">Inspector</div>}
        </section>
        <form aria-label="Chat"><input aria-label="Prompt" /></form>
      </article>
    </main>
  );
}

it("isolates the expanded viewer, keeps its canvas area mounted and restores interaction on Escape", () => {
  render(<Workspace />);
  const navigation = screen.getByRole("navigation");
  const chat = screen.getByRole("form");
  const viewer = screen.getByRole("region", { name: "Viewer" });
  const expand = screen.getByRole("button", { name: "Expand" });
  expand.focus();
  fireEvent.click(expand);
  expect(navigation.inert).toBe(true);
  expect(chat.inert).toBe(true);
  expect(expand).toHaveFocus();
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.getByRole("button", { name: "Expand" })).toHaveFocus();
  expect(navigation.inert).not.toBe(true);
  expect(chat.inert).not.toBe(true);
  expect(screen.getByRole("region", { name: "Viewer" })).toBe(viewer);
});

it("lets the inspector handle Escape first and restores outside interaction on unmount", () => {
  const { unmount } = render(<Workspace />);
  const navigation = screen.getByRole("navigation");
  fireEvent.click(screen.getByRole("button", { name: "Expand" }));
  fireEvent.click(screen.getByRole("button", { name: "Details" }));
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.getByRole("button", { name: "Reduce" })).toBeInTheDocument();
  unmount();
  expect(navigation.inert).not.toBe(true);
});
