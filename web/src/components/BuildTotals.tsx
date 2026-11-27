import { buildTotals, totalsText } from "../lib/buildTotals";
import type { Entry } from "../lib/chainCheck";
import { coverageText } from "../lib/coverage";

/**
 * The numbers behind the build record, in plain words, and which dates it covers.
 * `partial` is what the exporter said: true when earlier work was archived.
 */
export function BuildTotals({ entries, partial = null }: { entries: Entry[]; partial?: boolean | null }) {
  const coverage = coverageText(entries, partial);
  return (
    <div className="build-totals">
      <p>{totalsText(buildTotals(entries))}</p>
      {coverage && <p className="build-totals__coverage">{coverage}</p>}
    </div>
  );
}