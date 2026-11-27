import type { ReactNode } from "react";
import { TractorHoles } from "./TractorHoles";

function Perforation() {
  return (
    <div className="session-break" role="separator" aria-label="Tear here">
      <span aria-hidden="true">- - - - - - - - - - - - tear here - - - - - - - - - - - -</span>
    </div>
  );
}

type PieceProps = {
  kind: "whole" | "upper" | "lower";
  /** A perforation across the top / bottom of this piece. */
  top: boolean;
  bottom: boolean;
  children: ReactNode;
};

/** One sheet of paper: feed holes down both edges, lines in between. */
function Piece({ kind, top, bottom, children }: PieceProps) {
  return (
    <div className={`paper-piece paper-piece--${kind}`}>
      <div className="paper-piece__sheet">
        <TractorHoles side="left" />
        <TractorHoles side="right" />
        {top && <Perforation />}
        <ol className="print-lines">{children}</ol>
        {bottom && <Perforation />}
      </div>
    </div>
  );
}

type Props = {
  /** Every line when the paper is whole; the lines above the tear when torn. */
  upper: ReactNode;
  /** The lines from the broken one down. Only used when torn. */
  lower?: ReactNode;
  torn: boolean;
};

/**
 * The paper as it comes out of the printer. When it is torn it really splits:
 * two pieces with jagged edges, a gap, the lower piece shifted and turned.
 * The first piece keeps its place in the tree either way, so the lines above
 * the tear are not rebuilt (and so never print again) when it tears or mends.
 */
export function PaperRoll({ upper, lower, torn }: Props) {
  return (
    <section className={`paper-roll${torn ? " paper-roll--torn" : " paper-roll--whole"}`} role="region" aria-label="Printout">
      <Piece kind={torn ? "upper" : "whole"} top bottom={!torn}>
        {upper}
      </Piece>
      {torn && <div className="paper-gap" role="img" aria-label="Paper torn here" />}
      {torn && (
        <Piece kind="lower" top={false} bottom>
          {lower}
        </Piece>
      )}
    </section>
  );
}
