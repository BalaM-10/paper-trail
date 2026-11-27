import type { ReactNode } from "react";
import { jumpToLine } from "../lib/jumpToLine";

/**
 * A change the witness saw that the statement never mentioned, circled in red
 * marker. The ring is a loose hand-drawn rounded loop whose end overshoots its start.
 * Activating it jumps to the witness line that proves it.
 */
export function UndeclaredCircle({
  witnessSeq,
  children,
}: {
  witnessSeq: number;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className="undeclared-circle"
      title={`Go to line ${witnessSeq}, where the witness saw it`}
      onClick={() => jumpToLine(witnessSeq)}
    >
      <span className="undeclared-circle__text">{children}</span>
      <svg
        className="undeclared-circle__ring"
        viewBox="0 0 100 40"
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M 2 12 C 1.5 7, 2.5 3.5, 6 2.5 C 35 0.5, 65 2, 93 1.5 C 97 1.5, 98.5 4, 98.5 9 C 99 18, 98.5 29, 98 34 C 97.5 37, 96 38.5, 93 38.5 C 65 39.5, 35 38.5, 7 38.5 C 3.5 38.5, 1.5 35, 1.5 31 C 1.5 24, 1.5 18, 2.5 13 C 3.2 8, 4.5 4.5, 12 2.8" />
      </svg>
    </button>
  );
}
