# App-only supervised field tests — contract 1.0

This is a separate, explicit supervised household test path, not a relaxation of the existing measured protected profile. Robot is OFF during implementation. No hardware activity is authorized this turn. Connection, LiDAR, preparation, bounded tests and export must be available through the installed App when the operator later powers on.

## Ownership

Main owns all Python/core/robot/API/build/integration files and this contract. UI helper owns only RobotFleet.tsx, robot-fleet-types.ts, new RobotFieldTests.tsx, its tests and scoped CSS. Astra is read-only design review. No concurrent edits of the same files; no helper hardware/model/build calls.

## Public state and actions

Existing fleet action envelope remains unchanged. Add these physical actions:

- `field_setup`, offline allowed, payload `{config}`: schema `supervised-field-test-1.0`, robot_id, binding_sha256, footprint_radius_m (0.08..0.6), sensor_x_m/sensor_y_m (-0.6..0.6), sensor_yaw_rad (-pi..pi), angle_sign (-1 or 1), wheel_metres_per_tick (0.000001..0.01), wheel_separation_m (0.08..0.8), provenance (`reference`/`operator_reviewed`/`operator_measured`), axes_reviewed true. Save immutable digest and user inputs; saving never connects or arms. Reference values are editable and never labelled measured.
- `field_arm`, payload `{confirmed:true}`: explicitly reviewed supervision, unplugged charging, clear space and immediate physical power-off available. Requires connected, prepared, streaming complete native data and saved config. Fixed 900 second maximum current-session validity; no automatic resume/reconnect/boot restoration. Admission remains separately dependent on stop receipt. Stop/key release discard motion intent and nonce generation, perform zero/OFF and require fresh post-arm input; the existing supervision consent survives ordinary releases. LiDAR Off/disconnect/config/boot/TTL/storage fault end supervision. Consent is not a motor command lease.
- `field_test`, payload `{case,confirmed:true}`: cases `stationary`, `bootstrap_stop`, `forward`, `backward`, `left`, `right`, `full_turn`, `proximity`, `stall`, `presence_gap`, `soak`. Each creates a subtrial ID under the operation. Stationary/soak are zero-motion collection. Bootstrap is fixed forward .03 m/s <=.6s with dedicated actual-output guard and encoder/time bounds, watchdog observation and real zero/OFF. Other motion cases reuse <=2m/2pi/120s current finite task path; proximity/stall cases are bounded supervised observations, never a deliberate crash/stall. Presence gap is an induced App-input gap, not a real network outage. No arbitrary velocities/code.
- `field_review`, payload `{trial_id,observed,clearance_m?}`: observed `stopped`/`not_stopped`/`moved`/`not_moved`/`inconclusive`. Human observations are bound to the actual trial; outer-body clearance input is required for a 10cm physical-clearance claim. Raw sensor threshold alone is not that claim.

`robot.field` optional object: `{config,config_sha256,mode,armed,remaining_s,blockers,stop_receipt,tracking,active_trial,trials}`. Config is available offline, mode `SUPERVISED_FIELD_TEST`, no modelled industrial safety guarantee. Tracking `{status,epoch,pose,reason,raw_sha256,independent:true,accuracy:'UNQUALIFIED'}` is scan-relative, no wheel seed/deskew; ambiguity stops body-progress proof and is INCONCLUSIVE. Every individual trial has `{trial_id,case,status,reason,started_s,ended_s?,result?}`. Status RUNNING/PASS/FAIL/INCONCLUSIVE/CANCELLED means only its stated scope. UI must show exactly what is missing, never generic 'fully ready'.

## Guard and evidence

Command caps .03m/s and .20rad/s are policy caps, not measured values. Original 250ms input expiry, local 400ms watchdog, Stop priority, full native checksum/original angles/byte continuity/complete increasing rings, receipt age/span and directional coverage remain. Unknown beam acquisition time is explicitly unqualified. Receipt-based 10cm proximity stop does not assert physical stopping distance. Encoder wheel stall is separate from independent chassis proof. Scan registration runs outside publish and never uses fit residual as certified pose error. Stable tracking epoch is separate from per-frame evidence SHA.

New test/config/tracking/stop receipt files have fixed reviewed names and join existing raw recording/export. Context binds operation/robot/project/connection/boot/release/worker/config and trial. All saved settings are data, never restored movement authority. Existing strict protected profile remains available separately.

## Acceptance

Offline actual saved native replay and protocol/fault tests are supplementary. Installed same Electron BrowserWindow clicks must exercise offline setup/edit/save/reopen, the entire test list and missing-prerequisite feedback, plus actual Isaac SIM/manual/chat/Stop regressions. No direct mutation API/state injection/fixed model response substitutes. Robot OFF leaves physical sensor/motion outcomes NOT_RUN, not missing software paths. Normal Start and shutdown are separately recorded; Explorer/native OS limits disclosed.
