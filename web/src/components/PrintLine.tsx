import { memo, type CSSProperties, type ReactNode } from "react";
import { entryText } from "../lib/entryText";
import { inkFor } from "../lib/ink";
import type { DisplayEntry } from "../lib/synthesiseUndeclared";
import { MarkerArrow } from "./MarkerArrow";
import { Stamp } from "./Stamp";
import { UndeclaredCircle } from "./UndeclaredCircle";

type Props = {
  entry: DisplayEntry;
  /** Printed yet? Unprinted lines are blank paper. */
  visible: boolean;
  /** The next line to be printed. */
  isNext: boolean;
  /** Picked as the line to tamper with. */
  selected: boolean;
  /** The line the print head has just finished. Only this one animates. */
  fresh: boolean;
  onSelect: (seq: number) => void;
};

function isOverall(entry: DisplayEntry): boolean {
  return entry.kind === "verdict" && entry.data.kind_detail === "statement_overall";
}

function content(entry: DisplayEntry): ReactNode {
  if (entry.kind === "undeclared") {
    return (
      <UndeclaredCircle witnessSeq={entry.data.witnessSeq as number}>
        {entryText(entry)}
      </UndeclaredCircle>
    );
  }
  return entryText(entry);
}

/**
 * One line of the printout. Memoised: with a couple of thousand lines on the
 * paper, a step or a pick must redraw only the lines whose own props changed.
 */
export const PrintLine = memo(function PrintLine({ entry, visible, isNext, selected, fresh, onSelect }: Props) {
  const synthetic = entry._synthetic === true;
  const overall = isOverall(entry);
  const id = synthetic ? undefined : `line-${entry.seq}`;

  if (!visible) {
    return (
      <li
        id={id}
        className={`print-line print-line--pending${overall ? " print-line--overall" : ""}${isNext ? " print-line--next" : ""}`}
        aria-hidden="true"
      >
        <span className="print-line__no" />
        <span className="print-line__text" />
      </li>
    );
  }

  const verdict = entry.kind === "verdict" ? String(entry.data.verdict) : null;
  const between = entry.kind === "witness" && entry.data.event === "between_turns";
  const classes = [
    "print-line",
    between ? "print-line--between" : "",
    verdict ? "print-line--stamped" : "",
    overall ? "print-line--overall" : "",
    synthetic ? "print-line--note" : "",
    fresh ? "print-line--fresh" : "",
    selected ? "print-line--tamper-target" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // Each line is printed a touch lighter or darker than its neighbours.
  const style = { "--density": String(inkFor(entry.seq)) } as CSSProperties;

  return (
    <li id={id} tabIndex={-1} className={classes} style={style}>
      {synthetic && <MarkerArrow targetSeq={entry.data.witnessSeq as number} />}
      {synthetic ? (
        <span className="print-line__no print-line__no--note" aria-hidden="true">
          !
        </span>
      ) : (
        <button
          type="button"
          className="print-line__no"
          aria-pressed={selected}
          aria-label={`Line ${entry.seq}: ${selected ? "picked" : "pick"} to tamper with`}
          onClick={() => onSelect(entry.seq)}
        >
          {entry.seq}
        </button>
      )}
      <span
        className="print-line__text"
        onClick={synthetic ? undefined : () => onSelect(entry.seq)}
      >
        {content(entry)}
      </span>
      {verdict && <Stamp verdict={verdict} size={overall ? "huge" : "medium"} />}
    </li>
  );
});
