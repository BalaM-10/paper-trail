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

/** The last line of a checked statement. */
export function overallSentence(verdict: unknown): string {
  switch (verdict) {
    case "SUPPORTED":
      return "Overall: the statement matches the evidence.";
    case "CONTRADICTED":
      return "Overall: the statement does not match the evidence.";
    default:
      return "Overall: some of the statement could not be checked.";
  }
}

function listOf(value: unknown): string[] {
  return Array.isArray(value) ? (value as string[]) : [];
}

/** Plain-language description of one record. */
export function entryText(entry: Entry): string {
  const d = entry.data;

  switch (entry.kind) {
    case "witness": {
      if (d.event === "start") return "Witness took a snapshot of the project.";
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
      return `Witness compared the project to the earlier snapshot. ${summary}`;
    }

    case "tool": {
      const name = String(d.tool_name ?? "unknown");
      const input = (d.tool_input ?? {}) as Record<string, unknown>;
      if (name === "execute_pwsh") {
        return `Agent ran the command: ${String(input.command ?? "").slice(0, 80)}.`;
      }
      const verb = TOOL_VERB[name];
      if (verb) return `Agent ${verb} ${String(input.path ?? "a file")}.`;
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
