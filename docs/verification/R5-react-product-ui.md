# R5 React product UI verification

- Date: 2026-09-16 KST
- Result: **PASS for the tested local deterministic vertical slice**
- Canonical run: `artifacts/runs/20260916-235245`
- Boundary: local `127.0.0.1` App/backend plus the real Isaac Sim 6.0.1 managed Extension

## Implemented path

R5 adds `apps/twinpulse-web`, a React/TypeScript product UI served by the same authenticated loopback backend used by the R4 engine bridge. The visible workflow is:

1. upload a PNG/JPEG/WEBP image, select automatic/photo/drawing input kind, and optionally attach an image-bound measurement sidecar;
2. start or cancel an asynchronous generation job and inspect its phase;
3. review the generated draft and explicitly acknowledge the approximate-model warning;
4. build only when the current backend draft revision remains eligible;
5. wait for the Isaac snapshot to report that exact applied revision;
6. use only the currently permitted Build/Run/Pause/Reset/Focus commands.

The UI shows backend, Isaac engine, and live-provider state separately. A saved key or deterministic fixture availability is not labelled as a successful live-provider connection. Backend draft revision and Isaac applied revision remain different fields, and the UI does not claim 3D completion before they match.

The product upload path checks body size, safe filename, content signature, decoded image dimensions/pixel count and declared media type. Measurement JSON uses the provider's strict parser and must identify the attached source image. All JSON routes except the bounded upload route retain the smaller API limit. The browser receives no API key; authentication is bootstrapped from a one-time URL fragment and removed from the address bar.

Python remains authoritative for engine contracts. `scripts/generate_engine_ts.py` produces/checks the TypeScript contract used by the React App. The R4 engine-only backend remains compatible because product workflow/static serving is enabled only when a static root is supplied.

## Automated evidence

The full runner completed with:

```text
TWINPULSE_VERIFY_RESULT=PASS artifact_dir=...\artifacts\runs\20260916-235245
```

The same run passed:

- Core: 24/24
- Provider: 13/13
- R1 integration: 9/9
- R3 application/contracts: 9/9
- R4 bridge/API: 6/6
- R5 product API: 7/7
- React/Vitest: 3/3, including React StrictMode polling
- TypeScript contract drift check and production Vite build
- all preserved actual-Isaac regressions, followed by the R5 browser-to-Isaac E2E

R5 actual result:

| Check | Result |
|---|---|
| Browser stages | authenticated ready → draft reviewed/acknowledged → actual revision applied → Run/Pause → Reset/Focus → responsive/zoom/keyboard |
| Applied revision | backend draft and Isaac snapshot matched |
| Authored stage | 32 TwinPulse-owned prims |
| Runtime states observed | `idle`, `ready`, `running`, `paused` |
| Maximum AGV movement | 0.4123752734 m |
| Final runtime state | `built` after Reset |
| Responsive check | 390×844 Korean UI, horizontal overflow 0 px |
| Accessibility interaction | keyboard focus PASS |

Screenshot evidence:

- `artifacts/runs/20260916-235245/r5-browser/r5-desktop-applied.png`
- `artifacts/runs/20260916-235245/r5-browser/r5-mobile-korean.png`
- `artifacts/runs/20260916-235245/r5-browser/r5-zoom-125.png`

These screenshots and JSON/transcript artifacts are intentionally git-ignored runtime evidence. They were generated automatically; no user screenshot relay was required.

## Regressions caught during R5

- React StrictMode cleanup stopped the only polling loop because the default API client was recreated per render. A module-stable default client and restartable polling lifecycle fixed it; a StrictMode component test now covers the case.
- The E2E initially treated acknowledgement as a conventional writable checkbox although the server owns the acknowledgement state. The test now clicks the action and waits for authoritative backend state.
- Mobile step indicators and Focus completion were initially under-specified. The browser check now selects the completed step unambiguously, waits for the `focus_scene` succeeded receipt, and measures mobile overflow.

## Explicitly not proven

- No fresh paid multimodal provider request was made. Generation in this acceptance is deterministic and local; the live-provider App smoke remains NOT RUN.
- R6 process manager/one-command launcher, browser auto-open, restart/failure recovery, and official Isaac viewport capture are NOT RUN.
- This is loopback-only. It does not authorize remote binding, firewall changes, ROS2/MCP/WebRTC, cloud deployment, package publication, company-PC installation, or physical AGV control.
- The legacy Isaac UI remains available in standalone mode. It was not deleted or silently replaced.
