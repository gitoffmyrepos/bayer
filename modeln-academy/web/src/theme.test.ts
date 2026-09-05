import { afterEach, describe, expect, it, vi } from "vitest";

import { applyTheme, resolveTheme, saveTheme, THEME_STORAGE_KEY } from "./theme";

describe("theme preference", () => {
  afterEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
    vi.restoreAllMocks();
  });

  it("prefers a valid saved selection over the device preference", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");

    expect(resolveTheme(window.localStorage, () => ({ matches: false }))).toBe("dark");
  });

  it("uses the device preference when no valid selection is saved", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "sepia");

    expect(resolveTheme(window.localStorage, () => ({ matches: true }))).toBe("dark");
  });

  it("falls back to light when browser preference APIs fail", () => {
    const storage = {
      getItem: () => { throw new Error("blocked"); },
      setItem: vi.fn(),
    };

    expect(resolveTheme(storage, () => { throw new Error("blocked"); })).toBe("light");
  });

  it("applies and persists an explicit selection", () => {
    saveTheme("dark", window.localStorage, document.documentElement);

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("applies a theme without persisting it", () => {
    applyTheme("light", document.documentElement);

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });
});
