import { verdictWord } from "../lib/entryText";

export type StampSize = "small" | "medium" | "huge";

const VERDICT_CLASS: Record<string, string> = {
  SUPPORTED: "stamp--supported",
  CONTRADICTED: "stamp--contradicted",
  UNVERIFIED: "stamp--unverified",
  NO_STATEMENT: "stamp--no-statement",
};

/**
 * A rubber-stamp verdict. Always carries the word, never colour alone.
 * Small sits on a session roll, medium on a verdict line, huge is the overall
 * verdict and the biggest thing on the paper.
 */
export function Stamp({ verdict, size = "small" }: { verdict: string; size?: StampSize }) {
  return (
    <span className={`stamp ${VERDICT_CLASS[verdict] ?? ""} stamp--${size}`.replace(/\s+/g, " ")}>
      {verdictWord(verdict)}
    </span>
  );
}
