import type { ReactNode } from "react";
import { jumpToLine } from "../lib/jumpToLine";

/**
 * A change the witness saw that the statement never mentioned, circled in red
 * marker. The ring is a loose hand-drawn path whose end overshoots its start.
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
        <path d="M 14 9 C 30 2, 70 1, 88 7 C 99 12, 99 28, 86 33 C 68 40, 30 39, 13 32 C 2 27, 1 13, 14 8 C 20 5, 30 3, 40 3" />
      </svg>
    </button>
  );
}
