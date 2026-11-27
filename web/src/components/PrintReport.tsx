import { memo } from "react";
import type { ChainResult } from "../lib/chainCheck";
import { entryText, isSetupChanged, verdictWord } from "../lib/entryText";
import type { DisplayEntry } from "../lib/synthesiseUndeclared";
import { ChainStatus } from "./ChainStatus";

type Props = {
  sessionId: string;
  /** "turn 2 of 3" when the session has several turns, else null. */
  turn: string | null;
  title: string;
  chain: ChainResult | null;
  /** The session's lines, including the made-up "not mentioned" lines. */
  lines: DisplayEntry[];
  /** The fingerprint sentence for the whole record. */
  fingerprint: string;
};

/**
 * The clean evidence report, visible only when printing ("Tear off report").
 * It lists everything, whether or not the replay has reached it, and ends
 * with the overall verdict.
 */
export const PrintReport = memo(function PrintReport({ sessionId, turn, title, chain, lines, fingerprint }: Props) {
  const verdictLines = lines.filter(
    (l) => l.kind === "verdict" && l.data.kind_detail !== "statement_overall",
  );
  const notMentioned = lines.filter((l) => l.kind === "undeclared");
  const overall = lines.filter(
    (l) => l.kind === "verdict" && l.data.kind_detail === "statement_overall",
  );
  const between = lines.filter((l) => l.kind === "witness" && l.data.event === "between_turns");
  const setup = lines.filter(isSetupChanged);
  const last = overall[overall.length - 1];
  const silent = last !== undefined && last.data.verdict === "NO_STATEMENT";

  return (
    <section className="print-report" aria-hidden="true">
      <h1>Paper Trail: evidence report</h1>
      <p>Session: {sessionId}</p>
      {turn && <p>Turn: {turn.replace(/^turn /, "")}</p>}
      <p>Statement: {title}</p>
      <p className="print-chain-status">
        {chain ? <ChainStatus ok={chain.ok} brokenAt={chain.ok ? null : chain.brokenAt} /> : "Paper not checked"}
      </p>
      {setup.map((l) => (
        <p key={l.seq} className="print-setup">
          {entryText(l)}
        </p>
      ))}
      {between.map((l) => (
        <p key={l.seq} className="print-between">
          {entryText(l)}
        </p>
      ))}
      {verdictLines.map((l) => (
        <p key={l.seq} className="print-verdict-line">
          {verdictWord(l.data.verdict)}: {entryText(l)}
        </p>
      ))}
      {notMentioned.length > 0 && <p className="print-heading">
          {silent ? "Changes the witness saw:" : "Not mentioned in the statement:"}
        </p>}
      {notMentioned.map((l) => (
        <p key={l.seq} className="print-undeclared">
          {entryText(l)}
        </p>
      ))}
      <p className="print-verdict-line print-verdict-line--overall">
        {last ? `${entryText(last)} (${verdictWord(last.data.verdict)})` : "Overall: not checked yet."}
      </p>
      <p className="print-fingerprint">{fingerprint}</p>
    </section>
  );
});
