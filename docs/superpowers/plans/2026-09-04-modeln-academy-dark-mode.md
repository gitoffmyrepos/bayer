# ModelN Academy Dark Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an accessible, persistent Light/Dark selector across the ModelN Academy and deploy the dark-theme-capable web image to the internal homelab.

**Architecture:** A focused theme module owns validation, device fallback, DOM application, and local storage persistence. A reusable React segmented control is rendered in login, desktop sidebar, tablet/mobile utility, and standalone mission states. Semantic CSS tokens provide complete light/dark surface coverage, while a pre-render script resolves the same preference before the React bundle loads.

**Tech Stack:** React 19, TypeScript 5.9, Vitest, Testing Library, CSS custom properties, Vite, Playwright, Docker Buildx, Harbor, Kubernetes, Argo CD

---

## File Map

- Create `modeln-academy/web/src/theme.ts`: pure theme preference and DOM application contract.
- Create `modeln-academy/web/src/theme.test.ts`: preference resolution, failure fallback, persistence, and root-application tests.
- Create `modeln-academy/web/src/components/ThemeSelector.tsx`: accessible labeled Light/Dark segmented control.
- Modify `modeln-academy/web/src/App.test.tsx`: selector availability and authenticated interaction tests.
- Modify `modeln-academy/web/src/App.tsx`: own theme state and render selectors in authenticated layouts.
- Modify `modeln-academy/web/src/views/LoginView.tsx`: render the selector before sign-in.
- Modify `modeln-academy/web/src/styles.css`: semantic color tokens, dark palette, selector styling, and responsive placement.
- Modify `modeln-academy/web/index.html`: apply the stored/device preference before first paint.
- Modify `modeln-academy/web/e2e/academy.spec.ts`: verify selection and persistence in desktop and mobile browsers.
- Modify `sb-gitops/prod/platform-workloads/manifests/modeln-academy/04-workloads.yaml`: deploy the immutable web image digest.

### Task 1: Theme preference contract

**Files:**
- Create: `modeln-academy/web/src/theme.ts`
- Test: `modeln-academy/web/src/theme.test.ts`

- [ ] **Step 1: Write failing resolution and persistence tests**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { applyTheme, resolveTheme, saveTheme, THEME_STORAGE_KEY } from "./theme";

describe("theme preference", () => {
  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
    vi.restoreAllMocks();
  });

  it("prefers a valid saved selection over the device preference", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    expect(resolveTheme(localStorage, () => ({ matches: false }))).toBe("dark");
  });

  it("uses the device preference when no valid selection is saved", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "sepia");
    expect(resolveTheme(localStorage, () => ({ matches: true }))).toBe("dark");
  });

  it("falls back to light when browser preference APIs fail", () => {
    expect(resolveTheme({ getItem: () => { throw new Error("blocked"); }, setItem: vi.fn() }, () => { throw new Error("blocked"); })).toBe("light");
  });

  it("applies and persists an explicit selection", () => {
    saveTheme("dark", localStorage, document.documentElement);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("applies a theme without persisting it", () => {
    applyTheme("light", document.documentElement);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `cd modeln-academy/web && npm test -- src/theme.test.ts`

Expected: FAIL because `./theme` does not exist.

- [ ] **Step 3: Implement the minimal preference module**

```ts
export type Theme = "light" | "dark";
export const THEME_STORAGE_KEY = "modeln-academy-theme-v1";

type ThemeStorage = Pick<Storage, "getItem" | "setItem">;
type ThemeMedia = (query: string) => Pick<MediaQueryList, "matches">;

function isTheme(value: string | null): value is Theme {
  return value === "light" || value === "dark";
}

export function resolveTheme(
  storage?: ThemeStorage,
  media?: ThemeMedia,
): Theme {
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
  try { (storage ?? window.localStorage).setItem(THEME_STORAGE_KEY, theme); } catch { /* presentation preference is non-critical */ }
}
```

- [ ] **Step 4: Run the focused and full frontend tests**

Run: `cd modeln-academy/web && npm test -- src/theme.test.ts && npm test`

Expected: focused tests PASS and the existing five tests remain PASS.

- [ ] **Step 5: Commit the theme contract**

```bash
git add modeln-academy/web/src/theme.ts modeln-academy/web/src/theme.test.ts
git commit -m "feat(academy): add persistent theme preference"
```

### Task 2: Accessible selector and layout integration

**Files:**
- Create: `modeln-academy/web/src/components/ThemeSelector.tsx`
- Modify: `modeln-academy/web/src/App.test.tsx`
- Modify: `modeln-academy/web/src/App.tsx`
- Modify: `modeln-academy/web/src/views/LoginView.tsx`

- [ ] **Step 1: Add failing component behavior tests**

Import `within` from Testing Library, clear theme state in `afterEach`, and add these tests:

```tsx
it("lets an anonymous learner select and persist dark mode", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() =>
    response({ detail: { message: "Sign in to continue." } }, 401),
  );
  render(<App />);

  const group = await screen.findByRole("group", { name: "Color theme" });
  const dark = within(group).getByRole("button", { name: "Dark" });
  await userEvent.click(dark);

  expect(dark).toHaveAttribute("aria-pressed", "true");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem("modeln-academy-theme-v1")).toBe("dark");
});

it("keeps theme selection available after sign-in", async () => {
  mockSignedInApi();
  render(<App />);

  const groups = await screen.findAllByRole("group", { name: "Color theme" });
  expect(groups).toHaveLength(2);
  await userEvent.click(within(groups[0]).getByRole("button", { name: "Light" }));
  expect(document.documentElement.dataset.theme).toBe("light");
});
```

Extend `afterEach` with:

```ts
localStorage.clear();
document.documentElement.removeAttribute("data-theme");
document.documentElement.style.colorScheme = "";
```

- [ ] **Step 2: Run the component tests and verify RED**

Run: `cd modeln-academy/web && npm test -- src/App.test.tsx`

Expected: FAIL because no `Color theme` group is rendered.

- [ ] **Step 3: Create the reusable selector**

```tsx
import { Moon, Sun } from "@phosphor-icons/react";
import type { Theme } from "../theme";

export function ThemeSelector({ theme, onChange, className = "" }: {
  theme: Theme;
  onChange: (theme: Theme) => void;
  className?: string;
}) {
  return (
    <div className={`theme-selector ${className}`.trim()} role="group" aria-label="Color theme">
      <button type="button" aria-pressed={theme === "light"} onClick={() => onChange("light")}><Sun size={16} /><span>Light</span></button>
      <button type="button" aria-pressed={theme === "dark"} onClick={() => onChange("dark")}><Moon size={16} /><span>Dark</span></button>
    </div>
  );
}
```

- [ ] **Step 4: Wire theme state through all application states**

Initialize `const [theme, setTheme] = useState<Theme>(() => resolveTheme())`, apply it once on mount, and define `chooseTheme(next)` to call `setTheme(next)` and `saveTheme(next)`. Pass the selector into `LoginView` and render it in the login card; render it above the desktop sidebar learner profile, in a responsive mobile content utility row, and next to standalone mission content so the learner never has to leave the current task to switch.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `cd modeln-academy/web && npm test -- src/App.test.tsx src/theme.test.ts`

Expected: all theme and application tests PASS.

- [ ] **Step 6: Commit selector integration**

```bash
git add modeln-academy/web/src/components/ThemeSelector.tsx modeln-academy/web/src/App.tsx modeln-academy/web/src/App.test.tsx modeln-academy/web/src/views/LoginView.tsx
git commit -m "feat(academy): expose light and dark selector"
```

### Task 3: Complete visual themes and prevent startup flash

**Files:**
- Modify: `modeln-academy/web/src/styles.css`
- Modify: `modeln-academy/web/index.html`

- [ ] **Step 1: Add semantic light tokens and dark overrides**

Add the following light defaults and dark values to the root token block, then replace matching hard-coded light values throughout the existing selectors with the semantic token names:

```css
:root {
  --page: #f3f0e8;
  --surface: #fffdf8;
  --surface-muted: #edf1ed;
  --control: #ffffff;
  --control-border: #d4dad5;
  --hover: #eef3ef;
  --quiet: #e9eee9;
  --track: #dfe6e1;
  --ghost: rgba(23, 62, 53, .06);
  --copy: #4f5f59;
  --label: #45534e;
  --icon-muted: #9ca9a3;
  --coach: #e0eee8;
  --coach-empty: #eeeae0;
  --success-copy: #245b4c;
  --success-surface: #dceee6;
  --error-copy: #823f38;
  --error-surface: #f4dfda;
  --mobile-nav: rgba(255, 253, 248, .96);
}

[data-theme="dark"] {
  --ink: #edf5f1;
  --forest: #102c26;
  --forest-2: #4f9f89;
  --teal: #72c3aa;
  --teal-soft: #173f35;
  --amber: #efb65d;
  --amber-soft: #4a371c;
  --paper: #162e29;
  --mineral: #0c1d1a;
  --muted: #a2b6af;
  --danger: #ff9a8f;
  --page: #0c1d1a;
  --surface: #162e29;
  --surface-muted: #203a34;
  --control: #102622;
  --control-border: #35534a;
  --hover: #203f37;
  --quiet: #203b35;
  --track: #29463f;
  --ghost: rgba(199, 229, 218, .07);
  --copy: #c2d1cc;
  --label: #c9d8d3;
  --icon-muted: #7d958d;
  --coach: #183d34;
  --coach-empty: #2b332f;
  --success-copy: #b9ead8;
  --success-surface: #174437;
  --error-copy: #ffc0b9;
  --error-surface: #492b2a;
  --mobile-nav: rgba(15, 36, 31, .96);
  --shadow: 0 0 0 1px rgba(201, 229, 219, .09), 0 16px 34px rgba(0, 0, 0, .26);
}
```

- [ ] **Step 2: Style the selector and responsive placements**

Add these exact selector and placement rules:

```css
.theme-selector { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 4px; border: 1px solid var(--control-border); border-radius: 12px; background: var(--control); }
.theme-selector button { min-height: 36px; border: 0; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; color: var(--muted); background: transparent; font-size: .75rem; font-weight: 750; }
.theme-selector button[aria-pressed="true"] { color: white; background: var(--forest-2); box-shadow: 0 4px 12px rgba(14, 45, 38, .2); }
.login-theme { margin: 0 0 24px auto; width: min(220px, 100%); }
.sidebar-theme { margin-top: auto; border-color: rgba(255,255,255,.12); background: rgba(255,255,255,.05); }
.sidebar-theme button { color: #a9bcb5; }
.sidebar-profile { margin-top: 14px; }
.content-theme { display: none; }
.standalone-theme { display: flex; justify-content: flex-end; padding: 18px clamp(18px, 4vw, 60px) 0; }

@media (max-width: 980px) {
  .sidebar-theme { display: none; }
  .content-theme { width: min(220px, 100%); margin: 0 0 24px auto; display: grid; }
}
```

- [ ] **Step 3: Add the pre-render bootstrap script**

Insert this script in `<head>` before stylesheet or module rendering:

```html
<script>
  (() => {
    const key = "modeln-academy-theme-v1";
    let theme = "light";
    try {
      const saved = localStorage.getItem(key);
      theme = saved === "light" || saved === "dark"
        ? saved
        : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch {}
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  })();
</script>
```

- [ ] **Step 4: Run the complete frontend quality gate**

Run: `cd modeln-academy/web && npm test && npm run lint && npm run build`

Expected: all tests PASS, TypeScript reports no errors, and Vite completes a production build.

- [ ] **Step 5: Commit visual theme implementation**

```bash
git add modeln-academy/web/src/styles.css modeln-academy/web/index.html
git commit -m "feat(academy): add complete dark palette"
```

### Task 4: Browser regression coverage

**Files:**
- Modify: `modeln-academy/web/e2e/academy.spec.ts`

- [ ] **Step 1: Add a Playwright persistence test**

Add this test and the final mobile assertion:

```ts
test("theme selection persists across a signed-in reload", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("kelvin");
  await page.getByLabel("Password").fill(learnerPassword);
  await page.getByRole("button", { name: "Start learning" }).click();

  const theme = page.getByRole("group", { name: "Color theme" }).first();
  await theme.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("group", { name: "Color theme" }).first().getByRole("button", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

await expect(page.getByRole("group", { name: "Color theme" }).last()).toBeVisible();
```

Use Playwright keyboard input to focus the selector buttons and activate each with Enter. Inspect the computed foreground/background pairs for the selector, body copy, muted copy, inputs, quiz feedback, and mobile navigation; require WCAG AA contrast for normal text in both themes.

- [ ] **Step 2: Run local browser tests**

Run the established local frontend/API test environment, then run `cd modeln-academy/web && npm run test:e2e`.

Expected: existing mission/evidence and mobile flows plus the new persistence flow PASS.

- [ ] **Step 3: Commit browser coverage**

```bash
git add modeln-academy/web/e2e/academy.spec.ts
git commit -m "test(academy): cover persistent theme selection"
```

### Task 5: Publish, reconcile, and verify the homelab deployment

**Files:**
- Modify in `sb-gitops`: `prod/platform-workloads/manifests/modeln-academy/04-workloads.yaml`

- [ ] **Step 1: Push the Bayer master commits**

Run: `git pull --rebase origin master && git push origin master`

Expected: local and `origin/master` revisions match.

- [ ] **Step 2: Build and publish the web image**

Run from `modeln-academy`:

```bash
source_commit="$(git rev-parse --short=12 HEAD)"
image="harbor.strategybase.io/sb-custom-docker-images/modeln-academy-web:sha-${source_commit}"
docker buildx build --platform linux/amd64,linux/arm64 -f web/Dockerfile -t "$image" --push .
docker buildx imagetools inspect "$image"
```

Expected: both `linux/amd64` and `linux/arm64` manifests exist; use the manifest-list `sha256:` digest in GitOps.

- [ ] **Step 3: Update and validate GitOps**

Replace only the web image digest in `04-workloads.yaml`. Run:

```bash
kubectl kustomize prod/platform-workloads/manifests/modeln-academy | kubeconform -strict -ignore-missing-schemas -summary -kubernetes-version 1.33.0
kubectl kustomize prod/platform-workloads/manifests/modeln-academy | kubectl --context sb-ha-cluster apply --dry-run=server -f -
```

Expected: zero invalid resources and server-side dry-run success.

- [ ] **Step 4: Commit and push GitOps**

```bash
git add prod/platform-workloads/manifests/modeln-academy/04-workloads.yaml
git commit -m "feat(modeln-academy): deploy dark theme"
git pull --rebase origin master
git push origin master
```

- [ ] **Step 5: Reconcile and verify live behavior**

Hard-refresh the `modeln-academy` Argo application and wait for `Synced`, `Healthy`, and `Succeeded`. Verify five deployments remain ready, both kgateway HTTPRoutes remain Accepted/ResolvedRefs, HTTPS returns 200 with trusted TLS, HTTP redirects to HTTPS, and no Ingress or Tailscale proxy exists.

- [ ] **Step 6: Run deployed browser verification**

Launch Chromium with `--host-resolver-rules=MAP modeln.strategybase.io 192.168.119.240`, retrieve the learner password from `modeln-academy-runtime` without printing it, and run desktop/mobile login plus Dark-select/reload/Light-select checks against `https://modeln.strategybase.io`.

Expected: all flows PASS; precise service log scans contain no exceptions, panics, or HTTP 5xx responses.
