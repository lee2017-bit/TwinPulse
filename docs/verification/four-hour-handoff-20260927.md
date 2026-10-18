# Four-hour preparation handoff snapshot — 2026-09-27 16:10 KST

## Result

The current [local result page](../../artifacts/four-hour-handoff-20260927-final/index.html)
opens with the robot OFF, without a running backend or network. It separates
actual stored native data, historical actual Isaac native import, and synthetic
combined App-to-Isaac scene application. This is an interim snapshot inside the
13:46–17:45 approved window, not a claim that the physical demo is complete or
that the scheduled work has stopped.

`scripts/summarize_four_hour_prep.py` takes four explicit run directories. It does
not find the newest PASS, replace failures, execute their scripts, read arbitrary
source paths from JSON, start a service or contact the robot. All evidence reads
are bounded and resolved inside the repository; JSON rejects duplicates and
nonfinite constants. Output must be a new direct child of `artifacts`.

Nine checks bind the original raw/nodes/photos and native bundle roundtrip,
current browser source/build hashes, exact combined six/native nine stages,
data boundaries, no physical activity and explicit regression provenance. Three
native USD frames are recomputed and compared byte-for-byte with the historical
Isaac import; screenshot hashes are checked. The latest App's final USD download
matches that historical import. **No new native Isaac run is claimed.**

The result distinguishes `physical_demo_ready=false`, `motion_authorized=false`,
`physical_stop=FAIL_UNCHANGED`, `world_alignment=UNVERIFIED` and live battery
UNKNOWN. A failed evidence check produces a failure-only page, not a success
narrative. This is local traceability, not a signed attestation or new hardware
verification. The combined synthetic stage is hashed, not executed by the
summary tool; original run receipts remain available in its source record.

## Verification

- Eight new synthetic verifier tests PASS: expected boundaries/counts, changed
  code binding, mislabeled data/extra Run, changed historical USD/capture,
  missing run, duplicate/nonfinite JSON, wrong regression directory, UTF16 log
  and missing stage. Test captures/raw/photos are synthetic file fixtures.
- Full regression `artifacts/four-hour-handoff-regression-20260927-r1/manifest.json`
  and sibling `.log`: **351 Python /56 Web /TypeScript /production build PASS**.
  Groups138+95+33+9+9+10+46+11. The verifier tests are now included in the standard
  offline integration group. No runtime production logic was changed this turn.
- Final `summary.json`: all nine checks PASS; source/build hashes still match
  combined actual Isaac run `derived-combined-20260927-r2` and actual saved-native
  App `derived-combined-native-20260927-final` after the production rebuild.
- Historical native runtime source: `native-3d-isaac-20260927-r3`, frames0/37/73.
  No fabricated robot/world coordinate transform or recreated room geometry.
- Existing static-page Playwright QA reused unchanged: final `page-qa.json` PASS,
  every local link exists, three images decode, desktop1280/mobile390 have no
  horizontal page overflow, zero external requests or page errors. Full desktop
  and mobile captures visually inspected; source images clickable at full size.
- `git -c core.safecrlf=false diff --check` PASS. Preliminary handoff r1 preserved
  (old343 count); final page binds the new351 full regression. No failed runtime
  was hidden and prior reproduced failures remain in their named artifacts.

Reproduction with existing local Python and new output directory:

```powershell
.venv\Scripts\python.exe scripts\summarize_four_hour_prep.py --combined artifacts\derived-combined-20260927-r2 --native artifacts\derived-combined-native-20260927-final --isaac artifacts\native-3d-isaac-20260927-r3 --regression artifacts\four-hour-handoff-regression-20260927-r1 --output artifacts\new-four-hour-handoff
node apps/twinpulse-web/e2e/native-handoff-page.mjs artifacts/new-four-hour-handoff
```

## Remaining work

Robot remains OFF by user report, with no new connection or battery read. Real
native/base/world alignment and handedness, original stop qualification FAIL,
Burger physical mission integration and full physical demo remain open. The
next-session checklist keeps a single approved read-only check separate from
stationary coordinate evidence and separately authorized observed motion.

Next useful offline increment: inspect/test actual product disconnect and lease
loss without Run or any physical connection. Do not consume the rest of the
window by rerunning already-passed geometry. At17:45 stop new implementation,
verify current handoff freshness and pause the existing heartbeat.
