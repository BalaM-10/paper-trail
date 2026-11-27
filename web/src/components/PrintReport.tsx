import type { ChainResult } from "../lib/chainCheck";
import { entryText } from "../lib/entryText";
import type { DisplayEntry } from "../lib/synthesiseUndeclared";
import { ChainStatus } from "./ChainStatus";

type Props = {
  sessionId: string;
  title: string;
  chain: ChainResult | null;
  /** The session's lines, including the made-up "not mentioned" lines. */
  lines: DisplayEntry[];
};

/**
 * The clean evidence report, visible only when printing ("Tear off report").
 * It lists everything, whether or not the replay has reached it, and ends
 * with the overall verdict.
 */
export function PrintReport({ sessionId, title, chain, lines }: Props) {
  const verdictLines = lines.filter(
    (l) => l.kind === "verdict" && l.data.kind_detail !== "statement_overall",
  );
  const notMentioned = lines.filter((l) => l.kind === "undeclared");
  const overall = lines.filter(
    (l) => l.kind === "verdict" && l.data.kind_detail === "statement_overall",
  );
  const last = overall[overall.length - 1];

  return (
    <section className="print-report" aria-hidden="true">
      <h1>Paper Trail: evidence report</h1>
      <p>Session: {sessionId}</p>
      <p>Statement: {title}</p>
      <p className="print-chain-status">
        {chain ? <ChainStatus ok={chain.ok} brokenAt={chain.ok ? null : chain.brokenAt} /> : "Paper not checked"}
      </p>
      {verdictLines.map((l) => (
        <p key={l.seq} className="print-verdict-line">
          {String(l.data.verdict)}: {entryText(l)}
        </p>
      ))}
      {notMentioned.length > 0 && <p className="print-heading">Not mentioned in the statement:</p>}
      {notMentioned.map((l) => (
        <p key={l.seq} className="print-undeclared">
          {entryText(l)}
        </p>
      ))}
      <p className="print-verdict-line print-verdict-line--overall">
        {last ? `${entryText(last)} (${String(last.data.verdict)})` : "Overall: not checked yet."}
      </p>
    </section>
  );
}
