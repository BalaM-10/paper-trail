import type { Entry } from "./chainCheck";

/** Verbs for known tools. Anything else is "used a tool". */
const TOOL_VERB: Record<string, string> = {
  read_file: "read",
  fs_write: "wrote",
  str_replace: "edited",
};

/** What the agent said it did, by the kind of claim in its statement. */
const CLAIM_VERB: Record<string, string> = {
  files_created: "created",
  files_modified: "changed",
  files_deleted: "deleted",
  files_read: "read",
};

export type UndeclaredItem = { path: string; change: string };

/** Shown for a change the witness saw but the statement never mentioned. */
export function undeclaredText(item: UndeclaredItem): string {
  return `Witness saw ${item.path} ${item.change}. The agent never mentioned it.`;
}

/** Evidence line numbers, for example "(line 4)" or "(lines 2, 5)". Empty if none. */
export function evidenceRef(evidence: unknown): string {
  const lines = Array.isArray(evidence) ? (evidence as number[]) : [];
  if (lines.length === 0) return "";
  return `(${lines.length === 1 ? "line" : "lines"} ${lines.join(", ")})`;
}

/**
 * One verdict as a sentence, for example
 * "Agent said it deleted a.txt. Witness agrees (line 11)."
 * Reading a file is checked against the record of tool calls, not the witness.
 */
export function verdictSentence(d: Record<string, unknown>): string {
  const verb = CLAIM_VERB[String(d.claim)] ?? "touched";
  const said = `Agent said it ${verb} ${String(d.path)}.`;
  const ref = evidenceRef(d.evidence_seq);
  const where = ref ? ` ${ref}` : "";
  switch (d.verdict) {
    case "SUPPORTED":
      return `${said} ${d.claim === "files_read" ? "The record agrees" : "Witness agrees"}${where}.`;
    case "CONTRADICTED":
      return `${said} Witness says otherwise${where}.`;
    default:
      return `${said} There is no evidence either way.`;
  }
}

/**
 * What changed between two turns, outside the agent. After a turn that never
 * stopped, some of it may be the agent's, and the line says so.
 */
export function betweenTurnsText(d: Record<string, unknown>): string {
  const diff = (d.diff ?? {}) as Record<string, unknown>;
  const groups: [string, string[]][] = [
    ["created", listOf(diff.created)],
    ["changed", listOf(diff.modified)],
    ["deleted", listOf(diff.deleted)],
  ];
  const listing =
    groups
      .filter(([, files]) => files.length > 0)
      .map(([label, files]) => `${label} ${files.join(", ")}`)
      .join("; ") || "no changes";
  return d.unfinished === true
    ? `Since the unfinished turn before this one: ${listing}. The agent may have made some of these changes.`
    : `Between turns, outside the agent: ${listing}.`;
}

/** The last line of a checked statement. */
export function overallSentence(verdict: unknown): string {
  switch (verdict) {
    case "SUPPORTED":
      return "Overall: the statement matches the evidence.";
    case "CONTRADICTED":
      return "Overall: the statement does not match the evidence.";
    case "NO_STATEMENT":
      return "Overall: the agent changed files and said nothing.";
    default:
      return "Overall: some of the statement could not be checked.";
  }
}

/** The word printed on a stamp. NO_STATEMENT is two words. */
export function verdictWord(verdict: unknown): string {
  return String(verdict).replace(/_/g, " ");
}

/** The fingerprint of the whole record and how many lines it has. */
export function fingerprintText(entries: { hash: string }[]): string {
  const n = entries.length;
  const tip = n > 0 ? entries[n - 1].hash : "none yet";
  return `Fingerprint of the record: ${tip} (${n} ${n === 1 ? "line" : "lines"})`;
}

function listOf(value: unknown): string[] {
  return Array.isArray(value) ? (value as string[]) : [];
}

/**
 * The line for a shell command. Twin of command_sentence in papertrail/spool.py;
 * tests/fixtures/sentences.json holds the cases for both.
 * The recorder keeps a command of more than 2000 characters only as
 * { size: bytes, sha256 }, so its text is not in the record and cannot be shown.
 */
export function commandSentence(command: unknown): string {
  if (typeof command === "string" && command) return `Agent ran the command: ${command.slice(0, 80)}.`;
  if (command !== null && typeof command === "object" && !Array.isArray(command)) {
    const { size, sha256 } = command as Record<string, unknown>;
    if (typeof size === "number" && Number.isInteger(size) && size >= 0 && typeof sha256 === "string") {
      return `Agent ran a long command. The record keeps its size, ${size} ${size === 1 ? "byte" : "bytes"}, not its text.`;
    }
  }
  return "Agent ran a command.";
}

/** Plain-language description of one record. */
export function entryText(entry: Entry): string {
  const d = entry.data;

  switch (entry.kind) {
    case "witness": {
      if (d.event === "start") return "Witness took a snapshot of the project.";
      if (d.event === "turn") return "Witness took a snapshot of the project at the start of this turn.";
      if (d.event === "between_turns") return betweenTurnsText(d);
      const diff = (d.diff ?? {}) as Record<string, unknown>;
      const groups: [string, string[]][] = [
        ["Created", listOf(diff.created)],
        ["Changed", listOf(diff.modified)],
        ["Deleted", listOf(diff.deleted)],
      ];
      const parts = groups
        .filter(([, files]) => files.length > 0)
        .map(([label, files]) => `${label}: ${files.join(", ")}.`);
      const summary = parts.length > 0 ? parts.join(" ") : "No changes.";
      const since = String(d.baseline ?? "").startsWith("turn:")
        ? "the snapshot from the start of this turn"
        : "the earlier snapshot";
      return `Witness compared the project to ${since}. ${summary}`;
    }

    case "tool": {
      const name = String(d.tool_name ?? "unknown");
      const input =
        d.tool_input !== null && typeof d.tool_input === "object" && !Array.isArray(d.tool_input)
          ? (d.tool_input as Record<string, unknown>)
          : {};
      if (name === "execute_pwsh") return commandSentence(input.command);
      const verb = TOOL_VERB[name];
      if (verb) return `Agent ${verb} ${typeof input.path === "string" && input.path ? input.path : "a file"}.`;
      return `Agent used a tool: ${name}.`;
    }

    case "statement":
      return `Agent stated: ${String(d.summary ?? "")}`;

    case "verdict":
      return d.kind_detail === "statement_overall" ? overallSentence(d.verdict) : verdictSentence(d);

    case "undeclared":
      return undeclaredText(d as unknown as UndeclaredItem);

    case "error":
      return `Something went wrong: ${String(d.error ?? "unknown error")}.`;

    default:
      return `Record: ${entry.kind}.`;
  }
}
