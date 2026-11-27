import { Key } from "./Key";

type Props = {
  canTamper: boolean;
  canRestore: boolean;
  onTamper: () => void;
  onRestore: () => void;
};

/** The red TAMPER key and the RESTORE key. Nothing here writes anywhere. */
export function TamperKeys({ canTamper, canRestore, onTamper, onRestore }: Props) {
  return (
    <div className="key-group tamper-controls" role="group" aria-label="Tamper demo">
      <Key tone="red" label="Tamper with the paper" onClick={onTamper} disabled={!canTamper}>
        Tamper
      </Key>
      <Key onClick={onRestore} disabled={!canRestore}>
        Restore
      </Key>
    </div>
  );
}
