# M2-B source integrity and tool-plan verification

- Date: 2026-09-13 KST
- Host: local Windows 10, Isaac Sim 6.0.1-rc.7
- Scope: local verification plus user-run real-image evidence

## Contract checks

Commands:

```powershell
python -m compileall -q packages extensions\twinpulse.extension\twinpulse scripts
python packages\twinpulse_core\tests\test_contracts.py
python packages\twinpulse_provider\tests\test_provider.py
```

Result:

- Python compilation: PASS
- Core: 20/20 PASS
- Provider: 8/8 PASS
- Covered: allowlist and exact argument contracts, unknown-tool/extra-argument rejection, rack-row expansion, plan persistence serialization and hash tamper rejection, image-first request ordering, strict scene-tool-plan schema, timeout/cancel/provider errors.

The Codex filesystem sandbox prevented a subprocess from creating its temporary persistence directory. Record serialization and integrity were tested, but the actual `%LOCALAPPDATA%` save/reload path remains a user-runtime check.

## Isaac runtime regression

Command:

```powershell
C:\isaacsim\python.bat scripts\verify_m1_extension.py
```

Result: `TWINPULSE_M1_RESULT.status=PASS`

- Three Extension enable/disable cycles: PASS, 28 → 28 sample-fixture prim stability per cycle.
- Three run/pause/reset physics cycles: PASS.
- Allowlisted generated tool plan applied: PASS, 50 TwinPulse-owned prims.
- Intentional mid-replacement failure: PASS, previous scene ID/prim count/bundle preserved while the live PhysicsScene remained valid.
- Implicit sample fallback rejected: PASS.
- Settings window, warning window, camera, lights, and goal marker: PASS.
- Long-route closed-loop controller: PASS; 6.9 m route completed with 0.049724 m goal error and 0.005134 m maximum cross-track error.

## Real-provider evidence and remaining gate

The corrected user-run Luna request logged `images=1` and generated `warehouse_aisle_scene_01` with 14 allowlisted tool calls and 59 expanded objects. The generated plan built 134 prims with plan hash prefix `a135a31a65d7`; the same draft was restored after restart. This closes the single-image M2-B provider/source-integrity gate.

The first Run of that long generated route exposed fixed equal-wheel-speed drift. The closed-loop correction now uses live pose/yaw and stops if aisle deviation exceeds 0.20 m. A user-visible saved-draft Build/Run is still required to visually confirm this corrected motion; it needs no new API request. Three distinct image fixtures remain the M2-C gate.
