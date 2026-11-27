import { SPEEDS, type ReplayState } from "../hooks/useReplay";
import { Key } from "./Key";

type Props = {
  state: ReplayState;
  speed: number;
  /** Nothing to replay (no session picked, or it has no lines). */
  disabled: boolean;
  /** Everything is already printed. */
  atEnd: boolean;
  onPlay: () => void;
  onPause: () => void;
  onStep: () => void;
  onSkip: () => void;
  onSpeed: (ms: number) => void;
};

const SPEED_KEYS: [string, number][] = [
  ["Slow", SPEEDS.slow],
  ["Normal", SPEEDS.normal],
  ["Fast", SPEEDS.fast],
];

/** PLAY/PAUSE, FEED (one line), SKIP TO END and the three speed keys. */
export function ReplayControls({ state, speed, disabled, atEnd, onPlay, onPause, onStep, onSkip, onSpeed }: Props) {
  return (
    <>
      <div className="key-group replay-controls" role="group" aria-label="Replay controls">
        {state === "playing" ? (
          <Key onClick={onPause} disabled={disabled}>
            Pause
          </Key>
        ) : (
          <Key onClick={onPlay} disabled={disabled}>
            Play
          </Key>
        )}
        <Key onClick={onStep} disabled={disabled} label="Feed one line">
          Feed
        </Key>
        <Key onClick={onSkip} disabled={disabled || atEnd} label="Skip to end">
          Skip to end
        </Key>
      </div>
      <div className="key-group speed-keys" role="group" aria-label="Speed">
        {SPEED_KEYS.map(([name, ms]) => (
          <Key key={name} pressed={speed === ms} onClick={() => onSpeed(ms)}>
            {name}
          </Key>
        ))}
      </div>
    </>
  );
}
