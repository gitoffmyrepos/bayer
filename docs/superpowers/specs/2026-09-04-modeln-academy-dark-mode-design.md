# ModelN Academy Light and Dark Theme Design

**Date:** 2026-09-04  
**Status:** Approved for implementation  
**Selected direction:** Explicit labeled Light/Dark selector

## Objective

Let a learner choose a comfortable light or dark visual theme from every stage of the Academy experience. The choice must be easy to discover, persist on the current browser, apply without a light-color flash during startup, and preserve the existing forest, teal, mineral, and amber visual identity.

## Interaction Design

A reusable `ThemeSelector` presents two labeled choices, `Light` and `Dark`, as an accessible segmented control. The active choice has a filled treatment, while the inactive choice remains clearly selectable. The control uses native buttons inside a named group, exposes the current pressed state, supports keyboard operation, and keeps a visible focus indicator.

The selector appears:

- in the login card before authentication;
- above the learner profile in the desktop sidebar;
- in a compact utility row above page content on mobile.

Changing the selection updates the complete interface immediately. It does not require a page reload, affect learner progress, or call an API.

## Preference Behavior

The only explicit choices are Light and Dark. On the first visit, before the learner has chosen either option, the Academy uses the operating system `prefers-color-scheme` value. After an explicit selection, it stores `light` or `dark` under a versioned local-storage key and uses that value on subsequent visits.

Storage or media-query failures fall back to Light without preventing the application from loading. A small script in `index.html` applies the resolved theme to the document root before the React bundle and stylesheet render. React then initializes from the same resolver, preventing a theme mismatch or startup flash.

The root contract is `data-theme="light"` or `data-theme="dark"` on `<html>`, together with the matching CSS `color-scheme` value.

## Visual System

Existing light-only surface, text, border, input, navigation, and feedback colors move behind semantic CSS variables. The light theme remains visually unchanged except where tokenization is required.

Dark mode uses:

- a near-black green mineral page background;
- deep forest raised surfaces rather than flat black;
- warm off-white primary text and muted sage secondary text;
- brighter teal for interactive and focus states;
- amber for investigation emphasis and cautions;
- distinct green and red feedback surfaces with readable text;
- borders and shadows tuned for separation without glowing effects.

Incident simulations already use a focused dark treatment and retain their hierarchy. Maps, mastery cards, mission beats, search results, quiz options, form inputs, loading states, and the mobile navigation receive explicit dark-theme coverage. No information is conveyed by color alone.

## Components and State Flow

`src/theme.ts` owns the pure preference contract: validate stored values, resolve the initial value, persist a new selection, and apply it to the document root. `src/components/ThemeSelector.tsx` owns the reusable control. `App.tsx` owns the current theme state and passes the selector to authenticated and unauthenticated layouts.

The data flow is:

1. The pre-render script reads the stored choice or device preference and sets `data-theme`.
2. React resolves the same value into state.
3. The learner chooses Light or Dark.
4. The application applies the root attribute, updates `color-scheme`, and persists the explicit choice.
5. Reloads use the persisted choice before first paint.

Theme preference remains browser-local because it is a presentation setting, not learning progress. Cross-device theme synchronization is outside this feature.

## Accessibility and Motion

The control has an accessible group label, visible text and icons, `aria-pressed` state, keyboard activation, and focus-visible styling. Both themes maintain readable contrast for text, controls, error messages, correct/incorrect feedback, disabled states, and source-classification labels. Existing reduced-motion behavior remains unchanged.

## Testing and Acceptance

Unit and component tests are written first and must prove:

- a valid saved choice wins over the device preference;
- an absent or invalid saved choice falls back to the device preference;
- unavailable browser APIs fall back safely;
- selecting Dark updates the root attribute and persists `dark`;
- selecting Light reverses the state and persists `light`;
- the selector is available before and after sign-in with accessible state.

The production build must pass TypeScript checking, Vitest, and Vite compilation. Browser verification must cover desktop and mobile at `https://modeln.strategybase.io`, select Dark, reload to prove persistence, return to Light, and inspect representative dashboard, mission, quiz, atlas, review, and simulation surfaces. The deployed image must reconcile through GitOps, with Argo CD Synced/Healthy and no application 5xx errors.

## Scope Boundaries

This feature does not add a third Auto option, server-side theme storage, new authentication behavior, content changes, theme scheduling, user-created palettes, or changes to kgateway/DNS exposure.
