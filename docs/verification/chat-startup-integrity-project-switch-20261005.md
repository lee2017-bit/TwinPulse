# Startup integrity and project switching

2026-10-05 · Baseline v1.0.289. The selected offline startup checks, bounded derived-directory preparation and owned project round trip pass. This is not full C1/C2, clean-install, live-provider or physical-demo acceptance.

## Product changes

The launcher now publishes independent static checks for the built Web dependency manifest, nine reviewed Burger asset hashes, the extension module and owned-root contract, and the current Python/Pillow requirements. Existing executable/version, disk and temporary-write checks remain. Each result includes its reason, next action and observation time. The chat checklist distinguishes these snapshots from the current authenticated engine and command-readiness gates; viewer freshness and provider configuration remain separate observations.

Vite emits `twinpulse-build-manifest.json` with SHA256 values for the generated index and JS/CSS. Startup validates the bounded local manifest, its references and file digests. Missing, changed, malformed or unsafe entries are reported without replacing files. This build manifest detects inconsistent built files; it is not a signed distribution or proof of source-to-build authenticity. A missing Web entry point can still prevent opening the Web UI and requires restoring/rebuilding the local package.

The fixed Burger inventory now checks reviewed digests rather than accepting whatever bytes currently occupy the expected nine paths. Its existing dependency-closure/path checks remain, and file sizes are bounded before hashing. Asset mismatch also rejects the existing SIM preparation path, not merely its checklist. The extension check does not import or install Isaac dependencies. A configured Python different from the observed launcher interpreter is explicitly unqualified rather than assumed to have the same packages.

After acquiring its ownership lock, a fresh launcher may create its two derived runtime directories once each. Existing contents are preserved. A file/link collision or denied write is not deleted, retried indefinitely or resolved by changing permissions. Preparation failure releases the launcher lock and starts no child. The fixed allowlist has two possible attempts per fresh launch; no source-project, setting, asset or Web replacement is an automatic repair. Existing engine retry remains explicit and bounded by the launcher counter, not an automatic repeated launch.

## Final evidence

| Check | Evidence | Result and limit |
| --- | --- | --- |
| Actual chat project round trip | `artifacts/chat-startup-switch-20261005-final2/result.json` | PASS: create empty project, request default→room_two→default, reopen saved room, reload; three fresh owned Isaac/backend sessions, original project bytes unchanged |
| Bound source and build | Same receipt | 20 source and four built Web hashes unchanged before/after execution and matching final files |
| Startup checklist and cleanup | Same receipt and phase screenshots | All 15 static/preparation rows ready; each fresh directory records 1/1 attempt; all three supervisors stopped, owner locks released |
| Motion and generation boundary | Same browser receipts | Zero engine commands, robot writes or generation requests; saved initial v2 room is an explicit local fixture |
| Actual failed start and explicit recovery | `artifacts/chat-startup-recovery-20261005-final2/result.json` | PASS: intentional missing Isaac import attributed to `isaac_import`/`ModuleNotFoundError`; read-only diagnosis/download and one UI retry; fresh session/ticket, remaining retries 2; existing Isaac successfully starts |
| Existing SIM regression | `artifacts/chat-sim-startup-20261005-final/result.json` | PASS: fresh text→Q1→fixture generation→Build/static Burger→explicit PhysX Run/arrival→chat goal/Stop→reload/mobile→explicit Reset; host PASS, source/build hashes match, owned processes stopped |
| Python regressions | Command below | 144 PASS, including malformed/changed/unsafe manifest, asset tampering, independent results, environment uncertainty and no-spawn directory failure |
| Web regressions and build | Existing local pnpm/Vitest/TypeScript/Vite | 37 files / 290 PASS; build PASS, existing >500 kB warning remains |
| Existing six browser/API cases | `artifacts/c1-chat-20261005-v289-final/verification.json` | Image, text, REAL selection, failure, cancellation and saved-edit cases PASS; explicit fixtures, not physical or new inference acceptance |

Project switching deliberately sends no Build. The host's historical scene/capture verdict is consequently **FAIL**, with zero prims and capture NOT_RUN; the raw verdict is preserved. The tested startup scope is authenticated connected idle state, zero movement and complete owned cleanup. It is not converted into a scene PASS. The harness exercises production start/monitor/stop and actual Web/API requests, while controlled browser bootstraps replace native new-window opening. Native launcher-window handoff and another PC remain unaccepted here.

The final SIM regression uses the installed Isaac/PhysX/rendering, but generation is only the declared v2 fixture. The photo journey accepted in v288 is historical; this increment reruns fresh text and existing fixture image/API cases, not new LLM photo interpretation. Command-readiness rows include permitted-command gates: an untouched idle stage may advertise a feature while reporting `runtime_command_unavailable` before review/control ownership. File presence is not motion approval.

## Failure records and reproduction

The new tests initially failed because the package checklist and bounded preparation functions did not exist. The first build exposed absent Node type declarations; WebCrypto uses the existing runtime without adding a package. Sandbox Vite child creation returned EPERM; reviewed scoped local execution then passed, with no denial bypass. An initial project rehearsal incorrectly applied the legacy scene/capture PASS requirement to a no-Build startup test; `chat-startup-switch-20261005-01` remains FAIL. The intermediate `...-final` predates the final source-binding guard; only `...-final2` is final project acceptance.

```powershell
python -m unittest tests.integration.test_chat_startup_checks tests.integration.test_r6_process_manager tests.integration.test_simulation_goal tests.integration.test_site_simulation tests.integration.test_chat_conversation tests.integration.test_h2b2_site_review
pnpm test
pnpm build
python scripts/verify_chat_project_switch.py artifacts/<fresh-output>
python scripts/verify_startup_failure_browser.py --artifact-dir artifacts/<fresh-recovery-output> --recovery-isaac C:\isaacsim\python.bat
python scripts/verify_chat_sim_journey.py artifacts/<fresh-sim-output> --case text
python scripts/verify_chat_c1.py --output artifacts/<fresh-regression-output>
```

Run pnpm from `apps/twinpulse-web`; use the existing qualified local Python. No dependency installation is implied. Base HEAD remains `5c42899a95a0bf2422550bd17df7556a92ab3232` with pre-existing dirty changes preserved. This increment changes startup checks, fixed SIM inventory, launcher preparation/status, API display sanitization, Web checklist/types/build manifest and focused tests/harnesses. It does not change scene v1/v2 serialization, original asset/raw files, physical stop/freshness/segment/speed/budget gates or real mission locks.

## Remaining sequence

1. Broaden actual running-engine failure, transactional scene rollback and receipt-loss acceptance, beyond startup failure and explicit SIM Reset.
2. Broaden scene/robot diversity and natural-language generation/staging acceptance. Current bounded offline goals and one fixed Burger are not a general LLM interpreter or robot catalog.
3. Complete the prerequisite matrix and packaging/new-window/other-PC acceptance. Current explicit provider configuration does not prove a new paid generation call; unsupported installed dependencies remain a reported action, not an automatic installer.
4. Connect and accept C3–C6 REAL chat qualification, survey/correction, exact-route confirmation, five-second summaries and loop tasks. Existing real-photo model mismatch, measured profile/coordinates and field requirements remain unresolved.

C1/C2 PARTIAL; whole-demo readiness=false. Immediate code work above does not require robot power. Robot/SSH/serial/sensors/motors/power/deployment/paid calls/install/system settings/commit/push/new agents: zero. All test-owned processes stopped; existing heartbeat remains PAUSED. Reverting only this increment must preserve the earlier dirty work and historical evidence.
