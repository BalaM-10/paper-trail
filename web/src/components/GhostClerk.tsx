import type { ReplayState } from "../hooks/useReplay";
import type { Source } from "../hooks/useEntries";

export type Expression = "calm" | "pleased" | "alarmed";

export type GhostInput = {
  source: Source;
  /** Are there any records at all? */
  hasRecords: boolean;
  /** Is a session picked? */
  hasSession: boolean;
  /** The demo opened a session on its own and the visitor has not chosen yet. */
  preloaded: boolean;
  replayState: ReplayState;
  chainOk: boolean;
  brokenAt: number | null;
  /** The visitor tampered with the paper (so RESTORE can mend it). */
  tampered: boolean;
  /** The line picked to tamper with, if any. */
  tamperTarget: number | null;
  overallVerdict: string | null;
};

/**
 * What the clerk says and how he looks. Each message is short, dry and
 * friendly, and says what to do next, using the names printed on the
 * printer's keys (PLAY, PAUSE, FEED, TAMPER, RESTORE).
 */
export function ghostFor(i: GhostInput): { expression: Expression; message: string } {
  if (!i.chainOk) {
    return i.tampered
      ? {
          expression: "alarmed",
          message: "Ah. Someone's been at the paper. Click RESTORE and I'll pretend I saw nothing.",
        }
      : {
          expression: "alarmed",
          message: `Torn at line ${i.brokenAt}: a record was changed after it was written. Check the file on disk.`,
        };
  }
  if (i.source === "error") {
    return {
      expression: "alarmed",
      message: "The paper jammed and I found no records. Check the demo file, then reload the page.",
    };
  }
  if (i.source === "build-missing") {
    return {
      expression: "calm",
      message: "The build record isn't published yet. Click Demo to go back.",
    };
  }
  if (i.source === "loading") {
    return { expression: "calm", message: "Warming up the printer… nothing to click yet." };
  }
  if (!i.hasRecords) {
    return {
      expression: "calm",
      message: "Nothing is recorded yet. Ask the agent to do something and I'll print it here.",
    };
  }
  if (i.tamperTarget !== null) {
    return {
      expression: "calm",
      message: `Line ${i.tamperTarget} picked. Click TAMPER to forge it, or click the line again to let it go.`,
    };
  }
  if (!i.hasSession) {
    return {
      expression: "calm",
      message: "Pick a session from the list, then press PLAY and I'll print it line by line.",
    };
  }

  switch (i.replayState) {
    case "idle":
      return {
        expression: "calm",
        message: i.preloaded
          ? "I've pre-loaded the interesting session. Press PLAY when ready."
          : "Press PLAY to start. I'll stay here and watch.",
      };
    case "playing":
      return {
        expression: "calm",
        message: "Printing… press PAUSE to stop, or FEED to go one line at a time.",
      };
    case "paused":
      return {
        expression: "calm",
        message: "Paused. Press PLAY to continue, or FEED for one more line.",
      };
    case "done":
      switch (i.overallVerdict) {
        case "SUPPORTED":
          return {
            expression: "pleased",
            message: "Everything checks out. Remarkable. Pick another session, or Tear off a report.",
          };
        case "CONTRADICTED":
          return {
            expression: "alarmed",
            message: "The statement doesn't match what the witness saw. Click the red circle for the proof.",
          };
        case "NO_STATEMENT":
          return {
            expression: "alarmed",
            message: "The agent changed files and said nothing. Click a red circle to see what the witness saw.",
          };
        case "UNVERIFIED":
          return {
            expression: "calm",
            message: "Some claims couldn't be confirmed, which isn't the same as wrong. Pick another session.",
          };
        default:
          return {
            expression: "calm",
            message: "All printed, but no verdict yet. Click 'Check this statement' to get one.",
          };
      }
  }
}

/**
 * An original little ghost: a white sheet with a ragged hem, wearing a green
 * clerk's eyeshade. Three expressions, drawn as different mouths and eyes.
 * The size comes from CSS (120 px, 96 px on a phone).
 */
export function GhostSvg({ expression }: { expression: Expression }) {
  const eyeRadius = expression === "alarmed" ? 5.5 : 4;
  const eyeGap = expression === "pleased" ? 14 : 12;
  return (
    <svg
      className="ghost-clerk__svg"
      data-expression={expression}
      viewBox="0 0 100 100"
      aria-hidden="true"
      focusable="false"
    >
      {/* where he sits on the printer */}
      <ellipse data-part="shadow" cx="50" cy="92" rx="30" ry="3.5" fill="rgba(0,0,0,0.35)" />
      {/* sheet body with a ragged hem */}
      <path
        data-part="body"
        d="M 20 90 Q 20 20 50 15 Q 80 20 80 90 Q 70 82 60 90 Q 50 82 40 90 Q 30 82 20 90 Z"
        fill="#ffffff"
        stroke="#8a8a8a"
        strokeWidth="1.5"
      />
      {/* the green clerk's eyeshade */}
      <rect data-part="visor" x="18" y="28" width="64" height="14" rx="4" fill="#3a7d44" />
      <rect data-part="visor-brim" x="14" y="38" width="72" height="4" rx="2" fill="#2d6235" />
      {/* eyes */}
      <circle data-part="eye" cx={50 - eyeGap} cy="55" r={eyeRadius} fill="#222" />
      <circle data-part="eye" cx={50 + eyeGap} cy="55" r={eyeRadius} fill="#222" />
      {/* mouth */}
      {expression === "pleased" && (
        <path
          data-part="mouth"
          d="M 38 62 Q 50 72 62 62"
          fill="none"
          stroke="#333"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      )}
      {expression === "alarmed" && (
        <ellipse data-part="mouth" cx="50" cy="65" rx="5" ry="6.5" fill="#333" />
      )}
      {expression === "calm" && (
        <line
          data-part="mouth"
          x1="40"
          y1="64"
          x2="60"
          y2="64"
          stroke="#333"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}

/** The clerk, sitting on the corner of the printer with his speech bubble beside him. */
export function GhostClerk(props: GhostInput) {
  const { expression, message } = ghostFor(props);
  return (
    <aside className="ghost-clerk" aria-label="Ghost clerk">
      <p className="ghost-clerk__message" aria-live="polite">
        {message}
      </p>
      <div className="ghost-clerk__figure">
        <div className="ghost-clerk__bob">
          <GhostSvg expression={expression} />
        </div>
      </div>
    </aside>
  );
}
