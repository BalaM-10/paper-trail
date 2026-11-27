import { buildTotals, totalsText } from "../lib/buildTotals";
import type { Entry } from "../lib/chainCheck";

/** The numbers behind the build record, in plain words. */
export function BuildTotals({ entries }: { entries: Entry[] }) {
  return <p className="build-totals">{totalsText(buildTotals(entries))}</p>;
}