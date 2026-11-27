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
        <path d="M 2 15 C 1.5 8, 3 4, 6 3.5 C 35 1.5, 65 2.5, 93 2.5 C 97 2.5, 98.5 6, 98.5 13 C 99 21, 98.5 29, 98 33 C 97.5 36, 96 37, 93 37 C 65 38, 35 37, 7 37 C 3.5 37, 1.5 34, 1.5 28 C 1.5 22, 1.5 16, 2.5 11 C 3.5 8, 5 5.5, 12 4" />
      </svg>
    </button>
  );
}
