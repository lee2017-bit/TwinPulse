# Adaptive Architecture A0/A1a — existing scene tool catalog integration

Date: 2026-09-29 KST. Scope: local core/provider refactor and offline verification only.
Robot reported OFF. No SSH, serial, motor, sensor, deployment, paid provider or Isaac call in this change.

## A0 freeze and limits

- Repository HEAD at start: `5c42899a95a0bf2422550bd17df7556a92ab3232`. The working tree was already dirty, including an untracked `site_tools.py`; HEAD does **not** represent the current pre-edit source. Existing files and evidence were preserved.
- Before editing, canonical JSON-Schema SHA-256 (`sort_keys=True`, compact separators, UTF-8): v1 calls `b481aec2ac009d2a61e20cedde69e19b53bf494c209ef00d1eb2eccd4896a131`; v1 required slots `bf2c5a37ef18679ba001924fc7b99b757832acef78133d0ae8b6d2f750538213`; v2 `b1599ff2b94900ce624e9560d432032c8a7f6d7d76bb8a31da23aa49bb243160`. All three remained byte-equivalent under that canonicalization after the refactor.
- Golden executable fixtures pinned in `test_tool_catalog_compat.py`: v1 ordered five calls → 17 expanded objects, plan digest `c8fc953804d944e5f50679ea52cb5a95fbd4767b5208a7e351904fa57b52515e`, bundle digest `756e710786bb6a1e71ddb7f7147c91fb2bc939538ff54d63dfe8a9204d6bbfc8`; v2 scene-only and evidenced box site digests are pinned there. These fixture digests were calculated after the refactor, whereas the three schema digests above were captured before editing. They are regression locks, not proof of a full pre-edit source snapshot.
- Stable intentional differences retained: v1 required-slots provider format is adapted into ordered core calls; v1 requires driven robot plus task whereas v2 can be scene-only; v2 provider schema requires call evidence for newly generated responses but persisted pre-H3a v2 drafts may have `call_evidence=None`; semantic geometry/overlap, finite numeric, object-count and route checks remain local code rather than JSON Schema. These were not silently reconciled.
- **A0 PARTIAL:** a complete pre-edit dirty-file hash manifest was not captured before the first edit, so this condition cannot honestly be marked PASS. The source SHA-256 values below are post-edit. Bedroom/74-frame scan/room-goal/stop/mission fixtures were not newly frozen in this pass; prior records remain historical and physical gates unchanged.

## A1a product changes

- Added `twinpulse_core/tool_catalog.py`: ordered versioned definitions of the existing eight v1 tools and v2-only box, their domains, strict call schemas and names of trusted local static handlers. No dynamic plugin registration or provider-controlled execution path.
- Existing core v1/v2 allowlists and local static dispatch now use that catalog. Existing builder methods and all semantic validators remain in place; robot/task handling, v2 box builder and v1 route resolver retain their prior owners.
- Provider v1/v2 JSON Schemas now take call definitions from the same core catalog. Required-slot formatting and per-call evidence stay in provider. Public schema functions, plan types, revision strings and serialization were not changed.
- A compatibility test pins v1/v2 schema digests, tool order, handler availability, v1 bundle and v2 site digests, and unknown tool/over-limit/bool/NaN rejection. This is connected to the actual provider→core path, not a parallel test-only registry.

Current changed-source SHA-256 (post-edit):

| File | SHA-256 |
|---|---|
| `scene_tools.py` | `6A642EC9D11AC42234B325F2E7E4B0EAABEA184F78743B29D8957644605058C4` |
| `site_tools.py` | `814AA41B2232B92821EC1C0B8A323657A13BDE924AD22CA954B15B8198789AB1` |
| `tool_catalog.py` | `BE95A9FBB609FC74825BC6588C93DA5D767BE71F7741BDC69317A5FCD7536B93` |
| provider `schema.py` | `2EA75A69AC5D33BA86355A94A48397DF6CDA2DE7C4DA814634AE3DB94F7E37FC` |

## Verification

1. Focused core/provider/site tests before the final negative-test addition: `54 passed`; catalog compatibility after addition: `5 passed, 2 subtests passed`. Provider discovery before the addition: 36 passed.
2. `scripts/verify_twinpulse.ps1 -SkipIsaac` initially failed during offline scan/report tests at Windows temp `PermissionError [WinError 5]`; a second sandboxed attempt with workspace TEMP/TMP failed the same way. These are environment failures, not a PASS. Unrelated R3 application standalone also reproduced temp access failures (6 errors of 9 tests).
3. An approved normal-permission rerun of the same `-SkipIsaac` verifier completed with `TWINPULSE_VERIFY_RESULT=PASS`: [immutable run folder](../../artifacts/runs/20260929-022715/), core 170, provider and integration groups, Web 123/123 and production build. The small negative-test addition above was run separately afterward; full verifier was not repeated after that addition.
4. Actual Isaac/physics and physical robot testing: **NOT_RUN**. Saved/synthetic fixtures and local validation are not physical acceptance. Previous real stop-test FAIL and live mission/calibration/deployment locks remain unchanged.

## Next gate

A1a offline compatibility is supported, but A0 remains PARTIAL because no complete pre-edit dirty snapshot exists. A1b must not infer engine capability, runtime readiness or physical authority from this catalog pass. Verify the next capability descriptor against actual existing adapter behavior and preserve v1 +X/v2 goal semantics until a separately validated change.
