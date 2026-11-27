import type { Entry } from "./chainCheck";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** "2026-03-01T09:00:00Z" as "1 March 2026". The records are in UTC, so the date is read as written. */
export function plainDate(ts: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(ts);
  if (!m) return null;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return null;
  return `${Number(m[3])} ${MONTHS[month - 1]} ${m[1]}`;
}

/**
 * Which dates the record covers, from its first and last line, in plain words.
 * `partial` says the published record is only part of the build (earlier records
 * were put away); null means nobody said, and the dates are all that is claimed.
 */
export function coverageText(entries: Entry[], partial: boolean | null): string | null {
  if (entries.length === 0) return null;
  const first = plainDate(entries[0].ts);
  const last = plainDate(entries[entries.length - 1].ts);
  if (!first || !last) return null;
  const oneDay = first === last;
  if (partial) {
    const when = oneDay ? first : `from ${first} to ${last}`;
    return `This record covers only part of the build: ${when}. Earlier work was archived and is not shown here.`;
  }
  return oneDay ? `This record is from ${first}.` : `This record runs from ${first} to ${last}.`;
}