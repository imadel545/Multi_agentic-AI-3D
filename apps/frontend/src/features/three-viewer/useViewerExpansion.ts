import { useEffect, type RefObject } from "react";

/** Keep the same canvas mounted while isolating its expanded interaction area. */
export function useViewerExpansion(
  container: RefObject<HTMLElement | null>,
  expanded: boolean,
  onClose: () => void,
) {
  useEffect(() => {
    const viewer = container.current;
    if (!expanded || !viewer) return;
    const previousFocus = document.activeElement;
    const siblings = new Map<HTMLElement, boolean>();
    let current: HTMLElement = viewer;
    while (current.parentElement && current !== document.body) {
      for (const sibling of current.parentElement.children) {
        if (sibling instanceof HTMLElement && sibling !== current) {
          siblings.set(sibling, sibling.inert);
          sibling.inert = true;
        }
      }
      current = current.parentElement;
    }
    viewer.querySelector<HTMLButtonElement>("[data-viewer-expansion]")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      // The inspector owns the first Escape; the next one exits the viewer.
      if (viewer.querySelector(".context-drawer")) return;
      event.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      for (const [sibling, inert] of siblings) sibling.inert = inert;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus();
      }
    };
  }, [container, expanded, onClose]);
}
