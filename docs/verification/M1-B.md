# M1-B verification — Extension, scene, and AGV

- Date: 2026-09-12
- Status: PASS (local limited-runtime acceptance)
- Runtime: Isaac Sim 6.0.1-rc.7, Kit 110.1.2, Python 3.12.13
- Mode: headless MinimalRendering, CPU PhysX, 60Hz
- Extension: `twinpulse.extension-0.1.0`
- Evidence log: `C:\isaacsim\kit\logs\Kit\Isaac-Sim Python\6.0\kit_20260912_233617.log`

Command:

```powershell
C:\isaacsim\python.bat scripts\verify_m1_extension.py
```

## Final acceptance result

The final result was `TWINPULSE_M1_RESULT.status=PASS`.

| Check | Result |
|---|---|
| Fixed 3D scene | 22 owned prims under `/World/TwinPulse` |
| Idempotent compile | first/second count 22/22 in all lifecycle cycles |
| AGV physics movement | 0.095361m planar movement in each of 3 cycles |
| Goal tolerance | 0.024651m planar error, limit 0.025m |
| Ground/contact height | 0.211652m, accepted range 0–0.30m |
| Pause drift | 0m in all 3 cycles |
| Reset position error | 0m in all 3 cycles |
| Extension lifecycle | enable/disable 3/3 PASS |
| Physics subscription cleanup | inactive after every shutdown |
| PhysX/CUDA/device-loss/non-uniform-scale errors | none in final log |

The local Kit registry attempted an online index sync and logged two connection errors because the registry endpoint was unavailable. All declared dependencies were already local, the Extension loaded, and every local acceptance check passed. This is recorded as a network-registry limitation, not a physics or Extension failure.

During the first disable in the verification harness, Kit warned that the Extension object was still referenced by Python verification frames. The actual `on_shutdown` ran, the UI window was destroyed, and the physics subscription was inactive after all three shutdowns. This frame-retention warning is recorded for follow-up in an interactive UI test; it is not treated as callback accumulation.

## Failure history retained

1. Replacing the complete owned root expired SimulationManager's PhysicsScene reference. The compiler now preserves an already-known fixture and refuses unknown owned-root content.
2. Deleting/recreating Robot during reset invalidated tensor views. Reset now uses timeline stop and does not replace the articulation.
3. USD authoring pose was initially used as the runtime measurement. Live validation now uses the articulation physics pose and separates planar XY goal error from Z contact height.

## Not covered

- Visible-window visual inspection and complex RTX rendering on this underspecified PC.
- Image/natural-language input, LLM provider, ROS2, Isaac Lab, cloud GPU, and physical AGV.
- Arbitrary scene revisions or obstacle-aware planning; these are later milestones.
