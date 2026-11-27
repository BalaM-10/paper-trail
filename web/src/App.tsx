import { useCallback, useMemo, useState } from "react";
import { BuildTotals } from "./components/BuildTotals";
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
import { RecordSwitch } from "./components/RecordSwitch";
import { ReplayControls } from "./components/ReplayControls";
import { SessionList } from "./components/SessionList";
import { TamperKeys } from "./components/TamperKeys";
import { TearOffButton } from "./components/TearOffButton";
import { useChainCheck } from "./hooks/useChainCheck";
import { POLL_MS, useEntries, type View } from "./hooks/useEntries";
import { useFreshLine } from "./hooks/useFreshLine";
import { useReplay } from "./hooks/useReplay";
import type { Entry } from "./lib/chainCheck";
import { fingerprintText } from "./lib/entryText";
import { splitRolls, turnLabel } from "./lib/rolls";
import { synthesiseUndeclared } from "./lib/synthesiseUndeclared";

const NO_ENTRIES: Entry[] = [];

export default function App({ repoUrl = __REPO_URL__ }: { repoUrl?: string } = {}) {
  const [view, setView] = useState<View>("demo");
  const { entries, source, buildInfo, tamper, restore, isTampered, forceRefresh } = useEntries(POLL_MS, view);
  const { result: chain, unavailable } = useChainCheck(entries);
  // One roll of paper per turn of each session.
  const rolls = useMemo(() => splitRolls(entries), [entries]);

  const [picked, setPicked] = useState<string | null>(null);
  const [tamperTarget, setTamperTarget] = useState<number | null>(null);

  // The static demo opens on the interesting session: the one that is CONTRADICTED.
  const demoDefault =
    source === "demo" || source === "build"
      ? (rolls.find((r) => r.overallVerdict === "CONTRADICTED") ?? rolls[0])?.key ?? null
      : null;
  const selected =
    picked !== null && rolls.some((r) => r.key === picked) ? picked : demoDefault;
  const selectedRoll = rolls.find((r) => r.key === selected) ?? null;

  const sessionEntries = selectedRoll ? selectedRoll.entries : NO_ENTRIES;
  const lines = useMemo(() => synthesiseUndeclared(sessionEntries), [sessionEntries]);
  const replay = useReplay(lines.length, selected, source === "api");

  const brokenAt = chain && !chain.ok ? chain.brokenAt : null;

  // The paper splits at the broken line, if that line is on this session's paper.
  const tearIndex =
    brokenAt === null ? -1 : lines.findIndex((l) => !l._synthetic && l.seq === brokenAt);
  const torn = tearIndex >= 0;
  const freshIndex = useFreshLine(replay.cursor, torn);

  function selectRoll(key: string) {
    setPicked(key);
    setTamperTarget(null);
  }

  // Stable, so the memoised lines are not redrawn when something else changes.
  const toggleTarget = useCallback((seq: number) => {
    setTamperTarget((current) => (current === seq ? null : seq));
  }, []);

  function changeView(next: View) {
    setView(next);
    setPicked(null);
    setTamperTarget(null);
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
            sessions={rolls}
            selected={selected}
            source={source}
            onSelect={selectRoll}
            onVerified={forceRefresh}
            top={
              <>
                <RecordSwitch view={view} onChange={changeView} />
                {view === "build" && entries.length > 0 && <BuildTotals entries={entries} partial={buildInfo ? buildInfo.partial : null} />}
              </>
            }
          />

          <main className="stage__main">
            {source === "error" && (
              <p className="notice" role="alert">
                The paper jammed, and I couldn't find any records. Check that the demo file is in
                place, then reload the page.
              </p>
            )}
            {source === "build-missing" && (
              <p className="notice">
                The build record has not been published yet, so there is nothing to show here. Choose
                Demo to look at the sample sessions.
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
              preloaded={(source === "demo" || source === "build") && picked === null}
              replayState={replay.state}
              chainOk={chain ? chain.ok : true}
              brokenAt={brokenAt}
              tampered={isTampered}
              tamperTarget={tamperTarget}
              overallVerdict={selectedRoll?.overallVerdict ?? null}
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
                atEnd={replay.cursor >= lines.length}
                onPlay={replay.play}
                onPause={replay.pause}
                onStep={replay.step}
                onSkip={replay.skipToEnd}
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

          <Footer repoUrl={repoUrl} />
        </div>
      </div>

      {selectedRoll && (
        <PrintReport
          sessionId={selectedRoll.sessionId}
          turn={turnLabel(selectedRoll)}
          title={selectedRoll.title}
          chain={chain}
          lines={lines}
          fingerprint={fingerprintText(entries)}
        />
      )}
    </div>
  );
}
