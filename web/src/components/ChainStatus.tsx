/** Whether the paper is still as it was printed, in plain words. */
export function ChainStatus({ ok, brokenAt }: { ok: boolean; brokenAt?: number | null }) {
  if (ok) {
    return <span className="chain-status chain-status--ok">Paper intact</span>;
  }
  return (
    <span className="chain-status chain-status--broken">Paper torn at line {brokenAt}</span>
  );
}
