/**
 * Canonical JSON, matching Python's
 *   json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
 *
 * Keys are sorted, there is no spacing, and strings go through JSON.stringify
 * with no post-processing. tests/fixtures/hash_fixture.json (quotes, backslash,
 * newline, tab, U+0001, an emoji and an accented letter) is the contract: the
 * Python and browser hashes of that entry must be identical.
 */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalJson).join(",") + "]";
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return (
    "{" + keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(record[k])).join(",") + "}"
  );
}
