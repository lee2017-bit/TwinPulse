# Scene-aware robot control and stable Twin UX

Status: ACCEPTED_SCOPED_SIM_AND_PC (2026-10-19), physical navigation/localization
NOT_RUN/unsupported. [Actual final report](../../outputs/scene-robot-ux-20261019/report.html).
Fresh03 37/cold13/edit-Undo-lineage8/history4 whole PASS on installed4e19529056c3;
native normal lifecycle, current SHA gate and original-failure negatives passed.
Both original failed attempts remain unchanged. Main worked sequentially; no shared-file
parallel edits. Frozen previous release307ba690d100 remains a rollback/evidence
reference. No hardware, new dependency, publish or Git push in this request.

## Contracts and ownership

Main owns web RobotFleet/TwinViewport/types/CSS, core pure SIM planner, backend
fleet/parser, Isaac runtime/view capture, validators, tests and acceptance.

- Demonstration and fresh acceptance input use English, with English new UI
  status. Do not destroy or reject saved Korean conversation/Stop support. Full
  automatic response-language following is not claimed by this English-first
  change.
- Keep immutable decoded image and original frame/camera/revision guards. The
  connection dot is placed at the actual composed robot-model projection,
  independently of text-label collision avoidance. Derive model bounds from
  USD, not fixed screen percentages. A crowded label may hide, not drift across
  the room. New projected scan overlay belongs to the same captured frame and
  original scan pose/time; physical unaligned markers do not invent scans.
- Reserve controller/notice/command-result geometry while actions change.
  Actual continuous DOM rect evidence must cover direction changes and normal
  status transitions. Do not fix this by freezing live frames.
- Command panel clearly shows text, request ID and accepted/planning/running/
  arrived/interrupted/failed state from actual service/engine evidence, not only
  an HTTP acceptance toast. Keep independent Stop and original input expiry.
- Scene destination grammar produces a bounded `navigate` intent (target kind,
  nearest selection) from the panel or main chat. SIM resolves actual current
  USD catalog members, selects a reachable stand-off beside—not inside—the
  target, plans with existing bounded grid planner and follows it through the
  existing collision-checked kinematic integrator. Keep source project/revision,
  request/task/operation/connection/motion identities in logs. Missing targets,
  no route, changing scene, timeouts and Stop are terminal and do not teleport,
  silently choose another object or restore motion. Physical destination motion
  remains explicitly unsupported without its verified world binding/adapter;
  do not convert this feature into physical movement authority.
- LiDAR: selected robot only; default latest hit points, optional sparse rays,
  off option. Explicit source/age/point count and SIM-ground-truth/no-correction
  wording. Never animate fake rays or claim localization from mere sensor On.

## Research basis (primary sources,2026-10-19)

- [Gazebo VisualizeLidar](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1GZ__SIM__VERSION__NAMESPACE_1_1VisualizeLidar.html):
  selectable sensor visual type and non-hitting-ray visibility.
- [Foxglove3D](https://docs.foxglove.dev/docs/visualization/panels/3d):
  laser-scan/point size/shape and decay; avoid unbounded accumulated clutter.
- [OpenUSD BBoxCache](https://openusd.org/dev/api/class_usd_geom_b_box_cache.html):
  model bounds relative to an ancestor, transformed with current pose/camera.
- Nav2-style goal execution/result separation is a design reference, not a
  claim that Nav2 is installed or that the new SIM driver uses ROS navigation.

Tavily CLI and its linked setup skill were unavailable; existing Tavily connector
was used instead, without installation or authentication changes.

## Actual acceptance

Freeze/build/install and use same installed Test BrowserWindow through normal
root Test entry; record source/release/launch identity. English fresh generation,
both actual robot-body selections and camera changes, stable geometry throughout
all four pointer directions/60s hold/status changes, panel destination-to-bed,
main-chat destination-to-chair, terminal arrival within checked standoff, Stop
during navigation and no replay, missing/unreachable/physical target rejections,
LiDAR points/rays/off with original frame binding, save/Exit/cold re-open and
current whole regression gate. Actual hardware, Explorer/OS clipboard and full
native input remain NOT_RUN unless actually exercised. Keep all failures and
record a new actual demo only after current acceptance. No reuse of previous
source SHA as this version's acceptance.
