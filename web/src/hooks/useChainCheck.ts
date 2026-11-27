import { useEffect, useState } from "react";
import { checkChain, type ChainResult, type Entry } from "../lib/chainCheck";

export type ChainCheckState = {
  /** null while checking, or when there is nothing to check. */
  result: ChainResult | null;
  /** True when this browser/address cannot run the check at all. */
  unavailable: boolean;
};

/** Re-checks the whole paper in the browser whenever the records change. */
export function useChainCheck(entries: Entry[]): ChainCheckState {
  const [state, setState] = useState<ChainCheckState>({ result: null, unavailable: false });

  useEffect(() => {
    if (entries.length === 0) {
      setState({ result: null, unavailable: false });
      return;
    }
    let cancelled = false; // a newer set of records replaced this one
    checkChain(entries)
      .then((result) => {
        if (!cancelled) setState({ result, unavailable: false });
      })
      .catch(() => {
        // Web Crypto is missing, for example on a plain-http address.
        if (!cancelled) setState({ result: null, unavailable: true });
      });
    return () => {
      cancelled = true;
    };
  }, [entries]);

  return state;
}
