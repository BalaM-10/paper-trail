import demoLedgerRaw from "../../public/demo/ledger.jsonl?raw";
import { parseJsonl } from "../hooks/useEntries";
import type { Entry } from "../lib/chainCheck";

/** The generated demo ledger, as text and as parsed records. */
export const demoText: string = demoLedgerRaw;
export const demoEntries: Entry[] = parseJsonl(demoLedgerRaw);

export const SESSION_A = "demo-session-a";
export const SESSION_B = "demo-session-b";
/** The session where the agent changed files and wrote no statement. */
export const SESSION_C = "demo-session-c";

export function sessionOf(id: string): Entry[] {
  return demoEntries.filter((e) => e.session_id === id);
}

/** The witness line that proves what happened in a session. */
export function witnessStopSeq(id: string): number {
  return sessionOf(id).find((e) => e.kind === "witness" && e.data.event === "stop")!.seq;
}

/** The cleanup command line of a session (what Tamper picks by default). */
export function commandSeq(id: string): number {
  return sessionOf(id).find((e) => e.kind === "tool" && e.data.tool_name === "execute_pwsh")!.seq;
}

export function ok(body: string): Response {
  return new Response(body, { status: 200 });
}

/** Words that must never reach the screen (plain-language rule). */
export const BANNED = /\b(hash|chain|ledger|entry|entries|seq|jsonl|sha-?256|canonical|hex)\b/i;

/** All text a visitor, or a screen reader, could meet: text, labels and titles. */
export function visibleLanguage(root: HTMLElement = document.body): string {
  const parts = [root.textContent ?? ""];
  root.querySelectorAll("[aria-label],[title],[alt],[placeholder]").forEach((el) => {
    for (const attr of ["aria-label", "title", "alt", "placeholder"]) {
      const value = el.getAttribute(attr);
      if (value) parts.push(value);
    }
  });
  return parts.join("\n");
}
