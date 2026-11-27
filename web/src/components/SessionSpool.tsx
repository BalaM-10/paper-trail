import { useState } from "react";
import type { SessionMeta } from "../lib/sessionMeta";
import type { Source } from "../hooks/useEntries";
import { Stamp } from "./Stamp";

type Props = {
  meta: SessionMeta;
  selected: boolean;
  source: Source;
  onSelect: (sessionId: string) => void;
  /** Called after a statement was checked, so the records can be re-read. */
  onVerified: () => void;
};

/** One session, drawn as a spool of paper, titled by what the agent said it did. */
export function SessionSpool({ meta, selected, source, onSelect, onVerified }: Props) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  // Only the running API can check a statement; the static demo is already checked.
  const canCheck =
    source === "api" && meta.hasUnverifiedStatement && meta.statementIndex !== null;

  async function check() {
    setBusy(true);
    setFailed(false);
    try {
      const response = await fetch(
        `/api/verify/${encodeURIComponent(meta.sessionId)}/${meta.statementIndex}`,
        { method: "POST" },
      );
      if (!response.ok) throw new Error(`status ${response.status}`);
      onVerified();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="spool-item">
      <button
        type="button"
        className="spool"
        aria-pressed={selected}
        onClick={() => onSelect(meta.sessionId)}
      >
        <span className="spool__roll" aria-hidden="true">
          <span className="spool__core" />
        </span>
        <span className="spool__body">
          <span className="spool__title">{meta.title}</span>
          <span className="spool__meta">
            {meta.sessionId.slice(0, 8)} · {meta.date}
          </span>
          {meta.overallVerdict && <Stamp verdict={meta.overallVerdict} />}
        </span>
      </button>
      {canCheck && (
        <button type="button" className="btn btn--small" onClick={check} disabled={busy}>
          {busy ? "Checking…" : "Check this statement"}
        </button>
      )}
      {failed && (
        <span className="spool__error" role="alert">
          That check didn't work. Is the local API still running?
        </span>
      )}
    </li>
  );
}
