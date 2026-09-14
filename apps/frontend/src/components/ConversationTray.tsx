import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, MessageSquareText, X } from "lucide-react";

/** A bounded conversation surface that never changes the canvas dimensions. */
export function ConversationTray({
  children,
  activity,
  attention,
  open: controlledOpen,
  onOpenChange
}: {
  children: ReactNode;
  activity?: ReactNode;
  attention: unknown;
  /** Keep the tray coordinated with sibling command surfaces when needed. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [internalOpen, setInternalOpen] = useState(Boolean(attention));
  const isControlled = controlledOpen !== undefined;
  const open = controlledOpen ?? internalOpen;
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const feed = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);

  const changeOpen = useCallback((next: boolean) => {
    if (!isControlled) setInternalOpen(next);
    onOpenChange?.(next);
  }, [isControlled, onOpenChange]);

  useEffect(() => {
    if (attention && !open) changeOpen(true);
  }, [attention, changeOpen, open]);
  useEffect(() => {
    if (!open) return;
    const scrollToLatest = () => {
      if (followLatest.current && feed.current) feed.current.scrollTop = feed.current.scrollHeight;
    };
    followLatest.current = true;
    const frame = requestAnimationFrame(scrollToLatest);
    const observer = new MutationObserver(scrollToLatest);
    if (feed.current) {
      observer.observe(feed.current, {
        childList: true,
        subtree: true,
        characterData: true
      });
    }
    const close = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented ||
          !panel.current?.contains(document.activeElement)) return;
      event.preventDefault();
      changeOpen(false);
      trigger.current?.focus();
    };
    window.addEventListener("keydown", close);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("keydown", close);
    };
  }, [changeOpen, open]);
  return (
    <div className="conversation-tray">
      <div className="conversation-tray-bar">
        <button
          ref={trigger}
          type="button"
          aria-expanded={open}
          aria-controls="studio-conversation-panel"
          onClick={() => changeOpen(!open)}
        >
          <MessageSquareText size={16} aria-hidden="true" />
          <span>Conversation</span>
          <ChevronDown className={open ? "expanded" : ""} size={15} />
        </button>
        {activity}
      </div>
      <div
        ref={panel}
        className="conversation-popover"
        id="studio-conversation-panel"
        hidden={!open}
      >
        <header>
          <strong>Conversation</strong>
          <button
            type="button"
            aria-label="Fermer la conversation"
            onClick={() => {
              changeOpen(false);
              trigger.current?.focus();
            }}
          >
            <X size={17} />
          </button>
        </header>
        <div
          ref={feed}
          className="conversation-feed"
          aria-label="Conversation et cahier des charges"
          onScroll={() => {
            const element = feed.current;
            if (element) {
              followLatest.current =
                element.scrollHeight - element.scrollTop - element.clientHeight < 40;
            }
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
