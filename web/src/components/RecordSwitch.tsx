import type { View } from "../hooks/useEntries";

const CHOICES: [View, string][] = [
  ["demo", "Demo"],
  ["build", "How this was built"],
];

/**
 * Chooses which record the page shows: the demo sessions, or the record of how
 * Paper Trail itself was built. Two real buttons, so Tab, Enter and Space work,
 * and each says whether it is the chosen one.
 */
export function RecordSwitch({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <div className="record-switch" role="group" aria-label="Record to show">
      {CHOICES.map(([value, label]) => (
        <button
          key={value}
          type="button"
          aria-pressed={view === value}
          onClick={() => view !== value && onChange(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}