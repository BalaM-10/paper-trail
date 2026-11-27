import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  onClick?: () => void;
  /** Accessible name, when it says more than the printed label (it must contain it). */
  label?: string;
  tone?: "plain" | "red" | "wide";
  /** For keys that stay down, such as the chosen speed. */
  pressed?: boolean;
  disabled?: boolean;
};

/** A chunky key on the printer's front panel. A real button, so Enter and Space work. */
export function Key({ children, onClick, label, tone = "plain", pressed, disabled }: Props) {
  return (
    <button
      type="button"
      className={`key key--${tone}`}
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
