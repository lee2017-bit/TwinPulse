# M2 RobotProfile v2 repair verification

- Date: 2026-09-13 KST
- Host: local Windows 10, Isaac Sim 6.0.1-rc.7, CPU physics, MinimalRendering
- Command: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_twinpulse.ps1`
- Artifact: `artifacts/runs/20260913-205327`

## Result

- Overall automated result: PASS
- Core contracts: 23/23 PASS
- Provider contracts: 8/8 PASS
- Extension lifecycle: 3/3 PASS
- Short run/pause/reset: 3/3 PASS
- Generated scene, implicit fallback rejection, replacement rollback: PASS
- Robot profile metadata: `agv_compact_2wd_caster_v2`
- Driven wheels: 2
- Expected/observed passive support wheels: 2/2; spherical support joints valid
- Generated regression scene: 54 TwinPulse prims

## 6.9 m route

- Runtime state: completed
- Goal error: 0.049306 m
- Maximum cross-track error: 0.000825 m
- Maximum absolute pitch: 0.030598 degrees
- Maximum absolute roll: 0.043333 degrees
- Vertical range: 0.000286 m
- Geometric collision samples: 0/1720

## Limits

MinimalRendering did not capture a screenshot. The collision metric is sampled chassis-footprint overlap against validated scene colliders, not a PhysX contact-impulse trace. One Full-app visual check remains required after restart; the three-image M2-C gate is still open.
