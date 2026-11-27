import { useCallback, useEffect, useRef, useState } from "react";

export type ReplayState = "idle" | "playing" | "paused" | "done";

/** Milliseconds per printed line. */
export const SPEEDS = { slow: 1000, normal: 400, fast: 100 } as const;

/**
 * Line-by-line replay of `total` lines.
 *
 * `resetKey` identifies what is being replayed (the session): a new key starts
 * again from the top. If lines are added without the key changing (live mode),
 * the position is kept; when the replay had already reached the end and
 * `follow` is set, the new lines print by themselves.
 */
export function useReplay(total: number, resetKey: string | null, follow: boolean) {
  const [state, setState] = useState<ReplayState>("idle");
  const [cursor, setCursor] = useState(0); // number of lines printed so far
  const [speed, setSpeed] = useState<number>(SPEEDS.normal);
  const previous = useRef({ total, key: resetKey });

  useEffect(() => {
    const was = previous.current;
    previous.current = { total, key: resetKey };

    if (was.key !== resetKey) {
      setState("idle");
      setCursor(0);
      return;
    }
    if (total > was.total) {
      setState((s) => (s === "done" ? (follow ? "playing" : "paused") : s));
    } else if (total < was.total) {
      setCursor((c) => Math.min(c, total));
    }
  }, [total, resetKey, follow]);

  useEffect(() => {
    if (state !== "playing") return;
    if (cursor >= total) {
      setState("done");
      return;
    }
    const id = setTimeout(() => setCursor((c) => c + 1), speed);
    return () => clearTimeout(id);
  }, [state, cursor, total, speed]);

  const step = useCallback(() => {
    if (total === 0) return;
    const next = Math.min(cursor + 1, total);
    setCursor(next);
    setState(next >= total ? "done" : "paused");
  }, [cursor, total]);

  const play = useCallback(() => {
    if (total === 0) return;
    if (cursor >= total) setCursor(0); // replay from the start
    setState("playing");
  }, [cursor, total]);

  const pause = useCallback(() => {
    setState((s) => (s === "playing" ? "paused" : s));
  }, []);

  return { state, cursor, speed, setSpeed, step, play, pause };
}
