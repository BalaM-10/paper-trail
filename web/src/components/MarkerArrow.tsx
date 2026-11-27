import { useLayoutEffect, useRef, useState } from "react";

/** Shortest arrow worth drawing, in pixels. */
const MIN_LENGTH = 24;

/**
 * A hand-drawn red arrow in the margin, from the line it is placed in up to
 * the witness line that proves it. It must be the child of that line's <li>.
 *
 * Its length is measured from the two lines' positions, and measured again
 * when the window or the paper changes size (a tear moves things). Where there
 * is no layout, or no such line, nothing is drawn.
 */
export function MarkerArrow({ targetSeq }: { targetSeq: number }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const [length, setLength] = useState(0);

  useLayoutEffect(() => {
    const line = anchor.current?.parentElement;
    if (!line) return;

    const measure = () => {
      const target = document.getElementById(`line-${targetSeq}`);
      if (!target) return setLength(0);
      const here = line.getBoundingClientRect();
      const there = target.getBoundingClientRect();
      const distance = here.top + here.height / 2 - (there.top + there.height / 2);
      setLength(distance >= MIN_LENGTH ? Math.round(distance) : 0);
    };

    measure();
    window.addEventListener("resize", measure);
    const paper = line.closest(".paper-roll");
    const observer =
      typeof ResizeObserver !== "undefined" && paper ? new ResizeObserver(measure) : null;
    if (observer && paper) observer.observe(paper);
    return () => {
      window.removeEventListener("resize", measure);
      observer?.disconnect();
    };
  }, [targetSeq]);

  const h = length;
  return (
    <span ref={anchor} className="marker-arrow" style={{ height: h }} aria-hidden="true">
      {h > 0 && (
        <svg width="24" height={h} viewBox={`0 0 24 ${h}`} focusable="false">
          {/* a wobbly stem, drawn upward... */}
          <path
            d={`M 12 ${h} C 4 ${h * 0.8}, 20 ${h * 0.6}, 11 ${h * 0.42} S 15 ${h * 0.14}, 12 9`}
            fill="none"
            strokeWidth="3"
            strokeLinecap="round"
          />
          {/* ...with a head that points up at the witness line */}
          <path d="M 4 18 L 12 4 L 20 17" fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </span>
  );
}
