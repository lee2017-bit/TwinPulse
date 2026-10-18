# D3/D5 first slice — stored stationary scan contract and replay

2026-09-27 03:14 KST. **OFFLINE CONTRACT/PROJECTION TESTED SCOPE PASS**.
This is not D3/D5 completion, automatic alignment, a scene update, or a physical demo.
Robot access, SSH, serial, sensor/motor commands, deployment, actual Isaac and paid
calls: **NOT_RUN**. The original physical settling failure (122ms < 200ms) is unchanged.

## Implemented

- Pure `twinpulse_core.scan_recording`: immutable recording/frame/SE(2) transform
  contracts; session, clock, site, scene revision and robot-profile binding.
- Strict internal `scan-recording-1.0` JSON, not a ROS LaserScan format/decoder.
  SI metres/radians, right-handed x-forward/y-left/z-up; sensor→world direction
  explicit. Caller supplies independently selected site/scene/profile identities.
- 4 MiB input limit, 32 frames, 4096 beams/frame, at most2048 preview points.
  Byte limit applies at file/JSON entry; typed construction has frame/beam bounds.
  Duplicate/unknown fields, non-finite values, booleans-as-numbers, invalid ranges,
  angular spans >one revolution, reversed/nonmonotonic time, mixed clock/frame,
  stale/wrong-direction transforms and unsupported conventions are rejected.
- `null` represents a missing/invalid/occluded return. It contributes neither a
  point nor free-space evidence. No hidden wall deletion, occupancy or height guess.
- Deterministic projection preserves frame/beam index and timestamp. Global stride
  sampling is for review only, not a full sensor map; small frames may be skipped.
- Provenance labels synthetic/simulation/recorded_sensor remain **unverified claims**.
  Every result retains source_verified=false, alignment_verified=false,
  motion_authorized=false, demo_ready=false, physical_validation=NOT_RUN.
- Local-file CLI `scripts/replay_saved_scan.py`; output exclusively creates a new
  JSON file, never overwrites an existing result. No transport/scene/engine mutation.
- Integrated every core test file and saved scan/report tests into the existing
  one-command verifier. Fixed the prior report test fixture import for the verifier's
  dotted-module invocation (the earlier discover-only invocation had already passed).

## Important limitations

`stationary_snapshot` and zero per-ray time increment are declarations. This code
cannot prove the robot or sensor was stationary and does not compensate rolling
acquisition/motion. A future real adapter must establish these conditions or add
deskew. It must explicitly normalize ROS invalid ranges and units, not silently
label raw data stationary. Integer ns are session clock values, not necessarily UTC.

The fixed50ms maximum transform timestamp skew is an **input synchronization bound**,
not measured LiDAR accuracy, an alignment residual tolerance or a physical acceptance
result. Matching stamps/digests do not prove transforms, calibration, scale, authorship
or scene identity are truthful. Automatic landmark fitting/ambiguity/outlier rejection,
reviewed XY corrections/undo, App/Isaac overlays and map/mission invalidation are next.
No real stored LaserScan with validated TF was available; the fixture is synthetic.

## Evidence

Full command: `powershell -File scripts/verify_twinpulse.ps1 -SkipIsaac`

- [Manifest](../../artifacts/runs/20260927-031258/manifest.json): PASS; Isaac NOT_RUN.
- [Full console](../../artifacts/runs/20260927-031258/verification-console.txt).
- Python190 tests: core68 (including new scan15), scan CLI3+report12,
  provider33, R1=9, R3=9, R4=6, R5/S2/S3=39, process-manager11.
- Web23 tests + TypeScript/Vite build PASS.
- [Synthetic fixture](../../fixtures/scan/synthetic-stationary.json),
  [replayed preview](../../artifacts/scan-replay-20260927-offline.json).
- Known sensor translation(2m,3m), yaw+90deg, beam ranges1m/2m/null/3m
  project to(2,4)/(0,3)/(5,3) within floating-point precision. Three valid, one invalid.
- Wrong site rejected before output; existing output unchanged on second invocation.
- Initial CLI tests encountered Windows sandbox temp-directory ACL failures. The
  permitted local full-verifier execution then passed all three CLI tests; this was
  an execution-permission difference, not relaxed validation.
- A subsequent isolated scan-test invocation exposed reliance on another test's
  source-path setup. Added explicit local source-path setup; isolated15 and full
  core68 tests passed again. Production geometry/validation was unchanged.

## Reproduce (repository root, PowerShell)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s packages/twinpulse_core/tests -p 'test_*.py'
.\.venv\Scripts\python.exe -m unittest -v tests.integration.test_scan_replay_cli
.\.venv\Scripts\python.exe scripts/replay_saved_scan.py fixtures/scan/synthetic-stationary.json --site test_room --scene-revision ('a' * 64) --profile-digest ('b' * 64) --output artifacts/my-new-synthetic-preview.json
```

The a/b digests belong only to this synthetic fixture. Do not reuse them for a real
site. Supply a new output filename for every invocation. This CLI is an offline
developer preparation tool, not the final user's App workflow.
