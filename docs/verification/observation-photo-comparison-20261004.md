# Saved scan and photo model comparison

October 4, 2026. The existing App now compares verified saved scans with the unchanged authored photo-room model under one fixed transform across multiple times. The search finds very little multiframe support in all three preserved recordings. This is a diagnostic result, not proof of a particular room dimension, sensor error or odom drift. No room correction, localization acceptance or robot action occurred.

## Implemented product path

After building the independent observation map, **Compare with photo 3D · multiple frames** calls an authenticated, strict-shape local API. The service requires the current observation revision, reloads original raw evidence and nominal sensor geometry, checks the room manifest, and rejects changed identities or an invalidated epoch. Raw and model identities are checked again after computation. The result is an exclusive derived JSON under `artifacts/observation-model-comparison`, never an overwrite of recorded bytes or the room recipe.

Four uniformly selected usable historical keyframes seed the existing route-independent matcher. Up to four alternatives per seed are transformed to session odom. Every usable playback keyframe then tests each **same** transform; frames are not individually repositioned to manufacture a fit. Evaluation retains the existing 120 mm capped mean residual and 70% within-150-mm criteria, plus sensor-center plausibility in the authored model. All sampled returns contribute; scoring caps each residual at 500 mm using the existing 60 mm distance field. These numbers are diagnostic outline residuals, not physical position errors or changed stop criteria.

The view overlays up to 16 recorded keyframes on the model's scan-height cross-section, reports how many times support the same transform, and lists per-object nominal vertical intersections and nearest-surface disagreements. Nearest surface attribution is **not object recognition**. Search is bounded, not an exhaustive multiframe optimizer. Even full diagnostic support would not create a room-to-robot binding or motion permission. Existing photo-position candidates are revoked before diagnostics and late results are removed after session/room changes. Requests show progress and precise failures, with a 45-second browser deadline and no automatic retry.

## Results from actual preserved recordings

| Session | Paired original scans | Evaluated playback keyframes | Frames supporting best fixed transform | Weighted capped residual |
|---|---:|---:|---:|---:|
| `4493be87ef7643ababb661b4a12f0180` | 2317 of 2318 | 63 | 0 | 290.1 mm |
| `b6cf346718da44b99e7bffe6f7919bbf` | 1212 of 1213 | 63 | 1 | 207.0 mm |
| `1a7f033af112437699ca67aef3438ecb` | 25 of 30 | 25 | 0 | 253.0 mm |

All three report `MODEL_OR_ODOM_INCONSISTENT` within this bounded search. The failed session remains a failed acquisition session: its four time-gap and one final unbracketed scan are retained by the underlying observation map, not repaired. CLI report IDs are `4493…-5ed1d62de8494f30a08960cd29da6045`, `b6cf…-127e5b2d2c6a4a17bc2015a3eba15f0f` and `1a7f…-65e4d9a0d2d24ca59f0e809d59be9b85`.

The pinned nominal model places the scan plane at 182 mm above the floor. All eleven non-floor photo objects intersect that plane as authored full boxes. Desk/chair lower sections, open undersides, furniture legs and cloth are therefore unresolved modeling questions, not measured occupied polygons. In the first session's best diagnostic hypothesis, only 19 of 63 sensor centers are plausible in the authored model. The nearest left/right wall surfaces also have many large residuals. That attribution depends on an unverified transform; it cannot establish that those physical walls are incorrectly sized. Removing furniture or rescaling the whole room without independent evidence is not justified.

The near photo wall remains deliberately open. Returns outside the model can involve exterior views, incorrect photo dimensions, unverified mount/timing, odom drift or a combination. No one of those causes has been isolated by this increment.

## Verification

Related Python regression passed **349 tests and 270 subtests** in `artifacts/model-comparison-regression-20261004-r2.xml`. The final focused run passed **20 tests and 10 subtests**, additionally including changed coordinate-origin/heading invariance, in `artifacts/model-comparison-focused-20261004-r3.xml`. Synthetic fixtures check fixed-transform consistency, nonfabricated table/leg sections, sparse data, nonfinite values, unchanged originals, source/room/model rejection and epoch invalidation. Fixture PASS is not physical localization acceptance.

All **211 Web tests** passed in `artifacts/model-comparison-all-web-20261004-r2.json`; TypeScript and production Vite build passed. Both transport and body-read timeout cases are covered. A real production browser → authenticated API → real raw decoder → observation map → multiframe model comparison passed in `artifacts/model-comparison-browser-20261004-r1/verification.json`. Desktop/mobile screenshots were inspected, no horizontal overflow was observed, and changing sessions removed both views. The isolated workflow scaffolding is synthetic; the scan and comparison responses are not mocked. Counts were zero robot-operation POSTs, zero engine commands, zero external requests, and zero page errors. The one local status GET used no physical adapter.

The first broad Python command referenced a nonexistent test path and ran zero tests. This was corrected after enumerating the actual test files; no criteria were relaxed. Prior raw failures and derived records remain preserved. Isaac rendering and physical driver behavior were not rerun because no engine geometry or robot source changed.

## Use and remaining work

Restart the PC App, load the saved room and a saved session, build its observation map, then click **Compare with photo 3D · multiple frames**. Robot power and Isaac connection are unnecessary. The CLI equivalent is `.venv/Scripts/python.exe -B scripts/review_room_localization.py <job_id> --compare-model`.

This completes the offline comparison and sensor-section audit, not geometry correction. The next work is a separately evidence-bound sensor model and map-relative multiframe localization, without treating the photo's solid furniture boxes as measured scan obstacles. Actual first-ray timing/order, as-built mounting, metric room geometry, changed-start live acceptance and autonomous collision protection remain unverified. The existing communication repair is still undeployed and 0.08 m/s remains unapplied. The current recordings are sufficient for further offline development; no new lap was requested here.
