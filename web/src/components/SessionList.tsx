import type { ReactNode } from "react";
import type { Source } from "../hooks/useEntries";
import type { SessionMeta } from "../lib/sessionMeta";
import { SessionSpool } from "./SessionSpool";

type Props = {
  sessions: SessionMeta[];
  selected: string | null;
  source: Source;
  onSelect: (sessionId: string) => void;
  onVerified: () => void;
  /** Shown above the rolls (the switch between records, and its totals). */
  top?: ReactNode;
};

/** The rolls of paper: a column beside the printer on wide screens, above it on narrow ones. */
export function SessionList({ sessions, selected, source, onSelect, onVerified, top }: Props) {
  return (
    <nav className="session-list" aria-label="Sessions">
      {top}
      <p className="session-list__caption" aria-hidden="true">
        Rolls of paper
      </p>
      <ul>
        {sessions.map((meta) => (
          <SessionSpool
            key={meta.sessionId}
            meta={meta}
            selected={meta.sessionId === selected}
            source={source}
            onSelect={onSelect}
            onVerified={onVerified}
          />
        ))}
      </ul>
    </nav>
  );
}
