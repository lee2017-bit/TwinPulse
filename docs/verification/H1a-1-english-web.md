# H1a-1 English web UI — local no-call verification

- Date: 2026-09-25 KST.
- Source boundary: local `main` HEAD `5c42899a95a0bf2422550bd17df7556a92ab3232` with pre-existing dirty changes. The existing offline-mode edits in `App.tsx` and workflow type addition in `types.ts` were preserved; `types.ts` was not edited for H1a-1.
- Result: **H1a-1 WEB_UNIT_BUILD_BROWSER_PASS / ACTUAL_ISAAC_NOT_RUN**. H1a-2, H1b, H2-H8 remain outside this result.

## Implemented scope

- English product copy for the existing three screens, settings, warnings, status, labels, alt/ARIA text, and known-code recovery guidance. `index.html` uses `lang=en`.
- Removed the warehouse default prompt. Empty input keeps Create Draft disabled; a selected image may be submitted with empty instructions, and Korean user text/filenames are preserved unchanged.
- Saved API key and actual successful AI request remain distinct. Offline simulation keeps the existing no-generation gate. Draft acknowledgement and backend-permitted Run gate remain intact.
- Updated R5 browser selectors for the English UI. Added a no-call browser smoke with local JSON responses; it does not represent real provider, backend, or Isaac acceptance.

## Evidence and commands

| Check | Result |
|---|---|
| `pnpm --dir apps\twinpulse-web test` | PASS, 14/14 tests in 2 files |
| `pnpm --dir apps\twinpulse-web build` | PASS, TypeScript and Vite production build |
| `node apps\twinpulse-web\e2e\h1a-browser.mjs` | PASS, English HTML/chrome, disabled empty input, distinct key/live status, Korean text retained, 1366×768, 1920×1080 at 125%, 390×844 with 0 px horizontal overflow, keyboard focus, generation requests 0 |
| `git diff --check -- apps/twinpulse-web` | PASS |

Browser screenshots: `artifacts/runs/h1a-browser-smoke/1366x768.png`, `1920x1080-125.png`, `390x844.png` (local git-ignored evidence).

The first unprivileged test/build attempt failed before loading Vite with Windows sandbox `spawn EPERM`. Running the same repository commands with the tool's elevated process permission allowed verification. The first no-call browser smoke found an ambiguous `Cancel` selector (settings and generation buttons); it was scoped to the settings panel, then passed.

## Limits and next step

- No new paid request, provider generation, installer, actual Isaac session, ROS, or physical robot command ran. No commit or push was made.
- Some server-provided text, including supervisor diagnostic messages, safety reasons, receipts, and model-generated content, remains in its source language; replacing it requires H1b/H2/H3 contract work. The current simulation diagram is explicitly labeled as a status illustration, not the live 3D viewport.
- The next separately authorized step is **H1a-2**: installer/backend visible English wording and English quick-start instructions. Do not advance automatically.
