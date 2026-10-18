# A4 — browser exports and historical three-photo plan evaluation

Status: **offline increments PASS; A4 overall PARTIAL** (2026-09-29 07:52 KST). Robot OFF; no SSH, serial, sensors, motors, deployment, new model/API call or paid cloud resource.

## Browser JSON evidence identity

The preserved old `artifacts/bedroom-mission-browser-20260928-r1/export.json` and old comparison r2 export fail their original canonical Python revisions after JS changed number representation (`0.0` → `0`). They were not rewritten or admitted as authenticated imports.

Current explicit synthetic mission and comparison buttons now call separate authenticated/CSRF `rehearse-export` and `compare-export` endpoints. Each recomputes the fixed record from the still-reviewed source, checks its displayed revision and authority-free fields, then returns Python-serialized JSON text plus SHA-256 of its exact UTF-8 bytes. React verifies revision and byte hash before saving the returned bytes, without `JSON.stringify` of the parsed record. Stale record, missing review, bad shape, missing auth/CSRF are rejected. This adds no Build/Run/lease or robot call.

The actual local Chrome/App rehearsal `artifacts/runs/20260929-browser-exports-r1/result.json` **PASS**: one synthetic mission export and one comparison export; both downloaded files were independently reloaded by Python and retained canonical nested/outer revisions. Browser external requests 0, forbidden robot/engine requests 0, page errors 0; synthetic diagnostic collector 0, original project unchanged. The downloaded files' byte SHA-256 are `cb3b88623e04e2b9a105f7727656c0a74cf1e26910c23660d53cf079020bbb4e` (mission) and `38b2240c66b8f951241f2ded9672a45da269a1feeede4eb21026ebde97ec43534` (comparison). This is a loopback browser with synthetic room, not a physical or Isaac test.

## Stored provider evidence

The historical saved `artifacts/runs/20260924-185750-s2d-replay/stored-provider-results.json` (SHA-256 `f3426a15ce9beeeae19d1fd691b846e70baae24d1d193a8431f6a6fcce6922a8`) contains three different photo fixtures, plans and bundles. A new offline A4 adapter requires exactly the pinned IDs/image SHA/filenames/prompts of `fixtures/m2c/warehouse_images.json`, then reuses the existing `load_replay_fixture` parser and allowlisted tool-registry recompilation. The separate report is `artifacts/runs/20260929-stored-provider-a4-r1/evaluation.json`. Its three tool-validity axes are PASS for **stored locally reparsed/recompiled plans only**; source authentication remains false. It does not infer photographic geometry quality, model reliability, simulator physics, mission result, collision, or physical success.

The saved provider report has no per-fixture usage, token or pricing receipt and no per-fixture wall-clock latency. Its overall start/end timestamps are not a request-latency distribution. Cost is `UNKNOWN`, latency `NOT_MEASURED`, scene fidelity `NOT_MEASURED`, and the fixture partition is `historical_regression_not_held_out`. The existing historical S2-D Isaac replay is separate evidence and is not relabeled as an A4 physics run. Historical M2-D 27/29 FAIL and physical stop FAIL are unchanged.

## Tests and remaining scope

- Focused current export Python 24 PASS, React 15 PASS. New stored-provider adapter 3 PASS, including image/prompt/tool/status mutation rejection and output no-overwrite. Existing M2-D A4 test 1 remains in the full verifier.
- Updated `scripts/verify_twinpulse.ps1` includes both A4 test modules. Final `-SkipIsaac` **PASS**: `artifacts/runs/20260929-075011/manifest.json`, core 176, Web 128, production build PASS. The earlier full pass at `20260929-074212` preceded addition of the A4 verifier group; both runs are preserved. `git diff --check` exit 0.
- Sources: `bedroom_review.py` SHA-256 `45d809d39005a8840424308b756fa2ff52251cbe2e8d8da0f1a662ac91575a48`; `BedroomTwin.tsx` `5a3d0c6657fb3d2f0097ecbf1202b9e9de506d99b461cf25737367d49725f7f4`; `evaluation_report.py` `7240053f7d60ea843d5aa3d28f5973486b829b83f3f5e575886bec7d8b5ecee8`.

Remaining: actual different-room project creation/switch UI and independent sensor/mission refs (A2), photo-ground-truth/held-out fixtures and usage/latency receipts, multiple fixed-condition trials, and genuine simulation/physical axes. A4 cannot drive automatic model routing yet. No measured TF, room-to-odom alignment or live mission authority was created.
