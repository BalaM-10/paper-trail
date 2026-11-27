import { Key } from "./Key";

type Props = {
  on: boolean;
  onToggle: () => void;
  disabled?: boolean;
};

/**
 * The EXCEPTIONS ONLY key. It stays down while it is on (aria-pressed), and it is a
 * real button, so Tab, Enter and Space work. It only changes what the page shows.
 */
export function ExceptionsKey({ on, onToggle, disabled }: Props) {
  return (
    <div className="key-group filter-controls" role="group" aria-label="Filter">
      <Key pressed={on} onClick={onToggle} disabled={disabled}>
        Exceptions only
      </Key>
    </div>
  );
}
