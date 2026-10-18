# Battery charging threshold and operator readiness — 2026-09-26

## 2026-10-18 configurable display settings (v540)

Robots now exposes per-robot voltage-only / public ROBOTIS reference / custom
voltage-percent table settings, saved independently from the old registry shape
and hardware binding. Display settings cannot change existing motion protection.
Final installed same-BrowserWindow clicks and complete restart restore passed;
the charging robot was not contacted. Initial startup409, table clipping and
rollback-reader incompatibility were corrected and their evidence retained.
[Single actual report, recordings, exact IDs/SHA and limits](../../outputs/robot-battery-settings-20261018/report.html).
The public voltage-derived display is not a measured capacity calibration.

## 2026-10-18 correction and implementation

The later field suite/rules accidentally reintroduced11.4V as an extra motion
margin despite the decision below. It is not a ROBOTIS cutoff and11.34V is
approximately46.7%, not20% or a confirmed depleted battery. The actual powered
trial's earlier no-motion decision is preserved but its battery rationale is
corrected; native receipt/backlog remains an independent unresolved failure.

Official battery specification: LiPo11.1V nominal/1800mAh/19.98Wh/5C, LB-012
compatible with TurtleBot3. Nominal voltage is not the100% endpoint.
Sources checked2026-10-18:

- https://emanual.robotis.com/docs/en/platform/turtlebot3/features/
- https://en.robotis.com/shop_en/item.php?it_id=903-0210-000
- The OpenCR source/diagnosis links below (current public sources, not proof of
  the installed MCU binary):10.5→0/12.3→100; low LED<11.1, averaged protection
  state machine around11.0.20%=10.86 is below that protection region.

Local changes: explicit estimated_percent/estimate_method/capacity_measured=false
alongside nullable measured percent and original voltage/sample age; robot badge
and controller say `약47% (전압 추정) ·11.34V`, and separate20% reserve from existing
11.1V low-voltage/source guard. Saved connection observations show their recorded
estimate labelled historical, never current charge. No generic unknown robot
inherits this TB3 mapping. Extra11.4V field/observer comparisons were removed;
existing >11.1V production guard, freshness, charging, stop and geometry rules
are unchanged. No MCU firmware/deployed robot release modification or charging
robot access is performed by this update.20% does not promise operation down to
20%; lower-level protection may stop earlier and is reported as its own cause.

Supplementary Python39 and targeted fleet72/registry23 tests passed; an accidental
whole-web-suite invocation produced uninvestigated SceneFeedbackChat and
GenerationApproval failures plus jsdom canvas warnings and was interrupted, not
reported as an overall PASS. TypeScript/Vite build passed with its bundle-size
warning. Independent rerun of those two suites:15tests/13PASS/2FAIL; not proven
pre-existing and not hidden by the battery-specific results.

Actual installed10 `20261018T075120Z-52636c49c313`/source
`52636c49c3136097f6c63987136ffe6ba5eabe76d89de4d3b0385e74858af3b6`,1610file SHA
verified; ZIP `d0408045ec29ab770c1938b347509745803cf61fd190116782ad2a8ffb54d95a`.
Root Start-TwinPulse-Test.cmd via execution tool→same installed Electron's actual
Robots→Saved connection observations→original saved observation
`7da6f899dfd9eae8d46c7daa` displayed `약47% (전압추정) ·11.34V ·과거기록`.
Launch `dbcb224c1c3a48349f741be48d9e4af6`; explicit Exit. No new CheckConnection,
robot SSH, sensor or motion; the robot is charging. Native/Explorer/OSclipboard
NOT_RUN. [Actual screenshot](../../outputs/robot-battery-ui-20261018/recorded-47-percent.png)
and renderer recording/session are in `outputs/robot-battery-ui-20261018/`.
Fresh on-robot estimate/threshold behaviour remains NOT_RUN, existing native/ROS
lag and cold operation-summary defects unresolved. Model0HTTP/USD0, no dependencies,
firmware update, public release or Git writes. Old raw/observations preserved.

## User decision

User selected charging at approximately20% remaining. Interpret this as a
**voltage-derived estimate**, not calibrated measured capacity or remaining minutes.
Public ROBOTIS ROS2 firmware maps10.5V→0%,12.3V→100%:
`(V - 10.5) / 1.8 * 100`. This puts20% at10.86V,11.4V at50%, and the last
measured11.45V at approximately52.8%. Those percentages are calculated from the
public source, not a fresh measurement of the installed board's percentage register.

Source: https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3.cpp

## Independent hardware protection takes priority

Public firmware diagnosis code sets a low-battery LED below11.1V and uses an
approximately11.0V averaged-voltage state machine for warning/motor-power protection.
11.0V corresponds to approximately27.8% under the same display formula, so hardware
protection may intervene BEFORE the user's20% charging threshold. Do not promise
the robot can physically operate down to20%, or disable/alter firmware protection.
Exact installed-binary/source reproducibility and actual cutoff behavior remain
unverified. Battery damage, temperature, cell imbalance or unstable supply also
take priority over a percentage estimate. No such new condition was measured here.

Source: https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3_diagnosis.cpp

## Implementation / verified scope

Local bounded trial source in
`C:/Users/jaewo/Documents/Codex/2026-09-12/dl/guard_stop_probe` now includes
`battery_policy.hpp`: charging gate at<=20% (<=1086 centivolts), finite/range checks,
rounded centivolt comparison to avoid the earlier float-vs-double boundary error,
and clamped0–100% estimated display. The trial logs estimated percent in preflight.
This changes the optional trial client only, not the production command guard.
The firmware's independent protection is untouched; no new automatic battery alarm
monitoring service has been installed.

PC WSL GCC compilation with C++17/Wall/Wextra/Werror/pedantic and615 pure policy
checks PASS (10.85/10.86/10.87 boundary,11.4V accepted by charging policy,11.45V
estimate, nonfinite/range failures,301 centivolt values). Initial sandbox WSL
access denied; approved local execution then succeeded. No ROS/device access.
Full ROS probe rebuild/integration NOT_RUN for this revision.

**Not deployed to Pi.** Existing remote trial binary still has the historical11.4V
test threshold and its consumed one-shot marker remains in place. Never run that
old binary expecting this new policy. Before the next authorized trial, deploy
the reviewed source, rebuild/fake-test and separately establish a new one-shot
execution record. Do not erase the earlier marker or rerun automatically.

## Execution readiness correction

User reported they were not watching during the earlier brief movement because
preparation took approximately20 minutes. Therefore there is NO user visual
confirmation of that motion; only recorded telemetry/encoder evidence exists.
The assistant acknowledges it should have reconfirmed readiness just before motion.

For future physical trials: complete all lengthy preparation first; then state
fixed distance/speed/duration and request a fresh operator response confirming
they are watching and the area is clear. Execute promptly only after that response.
If delayed or preparation resumes, ask again. Earlier general approval is not a
standing authorization for unexpectedly delayed movement. Preparation should use
wall power where feasible; a physical power change remains an operator action.

This turn changes local source and records only. No robot SSH, motor/LiDAR action,
firmware update, threshold deployment, charging, shutdown or movement was performed.
The earlier instruction that charging is mandatory solely at11.4V is superseded;
physical command-expiry validation remains pending.
