# Accepted survey reference and native idle localization

Date: 2026-10-06 KST. Baseline: v1.0.299. Robot OFF; no SSH, serial, sensors, motors, deployment, paid calls, installation or new agents. Existing dirty changes, original measurements, failure history, wire contracts and physical authority locks remain preserved. Heartbeat remains PAUSED.

## Outcome and boundaries

The existing App/chat goal path can select an owned successful survey report as its localization reference, rather than reopening an unrelated legacy map. The existing native observed worker can sample fresh localization with wheels explicitly disabled. Neither saved survey pose nor successful synthetic arrival becomes current physical evidence or motion authorization.

**C4 remains PARTIAL; whole readiness=false.** Production PC-to-robot idle-preview transport, full survey-reference handoff and actual exact-plan Isaac3D receipt are not implemented. Physical Confirm remains locked. Chrome/Isaac/target build/field tests were NOT_RUN this increment. Web source/build were unchanged; the prior v298 build is historical evidence, not a new build acceptance.

## Existing paths connected

1. `survey_reference.py` reopens only an opaque mission/report-SHA key through the existing checked report loader. It verifies current project/source/room, correction ledger/effective geometry, full map hash/reprojected tracking, fit digest/geometry/height and disjoint causal fit/held-out sequences. It retains all selected keyframes and tracking endpoints. It returns no initial pose. The derived alignment wrapper has its own digest and original `source_report_revision`; stored report/map/fit bytes are unchanged.
2. `AutomaticMissionService` uses that reference in readiness and `_prior`. Explicit goal preview and start recheck selected reference identity/alignment against the trusted current-observation source. `ChatInspection.reference` caches only an explicitly selected, owned hash descriptor and validates it on every request. A later completed goal may replace the live job without losing that descriptor. New survey/owner, changed room/report/ledger or missing evidence cannot silently inherit it. Automatic reference restoration after App restart is not implemented.
3. `IdleCurrentEvidence` and existing `RobotObservedFactory` use the existing ROS observation window, reviewed planar binding and tracker. They recheck explicit motor-disabled state and source context before/after processing, retain actual oldest odom/scan sample age, reject backward time or age reaching the unchanged 200ms boundary, and clear candidate state on failure. Slow global matching is only a warm seed; a fresh sample is required afterward. Handoff closes idle sampling/cache while preserving only a tracker seed for the mission's next fresh tick. Independent cleanup invalidates it.
4. Existing remote factory explicitly rejects accepted full survey references with `SURVEY_REFERENCE_REMOTE_FULL_HANDOFF_REQUIRED`. It does not downsample them into the legacy 512-endpoint/16KiB bootstrap scope. Production factory still lacks the qualified idle preview interface and approved-preview remote execution still rejects `REMOTE_IDLE_PREVIEW_HANDOFF_NOT_IMPLEMENTED`. No HTTP endpoint registers an arbitrary observation source.

## Verification on final frozen source

| Check | Result | Scope |
| --- | --- | --- |
| Python selected integration/core suite | 136 PASS, 342.632s | Saved survey/reference, native idle window, current goal/chat/mission/report, remote correction and source identity |
| Web full suite | 316 PASS, 42 files, 23.97s | Existing Vitest/jsdom suite; not actual browser/runtime |
| Actual shared-loop moved start | PASS within the Python suite | Synthetic scan/odom feedback; no saved-pose injection, fresh localization, target arrival/zero, original report bytes unchanged |
| Native observed worker prepare/idle/handoff | PASS within the Python suite | Existing worker/window with synthetic ROS-shaped observations and explicit fixture binding; wheels disabled/no nonzero command; not measured ROS qualification |
| Tampering/failure/ownership/source lifetime | PASS within the Python suite | Wrong hash/map/alignment/project/geometry, missing map/held-out evidence, changed motor/source/clock and closed sampler reject |

Final Python command used `-B -m unittest -q` with: SurveyReferenceTests, IdleCurrentTests, CurrentGoalPreviewTests, ChatGoalTests, ChatConversationTests, SimulationGoalTests, ObservedMissionTests, CurrentEvidenceTests, AutomaticMissionTests, ChatInspectionTests, CurrentRoomVisualTests, test_mission_evidence, test_robot_source_identity, IdleCorrectionGuardTests and RemoteCorrectionTests. Web command: existing `pnpm test` in `apps/twinpulse-web`. Both owned test processes completed with exit code 0.

Temporary-directory/subprocess tests used scoped local execution permission because sandboxed Windows subprocess writes previously returned EACCES; no service/WSL permission workaround was used. Unrelated inaccessible pytest-cache directories were not modified.

### Preserved intermediate failure

An earlier 21-test run had 20 PASS and one native fixture error: `ADAPTIVE_INITIAL_LOCALIZATION_AMBIGUOUS`. A single-position 120-ray synthetic reference was insufficiently distinctive. The fixture was corrected to a denser 480-ray synthetic reference within the unchanged legacy ceiling. Production matcher, observability, stop and timing thresholds were not relaxed. Later focused native tests and the final 136-test suite passed. This is fixture coverage, not evidence that a real room ambiguity has been resolved.

## Source identity and non-deployment

Reviewed robot source changed, so prior source review/qualification cannot authorize the new source silently. No new physical registration or deployment was created. Final hashes recorded after tests were started and while sources remained frozen:

| Source | SHA256 |
| --- | --- |
| `packages/twinpulse_app/src/twinpulse_app/survey_reference.py` | `e9dcb8fd26498cee1d892b6a303950ba0c98ee130e7a099bbced11840286287d` |
| `packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py` | `f5505d5c7f1b54d9b1025ff320143dffa0ac635a4dc9b6dce66b870be058f49c` |
| `packages/twinpulse_robot_safety/observed_runtime.py` | `07614d00e5f89962ba36a878165063ffe023bd5c7cbd10fc01f0c8ea7db1cc17` |
| `tests/integration/test_survey_reference.py` | `35f4b4d41a61b42c7da4485fe4bb444318d3ff8917ab7ed5e25bd2aa70e0a8f0` |
| `tests/integration/test_idle_current_evidence.py` | `5585447120c098bb663574ef9a50ee99365c82b33078fbf9f68ba68bc039e072` |

## Exact next work

1. Add bounded owned full-reference transfer and continuous no-motion current-localization query to the production PC/remote worker path; bind exact report/map/room/owner/boot/release and preview-to-execution handoff. The native sampler implemented here is not that transport. Preserve raw recovery and rejection causes.
2. Connect the exact reviewed goal plan to actual Isaac3D demonstration and stage/engine/plan receipt before physical confirmation. A 2D SVG or fake receipt is not acceptance.
3. Complete goal five-second summaries, persistent C5 Loop and C6 integrated failure/normal acceptance. Keep restart/reconnect non-resumption and independent Stop/Force STOP.
4. Separate C3 reviewed target binary/profile, measured sensor/body evidence and field acceptance remain. The next two code tasks do not require robot power; powering on alone does not complete the demo.
