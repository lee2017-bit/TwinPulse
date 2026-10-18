# TwinPulse SIM alpha — 2026-10-19

This is a checkpoint in the **existing private repository**, not a public launch or a physical-robot qualification. Existing photos, user projects, credentials and raw sensor histories are not uploaded. The older October18 archive remains unchanged.

## This build

- Product: `0.1.0a1`, development channel.
- Installed build: `20261018T223143Z-307ba690d100`.
- Exact packaged source-manifest SHA256: `307ba690d1002b5ec59e3f8b3bae788093fda6e2eaa160acaa9a20da67bc36c8`.
- Windows ZIP: `188992874` bytes, SHA256 `2ebe556f9bf5be5ef3575fd93acc2779ec9bb624dba4f5d6781687a3461be039`.
- ZIP contains TwinPulse, not Isaac Sim/Kit, ROS or model weights. Existing compatible Isaac installation and user API configuration remain prerequisites. Unsigned local alpha; no clean-PC qualification is claimed.

Extract the ZIP and use its normal `Start-TwinPulse.cmd`. Keep existing user data outside the extracted package. Test automation is explicit opt-in; ordinary Start was verified with no debugging listener.

## Changes and actual acceptance

The default Twin robot label is now a small connection dot and name, with no shaded background, border, shadow, battery subline or leader overlay. Select the name or the robot's current projected area to open status and manual/chat controls in the bottom dock. Projected-area selection is not mesh picking, localization or permission to move. All existing freshness, revision, connection and applied-Stop checks remain.

Same installed Electron Test BrowserWindow + real Flash/Nemotron + Isaac:

| Journey | Result |
| --- | --- |
| New scene, two SIM robots, name/body selection, five renderer sizes, four directions, 60-second hold, chat90°, single360° scan, obstacle stop, Stop all, separate fault window, export and Exit | 32 steps PASS |
| Cold scene/definitions/history restoration, no restored authority, explicit SIM controls and separate delayed-ACK trial | 13 steps PASS |
| Exact chat/scene/operation linkage, actual scene edit, Undo, project switch | 8 steps PASS |
| Cold operation history and original physical-failure provenance without reconnecting | 4 steps PASS |
| Normal Start, duplicate Start reuse, native AltF4, restart, native AltF4 and owned cleanup | PASS;41.120s /56.559s engine readiness, debug listener0 |

245 continuous motion-display observations: maximum displayed-frame age476.977ms, original1s criterion exceeded0. Name labels measured72×16px/transparent/border0/shadow none; both actual canvas body clicks selected the matching robot. Exact final Stop all ACK/new-applied epochs are part of the hash-bound gate. Negative tests rejected a broken Stop and the original failed whole run.

Local detailed evidence: `outputs/robot-name-visibility-20261019/report.html`. Those private raw records are intentionally not Git assets. Gate: `READY_FOR_SUPERVISED_POWERED_TEST`, issues0; it means readiness to BEGIN a supervised test, not permission to bypass live guards or a claim of hardware success.

## Demo video

[Latest SIM demo and Windows ZIP](https://github.com/lee2017-bit/TwinPulse/releases/tag/sim-alpha-2026-10-19-name-visibility)

![Actual new installed UI](https://github.com/lee2017-bit/TwinPulse/blob/68d24dec7b09df9ee7a3e2a628245d2f0f8fb71f/docs/media/twinpulse-sim-20261019.png?raw=true)

`TwinPulse-SIM-Demo-2026-10-19.mp4`:195.200s,3393276bytes, SHA256 `c5bbf99bd96618ea46113cb2253b1b714f8fac791ffda0580d9f02c87b3d7601`.

This is an actual sampled recording of the same installed Test BrowserWindow, not a mockup or native desktop/robot-camera recording. It is a single excerpt from original footage38.5–234.0s, starting during generation and ending before physical setup/fault injection. No speedup, interpolated motion, replacement success responses or music. The source preserves original frame timestamps; the four full local recordings were separately clock-checked. Observed static holds are not proof of unseen movement between samples. The original full recording stays local.

Source project `chat_mveeoshk_2c1b20fc`; fresh launch `cfce7fc4cbf64826814f293dfc81c07d`; lineage operation `ebf442955b6a4e3ea8916decbf045b3e`; original synthetic text SHA256 `bea283424cf097c3166916b9f2f0279507d0bd2928f1030bc666c21f7798b4c2`. No personal photograph was sent for this run.

## Limits retained

Physical Pi load/storage, sensing, braking/driving and world alignment are NOT_RUN because the robot was OFF. Strict tracking/stall may still be INCONCLUSIVE on hardware. Full native Windows control, Explorer double-click, OS clipboard, actual DPI changes, another PC and new photo-quality acceptance are NOT_RUN. Normal native graphics capture timed out; fresh AX text confirmed authenticated readiness and native AltF4 closed both sessions, with separately observed PID/lock/port cleanup. Full interaction used the same installed opt-in Test window, not a separate Chrome/product mutation API.

Historical native access violation, startup timeout, ordinary drive abort and one1014.789ms display sample remain UNKNOWN root-cause risks. New full passes do not erase or explain those failures. The separate repository-wide license/header verifier still rejects an unchanged existing `model-library.css` missing-header condition; full public-distribution clearance is **not** asserted. Original third-party notices are retained. Do not change repository visibility based on this checkpoint.

This run:5 real provider HTTP requests, estimatedUSD0.0451653, new unknownUSD0. Additional50 campaign totalUSD2.2043013, remainingUSD47.7956987. The earlier20 campaign remains separate and unchanged. Estimates are not provider invoices.
