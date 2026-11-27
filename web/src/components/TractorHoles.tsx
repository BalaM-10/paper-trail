/** The feed holes down one edge of the paper. Drawn in CSS; purely decorative. */
export function TractorHoles({ side }: { side: "left" | "right" }) {
  return <div className={`tractor-holes tractor-holes--${side}`} aria-hidden="true" />;
}
