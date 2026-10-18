# Robot health V1 and stop-record analysis — 2026-09-27

User requested deeper review, consolidated diagnostic code and a revised plan
for incorporating the accumulated robot work into TwinPulse. No physical motion
was authorized or performed for this review.

## Changes

- Added scripts/robot_health.py, extended existing SSH checker and passive ROS
  probe with the current Burger profile and optional digest-pinned board snapshot.
- Structured boot/system/device/process/guard/voltage/torque/velocity/command data;
  ROS streams and guard status when already running, explicit unavailable checks.
- No driver launch, motor service call, command publisher, firmware or OS change.
- Legacy generic command remains available. Root topic is no longer silently
  preferred over another sensor of the same type.
- Added scripts/analyze_robot_stop.py for saved text only; current failure remains
  a failure. It reconstructs122ms stable age vs200ms criterion at the500ms endpoint.
- Added current-state/review-plan documents and corrected stale planning pointers.

## Validation

`python -m unittest discover -s tests/integration -p 'test_robot*.py' -v`:
23 tests PASS. Includes old9, new health10 and saved stop analysis4.
Cases: wrong firmware/incomplete data/restore failure/duplicate register rejection,
20% boundary, independent protection proximity, busy port/digest mismatch/timeout
without backend execution/retry, unavailable readings not inheriting old battery,
multi-topic ambiguity, preserved physical settling failure and slow accumulating drift.

Actual one-shot read-only checker completed and wrote:
`artifacts/robot-checks/20260926T152444Z-80d890/report.json` and report.html.
Health observation00:24:32KST, artifact timestamp00:24:44KST (~12s).
Board voltage11.21V/estimated39.4%, torquefalse, velocities0/0, encoder1800/5530,
commandbyteszero, FW5, terminal restoration confirmed. CPU38.946°C, root9.13GiB
free, two serial devices, no monitored base/probe process, guard artifactdigestmatch.
`IDLE_SNAPSHOT_OK`, ROS`NO_SENSOR_DATA`/notrunningornodata; no motion permission.
CLI headline initially printed only legacy sensorstatus; corrected to show health
headline plus separate sensorstatus. Unit suite passed after this display correction.

No repeated physical run, no manual marker removal, no old default launch.
No new battery service or production RobotSession introduced. Verified backend
digest2f6b92235bdd2dcccdf2eeaba1c6cf001a001c7efb5c22734464962ee25c81bf;
its reviewed C++ source is currently local opencr_readonly_check.cpp and it still
depends on the previous /tmp executable. Runtime lifetime/race ownership limitations
are explicit, with permanent packaging and single ownership next in D1.

The8-row saved report excerpt reconstructs timeoutreceipt at983ms, last anchor
reset1361ms, observationend1483ms, stableage122ms. Nominal wheel movement across
the lastpretimeout→finalobservedinterval is3.594/3.695mm. These are derived from
logged encoder samples; not independent ground stop distance or a diagnosis of
mechanical cause. No threshold adjustment made.
