import { useLayoutEffect, useRef, useState } from "react";

/**
 * Which line (by position) the print head has just finished, or -1.
 *
 * Only that line animates. It is cleared again after `ms`, and whenever the
 * paper tears or mends, so lines that are merely moved from one piece of paper
 * to the other (and so rebuilt by React) never print a second time.
 */
export function useFreshLine(cursor: number, torn: boolean, ms = 1200): number {
  const [fresh, setFresh] = useState(-1);
  const seen = useRef({ cursor, torn });
  // True only in the render where the paper tears or mends.
  const flipped = seen.current.torn !== torn;

  // Layout effect: the class must be on the line before the first paint, or a
  // finished line would flash for a frame before it starts to print.
  useLayoutEffect(() => {
    const was = seen.current;
    seen.current = { cursor, torn };
    if (was.torn !== torn || cursor <= was.cursor) {
      setFresh(-1);
      return;
    }
    setFresh(cursor - 1);
    const id = setTimeout(() => setFresh(-1), ms);
    return () => clearTimeout(id);
  }, [cursor, torn, ms]);

  return flipped ? -1 : fresh;
}
