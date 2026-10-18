# Derived review — combined browser to actual Isaac, 2026-09-27

## Result and scope

At15:47KST the combined **actual React UI → authenticated loopback API →
CommandBroker → production BridgeClient → actual isolated Isaac adapter/compiler
→ HTTP receipt/snapshot → UI confirmation** passed six stages. Source and
corrected scenes are explicitly synthetic fixtures, not a reconstruction of the
user's room. No robot connection, provider request, physics play or physical
qualification occurred. The original physical stopping FAIL remains unchanged.

## Integration defect found and corrected

The first combined run reproduced a first-build deadlock: v2 Build eligibility
requires the engine's `build_site_scene` permission, that permission requires a
control lease, and previously the App acquired the lease only inside the disabled
Build handler. Earlier fixture tests supplied a lease; separate UI checks had no
engine, so neither exposed the complete dependency cycle.

The scene review now provides **Acquire scene control**. This explicit action
requests the existing authenticated lease only; it neither acknowledges a draft
nor submits an engine command. It is disabled without a current stage and v2
capability. Existing ownership conflicts and acquisition errors remain failures.
Build still waits for engine permissions and a fresh scene acknowledgement.
Neither backend acceptance nor engine lease/Run gates was relaxed.

Four new React cases cover success, rejection, disconnected engine and unsupported
capability. All assert no implicit acknowledgement or build. The existing lease
renewal loop is reused. No automatic acquisition on page load was added.

## Evidence

- `artifacts/derived-combined-20260927-r2/result.json`: PASS, actual Isaac exit0.
  `browser-result.json`: six stages, exactly two `build_site_scene` requests,
  zero external browser requests/page errors. The production bridge, not test
  code, bootstraps the engine, receives commands and posts receipts/snapshots.
  No broker state is manually injected. An adapter wrapper observes/validates
  the two known commands and calls the actual implementation unchanged.
- Source wall(1,1,.5) and derived wall(1.1,1.1,.5) checked against actual USD
  attributes and compiler fingerprints. Original initialized project bytes are
  unchanged; unrelated `/ExternalKeep` survives. No Robot/Task prim or Run
  permission. The timeline is checked throughout the browser loop.
- The browser acquires control without acknowledgement/build, reviews and builds
  the original, adopts the derived record, reviews again and builds it, sees
  **Completed and confirmed**, checks Run disabled, then explicitly restores the
  saved record and verifies acknowledgement is cleared without another command.
- `combined-desktop.png` / `combined-mobile.png` visually reviewed; mobile page
  has no horizontal overflow (the geometry table retains its own scroll area).
  `synthetic-derived-stage.usda` is the final isolated stage, not physical data.
- `artifacts/derived-combined-regression-20260927-r1/manifest.json` and sibling
  `.log`: full **343 Python /56 Web /TypeScript /production build PASS**.
  Python groups138+87+33+9+9+10+46+11. This regression skips Isaac; the separate
  combined run above is the actual Isaac evidence.
- `derived-combined-noengine-20260927-final`: existing synthetic no-engine App
  five stages PASS; missing engine still cannot build after acknowledgement.
- `derived-combined-native-20260927-final`: actual saved-native App nine stages
  PASS, no live sensor, photo/frame/axis/export provenance retained. This is
  separate from the combined synthetic geometry test.
- Combined source/build hashes match current files after full rebuild; originals
  and failures retained. `git -c core.safecrlf=false diff --check` PASS.

Reproduce with existing tools and a new output directory:

```powershell
C:\isaacsim\python.bat scripts\rehearse_derived_isaac.py --output artifacts\new-combined-derived-run
```

The runner uses a new local backend/project/stage and its own Chrome child. It
does not start the Extension UI, restore a user project, use stored credentials,
or reuse any existing backend/Isaac process. Ephemeral credentials stay in memory
and the owned child environment, never in saved evidence. Local runtime access
required approved execution; no installation or permission workaround was used.

## Failed attempts retained

- `derived-combined-20260927-r1`: FAIL at source Build (disabled after15s), zero
  commands; this is the reproduced lease dependency bug, not an ignored timeout.
- `derived-combined-web-20260927-r1.log`:55PASS/1FAIL because the new rejection
  test expected a raw Error message while the App intentionally displays its
  generic sanitized error. Corrected expectation; all56 then PASS in r2 and full
  regression. Product error handling was not changed to satisfy the test.
- Initial static inspection caught a verification hash path named `compiler.py`;
  corrected to existing `scene_compiler.py` before the first Isaac run.

## Next / remaining

Combined synthetic scene application is now verified, replacing the prior
separate-boundary limitation. It does **not** qualify real native/base/world TF,
physical clearances, stop behavior or a D2 physical mission. Saved photo direction
and mirrored display candidates remain hypotheses. Full physical demo remains
incomplete; robot stays user-reported OFF and no new battery reading exists.

Next offline work: consolidate a current source-bound handoff/reproduction page
and review actual disconnected/lease-loss product behavior where useful. Do not
repeat passing geometry as a substitute for missing physical evidence. Continue
only inside the approved17:45KST window, then pause the existing heartbeat.
