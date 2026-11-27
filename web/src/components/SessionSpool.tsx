import { useState } from "react";
import { turnLabel, type Roll } from "../lib/rolls";
import type { Source } from "../hooks/useEntries";
import { Stamp } from "./Stamp";

type Props = {
  meta: Roll;
  selected: boolean;
  source: Source;
  onSelect: (key: string) => void;
  /** Called after a statement was checked, so the records can be re-read. */
  onVerified: () => void;
};

/** One turn of a session, drawn as a spool of paper, titled by what the agent said it did. */
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
        onClick={() => onSelect(meta.key)}
      >
        <span className="spool__roll" aria-hidden="true">
          <span className="spool__core" />
        </span>
        <span className="spool__body">
          {/* Three lines at most on the roll. The whole title stays in the text (so it is the
              button's name) and is the tooltip. */}
          <span className="spool__title" title={meta.title}>
            {meta.title}
          </span>
          <span className="spool__meta">
            {meta.sessionId.slice(0, 8)} ·{" "}
            {turnLabel(meta) && (
              <>
                <span className="nobreak">{turnLabel(meta)}</span> ·{" "}
              </>
            )}
            <span className="nobreak">{meta.date}</span>
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
