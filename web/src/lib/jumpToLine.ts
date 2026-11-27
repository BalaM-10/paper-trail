/**
 * Bring a printed line into view and give it keyboard focus, so a visitor (and
 * a screen reader) lands on it. Returns false if that line is not on the page.
 */
export function jumpToLine(seq: number): boolean {
  const el = document.getElementById(`line-${seq}`);
  if (!el) return false;
  const reduceMotion =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView?.({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
  el.focus?.({ preventScroll: true });
  return true;
}
