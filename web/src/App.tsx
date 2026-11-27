import { useMemo, useState } from "react";
import { ChainStatus } from "./components/ChainStatus";
import { Footer } from "./components/Footer";
import { GhostClerk } from "./components/GhostClerk";
import { Header } from "./components/Header";
import { InkFilters } from "./components/InkFilters";
import { LiveIndicator } from "./components/LiveIndicator";
import { PaperRoll } from "./components/PaperRoll";
import { Printer, type Light } from "./components/Printer";
import { PrintLine } from "./components/PrintLine";
import { PrintReport } from "./components/PrintReport";
import { ReplayControls } from "./components/ReplayControls";
import { SessionList } from "./components/SessionList";
import { TamperKeys } from "./components/TamperKeys";
import { TearOffButton } from "./components/TearOffButton";
import { useChainCheck } from "./hooks/useChainCheck";
import { useEntries } from "./hooks/useEntries";
import { useFreshLine } from "./hooks/useFreshLine";
import { useReplay } from "./hooks/useReplay";
import { buildSessionMeta } from "./lib/sessionMeta";
import { synthesiseUndeclared } from "./lib/synthesiseUndeclared";

export default function App() {
  const { entries, source, tamper, restore, isTampered, forceRefresh } = useEntries();
  const { result: chain, unavailable } = useChainCheck(entries);
  const sessions = useMemo(() => buildSessionMeta(entries), [entries]);

  const [picked, setPicked] = useState<string | null>(null);
  const [tamperTarget, setTamperTarget] = useState<number | null>(null);

  // The static demo opens on the interesting session: the one that is CONTRADICTED.
  const demoDefault =
    source === "demo"
      ? (sessions.find((s) => s.overallVerdict === "CONTRADICTED") ?? sessions[0])?.sessionId ?? null
      : null;
  const selected =
    picked !== null && sessions.some((s) => s.sessionId === picked) ? picked : demoDefault;
  const selectedMeta = sessions.find((s) => s.sessionId === selected) ?? null;

  const sessionEntries = useMemo(
    () => entries.filter((e) => e.session_id === selected),
    [entries, selected],
  );
  const lines = useMemo(() => synthesiseUndeclared(sessionEntries), [sessionEntries]);
  const replay = useReplay(lines.length, selected, source === "api");

  const brokenAt = chain && !chain.ok ? chain.brokenAt : null;

  // The paper splits at the broken line, if that line is on this session's paper.
  const tearIndex =
    brokenAt === null ? -1 : lines.findIndex((l) => !l._synthetic && l.seq === brokenAt);
  const torn = tearIndex >= 0;
  const freshIndex = useFreshLine(replay.cursor, torn);

  function selectSession(sessionId: string) {
    setPicked(sessionId);
    setTamperTarget(null);
  }

  function toggleTarget(seq: number) {
    setTamperTarget((current) => (current === seq ? null : seq));
  }

  function tamperWithPaper() {
    // The picked line, else the cleanup command line of this session, else the last line.
    const fallback =
      sessionEntries.find((e) => e.kind === "tool" && e.data.tool_name === "execute_pwsh") ??
      sessionEntries[sessionEntries.length - 1] ??
      entries[entries.length - 1];
    const seq = tamperTarget ?? fallback?.seq;
    if (seq === undefined) return;
    tamper(seq);
    setTamperTarget(null);
  }

  function restorePaper() {
    restore();
    setTamperTarget(null);
  }

  // What the paper status says, in words.
  let status;
  if (unavailable) {
    status = (
      <span className="chain-status chain-status--unknown">
        Paper not checked: this browser can't do it on this address
      </span>
    );
  } else if (chain) {
    status = <ChainStatus ok={chain.ok} brokenAt={brokenAt} />;
  } else if (entries.length > 0) {
    status = <span className="chain-status">Checking the paper…</span>;
  } else {
    status = <span className="chain-status">No paper yet</span>;
  }

  // The printer's light and the word on its display always agree.
  let light: Light = "ready";
  let printerState = "Ready";
  if (source === "loading") {
    light = "off";
    printerState = "Warming up";
  } else if (brokenAt !== null) {
    light = "error";
    printerState = "Jammed";
  } else if (entries.length === 0) {
    light = "off";
    printerState = "Tray empty";
  } else if (replay.state === "playing") {
    light = "busy";
    printerState = "Printing";
  } else if (replay.state === "paused") {
    printerState = "Paused";
  } else if (replay.state === "done") {
    printerState = "Finished";
  }

  const rows = lines.map((entry, i) => (
    <PrintLine
      key={entry._synthetic ? `u${i}` : entry.seq}
      entry={entry}
      visible={i < replay.cursor}
      isNext={i === replay.cursor}
      selected={tamperTarget === entry.seq}
      fresh={i === freshIndex}
      onSelect={toggleTarget}
    />
  ));

  const empty = (
    <li className="print-line print-line--empty">
      <span className="print-line__no" />
      <span className="print-line__text">
        {selected
          ? "Nothing printed for this session yet."
          : "Blank paper. Pick a session and I'll print something."}
      </span>
    </li>
  );

  return (
    <div className="app">
      <div className="screen-only">
        <InkFilters />
        <div className="stage">
          <Header />

          <SessionList
            sessions={sessions}
            selected={selected}
            source={source}
            onSelect={selectSession}
            onVerified={forceRefresh}
          />

          <main className="stage__main">
            {source === "error" && (
              <p className="notice" role="alert">
                The paper jammed, and I couldn't find any records. Check that the demo file is in
                place, then reload the page.
              </p>
            )}
            {(source === "api" || source === "demo") && entries.length === 0 && (
              <p className="notice">
                The paper tray is empty: nothing has been recorded yet. Ask the agent to do
                something and it will print here.
              </p>
            )}

            <GhostClerk
              source={source}
              hasRecords={entries.length > 0}
              hasSession={selected !== null}
              preloaded={source === "demo" && picked === null}
              replayState={replay.state}
              chainOk={chain ? chain.ok : true}
              brokenAt={brokenAt}
              tampered={isTampered}
              tamperTarget={tamperTarget}
              overallVerdict={selectedMeta?.overallVerdict ?? null}
            />

            <Printer
              light={light}
              display={
                <>
                  <span className="lcd__state">{printerState}</span>
                  <div className="lcd__status" role="status" aria-label="Paper status">
                    {status}
                    {source === "api" && <LiveIndicator />}
                  </div>
                </>
              }
            >
              <ReplayControls
                state={replay.state}
                speed={replay.speed}
                disabled={lines.length === 0}
                onPlay={replay.play}
                onPause={replay.pause}
                onStep={replay.step}
                onSpeed={replay.setSpeed}
              />
              <TamperKeys
                canTamper={entries.length > 0}
                canRestore={isTampered}
                onTamper={tamperWithPaper}
                onRestore={restorePaper}
              />
              <TearOffButton />
            </Printer>

            <PaperRoll
              torn={torn}
              upper={lines.length === 0 ? empty : torn ? rows.slice(0, tearIndex) : rows}
              lower={torn ? rows.slice(tearIndex) : null}
            />
          </main>

          <Footer repoUrl={__REPO_URL__} />
        </div>
      </div>

      {selected && selectedMeta && (
        <PrintReport
          sessionId={selected}
          title={selectedMeta.title}
          chain={chain}
          lines={lines}
        />
      )}
    </div>
  );
}
