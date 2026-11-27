import { Key } from "./Key";

/** Prints the clean evidence report (see PrintReport and print.css). */
export function TearOffButton() {
  return (
    <Key tone="wide" onClick={() => window.print()}>
      Tear off report
    </Key>
  );
}
