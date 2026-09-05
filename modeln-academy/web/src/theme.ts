export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "modeln-academy-theme-v1";

type ThemeStorage = Pick<Storage, "getItem" | "setItem">;
type ThemeMedia = (query: string) => Pick<MediaQueryList, "matches">;

function isTheme(value: string | null): value is Theme {
  return value === "light" || value === "dark";
}

export function resolveTheme(storage?: ThemeStorage, media?: ThemeMedia): Theme {
  try {
    const saved = (storage ?? window.localStorage).getItem(THEME_STORAGE_KEY);
    if (isTheme(saved)) return saved;
  } catch {
    return "light";
  }

  try {
    const matches = media
      ? media("(prefers-color-scheme: dark)").matches
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    return matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement) {
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

export function saveTheme(
  theme: Theme,
  storage?: ThemeStorage,
  root: HTMLElement = document.documentElement,
) {
  applyTheme(theme, root);
  try {
    (storage ?? window.localStorage).setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // A blocked presentation preference must never block the academy.
  }
}
