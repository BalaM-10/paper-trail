import { NOTHING_TO_FLAG, hiddenText } from "../lib/exceptions";

/**
 * Printed at the top of a roll while EXCEPTIONS ONLY is on: how many lines are hidden,
 * and, when nothing is left, that there is nothing to flag. These are notes about the
 * page, not lines of the record, so they carry no number and do not wait for the replay.
 */
export function ExceptionNotes({ hidden, nothingToFlag }: { hidden: number; nothingToFlag: boolean }) {
  return (
    <>
      <li className="print-line print-line--filter-note">
        <span className="print-line__no" aria-hidden="true" />
        <span className="print-line__text">{hiddenText(hidden)}</span>
      </li>
      {nothingToFlag && (
        <li className="print-line print-line--filter-note print-line--nothing">
          <span className="print-line__no" aria-hidden="true" />
          <span className="print-line__text">{NOTHING_TO_FLAG}</span>
        </li>
      )}
    </>
  );
}
