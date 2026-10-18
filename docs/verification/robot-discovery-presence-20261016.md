# Robot discovery presence — 2026-10-16

## Verdict

Actual installed UI separation/expiry/manual selection/cold restart PASS in scope. **Powered TurtleBot3 discovery, advertised-name match, ON/OFF/IP-change and SSH/sensors NOT_RUN.** No fake service advertisement or product fixture was substituted into acceptance. Actual searches observed0network responses and2OS-remembered Bluetooth entries, shown separately.

## Frozen candidate and actual runs

- Release `20261016T004925Z-cb617b49c9b9`; source SHA `cb617b49c9b9d4c22030914c8cf519ac325f0852b855917a204e0b95c729bdf8`; ZIP SHA `f67a2f3bc3c1b7dca23fadc1a03d5d2b576f2460c13d929ebc7482b3675b759f`.
- Same installed Start (execution tool, not Explorer double-click), actual Electron44.7.2/Chromium152 BrowserWindow via per-launch loopback CDP. No substitute Chrome/context/auth injection/direct product mutations/fixed model outputs.
- ui01:7PASS — real Isaac ready, saved names/selection, explicit search/inventory separation, actual30s expiry+refresh, manual draft with no guessed address, local PC6ready/selection/menu reopening, visible Exit. Launch `3a45e508cccf4ce8b37a40f14ca92852`, execution `4671037c61204f3fa3118c1845b8c480`. Actions discover/discover/prepare/select/select.
- ui02cold:5PASS — real Isaac, saved names/selection, no old/implicit discovery, explicit search/inventory display, visible Exit. Launch `20d8c01c3ca841deb2e364e459aeaebb`, execution `18900c45c121427f8150bd32b5f8048b`. Action discover only.
- Both HTTP/pageerror0 and matching `owned_processes_stopped=true` cleanup receipts. Connect/SSH/model HTTP0, USD0. No register or new chat in this task. UI capture source/data are local/private.
- Output and actual installed package each verified1,456files; manifest simulation/robot_observation=true, physical_robot=false. Real control/collection remains disabled.

## Contract and review

`robot_discovery.py` separates network replies from OS inventory, preserves advertised display case, uses receipt-time TTL/withdrawals and exact live PTR/SRV/A chain. Registered names can match address/hostname+port for display only; no credentials/adapter inheritance, automatic selection, endpoint update or identity claim. Duplicate matches remain explicit. Server monotonic and client request-start timers prevent stale action after transit/poll failure/tab suspension. Expired observations remain private until the next search so they are unknown rather than incorrectly not_seen. Search absence never means power-off. Existing run-ID/sequence guards retained.

Astra xhigh1 read-only review found3P2 (old IP TTL chain, in-transit stale revival, expired-observation misclassification); fixed and re-reviewed with no additional P1/P2 in scope. Final Python48/Web69/TypeScript/Vite PASS are supplementary. First Web timer regression had1FAIL because fake clocks were installed after rendering; corrected test setup before render. That test-harness failure is not erased or called product acceptance.

## Preservation and remaining work

Original1,507files/83providerledgers/3robotrecords unchanged, original selection restored, new registration/project files0. Protected historical UNKNOWN-inclusive USD6.8918946/20 unchanged. No new dependencies/system or robot settings/Cloud/Git commit/push/public distribution. Initial previous normal17 shutdown was cooperative operational cleanup, not counted as UI Exit.

Actual robot must be powered, network-ready and advertising a supported service; this task did not install/configure robot advertising. If no advertisement, manual saved selection/Check connection remains available. Actual powered discovery/name/ON-OFF/IP-change/authentication/sensors, same-room survey/alignment and previous photo/whole-generation/nativeOS/clean-PC gates are still unverified. [One report with all actual screens/IDs/remaining work](../../outputs/robot-discovery-presence-20261016/report.html).

Final ordinary debug-off startup restored: launch `db65d8e294204bbb8da9de0b810b97fb`, execution `7eefb8c7b26f4a82938e036038a7e96d`, owner5596/backend9128/Isaac1304/Desktop13016. Authenticated current Isaac ready, no remote-debugging switch/19222listener. App left running. Report12embedded screenshots all decode; desktop1280/mobile390 no horizontal overflow; actual rendered report inspected. Report-only headless QA is separate from installed acceptance. `git diff --check` PASS; final data preservation re-audit exact. See `outputs/robot-discovery-presence-20261016/final-audit.json`.
