# Recorded scan positioning in the sensor map

October 4, 2026. The existing App now locates three consecutive recorded scans in a reference built from observed endpoints, independently of the photo-room furniture boxes. Actual preserved recordings produce historical geometric candidates; ambiguous candidates remain rejected. This completes a connected offline positioning diagnostic, not measured room calibration, live relocalization or autonomous driving.

## Product path and source controls

Load a saved session and build its observation map. The new **Find scan position in the sensor map** section lets the user select the same or another saved test session and an original zero-based test frame. **Locate recorded scans · sensor map** calls the authenticated strict-shape `/v1/product/room-localization/sensor-map` API. It shows progress, an explicit failure or candidate, a gray reference cloud, three cyan test scans and an amber historical sensor position. Changing the reference session, observation revision or test selection clears previous results; late responses cannot restore them. A 45-second fetch/body deadline does not automatically retry. Robot power, paid generation and an Isaac connection are unnecessary.

The service requires the current observation revision and epoch, reloads project-bound originals, and checks raw byte identities and nominal sensor geometry before and after search. It saves an exclusive canonical-hashed JSON in `artifacts/sensor-map-localization`, binding the reference and query jobs, raw revisions, boot/release identities, project and observation revision. It revokes any previous photo-position binding and never calls localization acceptance or the physical mission adapter. A changed source/model/epoch, busy worker or missing current map is rejected. Photo geometry is not loaded by this path.

The CLI uses the same service:

```powershell
.venv/Scripts/python.exe -B scripts/review_room_localization.py <reference_job> --sensor-map-query <query_job> --frame <zero_based_index>
```

## Search and test leakage limits

The reference is rebuilt from original scans, not reused from the full cached display map. If raw identities or boot IDs are shared, all reference beam intervals overlapping the selected query interval plus two seconds on either side are excluded. Original frame indices and raw sequence identifiers remain attached to the reference and test evidence. A short recording entirely consumed by this holdout fails rather than matching itself. Different recordings in the same boot also use the overlap check; an empty overlap does not establish independent physical ground truth.

The existing bounded global XY/heading search now scores a 60 mm chamfer distance field seeded by observed 50 mm endpoint bins, not authored wall/furniture polygons. Query global odom coordinates and an old route are not search priors. Query odom is used only for declared-time deskew and relative motion across the three selected scans, whose time span must not exceed one second. The same candidate reference-from-query transform must support all three. Existing 120 mm capped mean and 70% within-150-mm fit criteria remain; a distinct alternative must have at least 25 mm worse mean residual. Missing distinct alternatives or an insufficient margin yields `AMBIGUOUS`, not acceptance.

Bounds limit the reference to 18,000 cells, the distance field to 60,000 cells and coarse search to the existing budget. Search remains approximate and bounded, not exhaustive. Sensor-center checks use the reference search envelope, not obstacle polygons or collision clearance. Missing returns never infer free space. Declared first-ray timing, nominal mounting and odom drift remain unverified. Endpoint residuals are quantized map consistency scores, **not physical position accuracy**.

## Actual preserved recording results

The reference below is `4493be87ef7643ababb661b4a12f0180`, originally 2,318 scans. These are real raw-decoder results, not mock sensor responses.

| Test recording and original frames | Excluded reference scans | Retained reference scans | Supporting test scans | Result | Alternative margin |
|---|---:|---:|---:|---|---:|
| Same recording, 771–773 | 45 | 2,273 | 3 of 3 | Geometric candidate | 99.0 mm |
| `b6cf346718da44b99e7bffe6f7919bbf`, 403–405 | 0 | 2,318 | 3 of 3 | Geometric candidate | 81.5 mm |
| Failed acquisition `1a7f033af112437699ca67aef3438ecb`, 25–27 | 0 | 2,318 | 3 of 3 | Ambiguous | No distinct rival available |
| Same failed acquisition, 1–3 | 0 | 2,318 | 3 of 3 | Ambiguous | No distinct rival available |

The tiny capped residuals in these rows (approximately 1.4, 2.2, 0.3 and 0.6 mm) must not be described as millimeter positioning accuracy. Both recordings share odom-related assumptions, the field is quantized and no surveyed pose was supplied. The failed acquisition remains failed; usable recorded frames do not repair its input deadline, time gaps or final unbracketed scan. Its ambiguous results demonstrate that three supporting scans alone do not establish a unique location.

Requesting that failed recording's final frame 29 was separately rejected with `OFFLINE_LOCALIZATION_REJECTED` and the actual `ODOM_TIME_UNBRACKETED` reason. No candidate was saved for this rejected request and no movement was attempted.

CLI report suffixes are `6e04fde1b2d14f53a60b5431cd368f33`, `46b93ec7bef04b1cbac267a3066c6aef`, `3cc373aed8f14ddbb817c09339b88e06` and `8e08fd695c2841b8aa21f2845988c829`, respectively. The real browser also independently produced the same held-out result with suffix `3c5fb287696e4ddc83414a0483adcf9c`.

## Verification

Related Python regression passed **358 tests and 285 subtests** in `artifacts/sensor-map-regression-20261004-r1.xml`; focused core/App tests passed **23 tests and 19 subtests** in `artifacts/sensor-map-focused-20261004-r1.xml`. Tests cover changed synthetic start/heading with query odom reset to zero, same-raw/same-boot holdout, original-index preservation, short self-recording rejection, inconsistent neighbors, ambiguity, sparse data and resource limits. App tests cover project/raw/model/revision binding, pre/post-search source changes, stale epochs, invalidation, busy rejection, authentication, strict request shape, hashed reports and no goal authority.

The first core run had an import-path collection error, which was corrected. The second exposed an overly strong test expectation: the accurate best synthetic pose still lacked a unique alternative margin. The test now requires that case to remain ambiguous; production thresholds were not relaxed. Both early reports remain preserved as `sensor-map-core-20261004-r1.xml` and `r2.xml`.

All **216 Web tests** passed in `artifacts/sensor-map-web-20261004-r1.json`, including query-change/late-result removal, parent busy-state handling, explicit failure and both fetch/body timeouts. TypeScript and production Vite build passed. Actual Chrome → production Web → authenticated API → actual raw decoder → map → photo comparison → held-out sensor positioning passed in `artifacts/sensor-map-browser-20261004-r1/verification.json`. The browser checks excluded endpoint source indices, source/revision identities, cleared photo candidates, and reference/test session invalidation. Desktop/mobile screenshots were visually inspected and had no horizontal overflow. Counts were zero robot-operation POSTs, zero engine commands, zero external requests and zero page errors. One local snapshot GET had no physical adapter. Original project state and source/build hashes stayed unchanged during the rehearsal.

## Remaining integration

This path yields a historical position in the **reference session initial odom coordinates**, not the photo room or current robot. The next connected task is an explicit evidence-bound relationship between that sensor frame and the photo-room frame, with uncertainty and invalidation rather than treating furniture boxes as measured obstacles. Live first-scan positioning after a new start or hand repositioning, physical timing/mount validation, room geometry correction and collision-protected autonomous acceptance remain unimplemented or unverified. The prior communication repair remains undeployed and the requested 0.08 m/s remains unapplied. No new robot lap, connection, deployment or stop test was requested in this increment.
