import type { ReactNode } from "react";

export type Light = "off" | "ready" | "busy" | "error";

type Props = {
  /** The status light. Decorative: the display says the same in words. */
  light: Light;
  /** What the little display shows. */
  display: ReactNode;
  /** The keys. */
  children: ReactNode;
};

/**
 * The printer: a drawn body, a front panel with a status light and a small
 * display, and a slot at the bottom that the paper comes out of.
 */
export function Printer({ light, display, children }: Props) {
  return (
    <div className="printer" data-light={light}>
      <div className="printer__lid" aria-hidden="true">
        <span className="printer__vents" />
        <span className="printer__brand">PAPER TRAIL PT-1</span>
      </div>
      <div className="printer__panel">
        <div className="printer__readout">
          <span className={`led led--${light}`} aria-hidden="true" />
          <div className="lcd">{display}</div>
        </div>
        <div className="printer__keys">{children}</div>
      </div>
      <div className="printer__slot" aria-hidden="true" />
    </div>
  );
}
