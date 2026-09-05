import { Moon, Sun } from "@phosphor-icons/react";

import type { Theme } from "../theme";

export function ThemeSelector({
  theme,
  onChange,
  className = "",
}: {
  theme: Theme;
  onChange: (theme: Theme) => void;
  className?: string;
}) {
  return (
    <div className={`theme-selector ${className}`.trim()} role="group" aria-label="Color theme">
      <button type="button" aria-pressed={theme === "light"} onClick={() => onChange("light")}>
        <Sun size={16} />
        <span>Light</span>
      </button>
      <button type="button" aria-pressed={theme === "dark"} onClick={() => onChange("dark")}>
        <Moon size={16} />
        <span>Dark</span>
      </button>
    </div>
  );
}
