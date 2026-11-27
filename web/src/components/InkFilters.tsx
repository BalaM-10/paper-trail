/**
 * Shared SVG filters, defined once for the whole page and used from CSS:
 *   rough-ink   rubber stamps: wobbly edges and a few patches of missing ink
 *   marker-ink  the red marker: a gentler wobble
 * The element is invisible and takes no room.
 */
export function InkFilters() {
  return (
    <svg
      width="0"
      height="0"
      focusable="false"
      aria-hidden="true"
      style={{ position: "absolute", width: 0, height: 0, overflow: "hidden" }}
    >
      <defs>
        <filter id="rough-ink" x="-8%" y="-15%" width="116%" height="130%">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" result="edge" />
          <feDisplacementMap in="SourceGraphic" in2="edge" scale="3.2" xChannelSelector="R" yChannelSelector="G" result="rough" />
          <feTurbulence type="fractalNoise" baseFrequency="0.55" numOctaves="2" seed="3" result="grain" />
          <feColorMatrix
            in="grain"
            type="matrix"
            values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  14 0 0 0 -4.3"
            result="inked"
          />
          <feComposite in="rough" in2="inked" operator="in" />
        </filter>
        <filter id="marker-ink" x="-40%" y="-20%" width="180%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.07" numOctaves="2" seed="11" result="wobble" />
          <feDisplacementMap in="SourceGraphic" in2="wobble" scale="2.4" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
  );
}
