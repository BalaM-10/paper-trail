/** The faintest a printed line ever gets (1 is full black ink). */
export const MIN_INK = 0.82;

/**
 * How dark the ink is for one printed line: a little different from line to
 * line, as on a real printer, but always the same for the same line number so
 * the paper never shimmers when it is redrawn.
 */
export function inkFor(seq: number): number {
  const steps = 19; // 0.82, 0.83 ... 1.00
  const n = Number.isFinite(seq) ? Math.abs(Math.trunc(seq)) % steps : 0;
  const scrambled = (n * 7 + 3) % steps; // neighbouring lines do not step smoothly
  return Math.round((MIN_INK + scrambled / 100) * 100) / 100;
}
