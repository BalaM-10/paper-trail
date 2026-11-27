/** Shown only while the page is reading from the running local API. */
export function LiveIndicator() {
  return (
    <span className="live-indicator" title="Live: new lines print as they arrive">
      LIVE
    </span>
  );
}
