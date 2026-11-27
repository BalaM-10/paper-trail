import type { ReactNode } from "react";
import type { Source } from "../hooks/useEntries";
import type { Roll } from "../lib/rolls";
import { SessionSpool } from "./SessionSpool";

type Props = {
  /** One per turn of each session. */
  sessions: Roll[];
  selected: string | null;
  source: Source;
  /** Called with the roll's key. */
  onSelect: (key: string) => void;
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
            key={meta.key}
            meta={meta}
            selected={meta.key === selected}
            source={source}
            onSelect={onSelect}
            onVerified={onVerified}
          />
        ))}
      </ul>
    </nav>
  );
}
