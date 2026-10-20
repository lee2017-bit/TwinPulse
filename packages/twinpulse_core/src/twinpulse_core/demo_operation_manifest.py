# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Declared demo-operation contract, not evidence of execution or motion authority.

An empty product/integration mapping is intentional: the audit must expose it.
The strings describe acceptance evidence; they must never be interpreted as an
instruction to start a robot or as proof that a test has run.
"""

from types import MappingProxyType
from .robot_control_timing import INPUT_TTL_MS


# Current automatic product flow, distinct from the retained DP0 inventory.
# These identifiers select fixed, reviewed local checks in run_demo_preflight;
# neither entry paths nor acceptance descriptions are executable input.
AUTOMATIC_OPERATIONS = MappingProxyType({
    'raw_integrity': ('twinpulse_app.saved_mapping_evidence.saved_observation_source', (),
        'Each original raw/footer/session; preserve gaps, rejected data and source failure'),
    'recorded_mapping_photo': ('twinpulse_app.automatic_demo_service.AutomaticDemoService', ('raw_integrity',),
        'All three originals through shared map/photo/save/reopen; mismatch is not alignment PASS'),
    'cold_start_revision_goal': ('twinpulse_app.automatic_mission_service.AutomaticMissionService', (),
        'One Start survey/held-out fit/correction/revision/fresh goal/final zero with output-reactive synthetic observations'),
    'revision_ack': ('twinpulse_core.current_mission_evidence', (),
        'Reject wrong scope, expired, repeated or stopped correction; preserve source guard'),
    'loss_stop_cleanup_storage': ('twinpulse_app.automatic_mission_service.AutomaticMissionService', (),
        'Lost pose, force/graceful stop, failed sensor cleanup and failed report storage retain causes and clear current visuals'),
    'driver_transport': ('twinpulse_robot_safety.isolated_ros_scan', (),
        'Fixed fake-driver lifecycle/early exit/library/lease/raw export boundaries; never real ROS or SSH'),
    'package_contracts': ('scripts.verify_packaged_automatic_demo', (),
        'Package admission/failure contracts only, not a new packaged runtime receipt'),
    'active_isaac_runtime': ('twinpulse.extension.isaac_adapter', ('cold_start_revision_goal',),
        'Requires a fresh actual Web/API/Isaac receipt bound to this build; NOT_RUN by the OFF check'),
    'same_condition_mission_comparison': ('twinpulse_app.automatic_comparison_service.AutomaticComparisonService.start', (),
        'Reset synthetic world, paired shared missions, isolated ledgers, raw/reopen and collision scoring; not physical'),
    'physical_mission': ('twinpulse_robot_safety.mission_runtime', ('recorded_mapping_photo','driver_transport'),
        'Requires reviewed target/mount/acquisition/profile and new current-boot on-site approval; never run by OFF check'),
})


# entry, prerequisites, request, response, expected observation, bounds,
# original evidence, acceptance, cleanup, integration test id, physical test id.
# The offline test id is supplied by the inventory in demo_contract.py.
_ROWS = {
    'project_scene_open': (
        'POST /v1/product/bedroom/build', 'saved project revision and explicit Build acknowledgement',
        'revision, acknowledgement, request ID', 'owned engine Build receipt and saved scene revision',
        'Burger visual and same saved scene reopen', 'no robot motion; one reviewed revision per request',
        'source photo/recipe/revision and engine receipt', 'same source/build and revision after reopen',
        'stop only owned Build; preserve source and unrelated prims',
        'tests/integration/test_bedroom_review.py#test_real_broker_envelope_has_bound_preview_no_motion', None),
    'room_goal_preview': (
        'POST /v1/product/bedroom/goal-preview', 'reviewed room and explicit metric reference or missing-reference status',
        'scene/evidence revisions, metric goal, optional correspondences', 'candidate or missing-reference reason',
        'candidate transform with residual; no motion authority', '3–16 nondegenerate pairs; residual <= 0.05 m',
        'scene revision, reference hash and input points', 'missing/invalid evidence cannot produce executable goal',
        'no actuator; preserve rejected reference and reason',
        'tests/integration/test_robot_geometry_evidence.py#test_existing_review_goal_path_is_non_mutating_and_bound', None),
    'source_prepare': (
        'POST /v1/product/robot/physical/start', 'reviewed fixed source and pinned target manifest; explicit on-site prepare approval',
        'mode=prepare, request ID, confirmation and fresh expiry', 'owned prepare result and saved source/preparation report',
        'target package inventory; any source transfer requires this explicit prepare request', 'bounded local bundle; no secrets',
        'source hashes and package manifest', 'same source fingerprint; missing dependencies block readiness',
        'retain original files; no motion or automatic robot operation after prepare',
        'tests/integration/test_physical_controller.py#test_http_prepare_mode_reaches_only_owned_fake_prepare', None),
    'stationary_raw_odom_scan_tf': (
        'POST /v1/product/robot/readiness/start', 'current robot idle and explicit one-time source transfer plus bounded no-motion collection approval',
        'request ID, source-transfer/no-motion confirmation and fresh expiry', 'owned saved observer report with exact boot/release',
        'raw odom/scan/TF or explicit no-publisher/no-message/rejection reason', '20 s bounded observation; no motion',
        'serialized ROS bytes, topic/type/sequence/time, stdout/stderr', 'complete raw receipt and diagnosed gaps, not fabricated pose',
        'stop observer; preserve raw even when invalid',
        'tests/integration/test_robot_readiness_app.py#test_authenticated_single_start_and_saved_gap', None),
    'ros_lidar_start_scan_stop': (
        None, 'reviewed driver release, sole serial owner and explicit sensor scope',
        'bounded start and stop', 'driver write/read result and terminal state',
        'LaserScan topic sample and independently observed rotor stop', 'bounded capture and shutdown deadlines; no wheel command',
        'serial chunks, ROS scan bytes, driver logs and STOP result', 'valid scan plus verified lifecycle; raw serial alone insufficient',
        'STOP and close sole port; failure remains failure', None, None),
    'forward_motion': (
        'POST /v1/product/robot/physical/input', 'owned qualified session, fresh input and scoped floor clearance',
        'action=forward, sequence, expiry', 'PC receipt, worker acceptance and ROS publish result',
        'encoder/odom forward displacement and final zero command', f'per-input {INPUT_TTL_MS} ms freshness; bounded hold/session',
        'input/pipe/publish/encoder/odom journal and raw ROS', 'expected direction, no collision and independently confirmed stop',
        'zero command, torque OFF and original evidence export',
        'tests/integration/test_physical_controller.py#test_http_forward_input_reaches_fake_owned_pipe', None),
    'reverse_motion': (
        'POST /v1/product/robot/physical/input', 'owned qualified session, fresh input and scoped rear clearance',
        'action=backward, sequence, expiry', 'PC receipt, worker acceptance and ROS publish result',
        'encoder/odom rear displacement and final zero command', f'per-input {INPUT_TTL_MS} ms freshness; bounded hold/session',
        'input/pipe/publish/encoder/odom journal and raw ROS', 'expected direction, no collision and independently confirmed stop',
        'zero command, torque OFF and original evidence export',
        'tests/integration/test_physical_controller.py#test_http_reverse_input_reaches_fake_owned_pipe', None),
    'left_turn': (
        'POST /v1/product/robot/physical/input', 'owned qualified session, fresh input and scoped turn clearance',
        'action=left, sequence, expiry', 'PC receipt, worker acceptance and ROS publish result',
        'encoder/odom counterclockwise yaw and final zero command', f'per-input {INPUT_TTL_MS} ms freshness; bounded hold/session',
        'input/pipe/publish/encoder/odom journal and raw ROS', 'expected yaw sign, no collision and independently confirmed stop',
        'zero command, torque OFF and original evidence export',
        'tests/integration/test_physical_controller.py#test_http_left_input_reaches_fake_owned_pipe', None),
    'right_turn': (
        'POST /v1/product/robot/physical/input', 'owned qualified session, fresh input and scoped turn clearance',
        'action=right, sequence, expiry', 'PC receipt, worker acceptance and ROS publish result',
        'encoder/odom clockwise yaw and final zero command', f'per-input {INPUT_TTL_MS} ms freshness; bounded hold/session',
        'input/pipe/publish/encoder/odom journal and raw ROS', 'expected yaw sign, no collision and independently confirmed stop',
        'zero command, torque OFF and original evidence export',
        'tests/integration/test_physical_controller.py#test_http_right_input_reaches_fake_owned_pipe', None),
    'graceful_stop': (
        'POST /v1/product/robot/physical/input', 'active owned operation',
        'action=finish_stop, sequence, expiry', 'stop receipt and terminal worker result',
        'no next motion slice; zero output and stationary readback', 'only current bounded slice may finish',
        'stop intent, final publish/readback and cleanup journal', 'final stop confirmed; timeout is not success',
        'torque OFF; preserve failure and evidence',
        'tests/integration/test_physical_controller.py#test_http_graceful_stop_reaches_fake_owned_pipe', None),
    'force_stop': (
        'POST /v1/product/robot/physical/input', 'active or uncertain owned operation',
        'action=force_stop, sequence, expiry', 'urgent stop receipt and terminal worker result',
        'queued/current output cancelled, zero output and stationary readback', 'no wait for a new motion slice',
        'force intent, final publish/readback and cleanup journal', 'stop confirmation or explicit unconfirmed failure',
        'torque OFF; preserve failure and evidence',
        'tests/integration/test_physical_controller.py#test_http_force_stop_reaches_fake_owned_pipe', None),
    'calibrated_goal': (
        None, 'current boot, measured sensor-to-base and room-to-odom calibration',
        'goal with scene/geometry/calibration revisions', 'validated executable odom goal or reason',
        'current-frame goal with independent residual and geometry evidence', 'no default photo-derived transform; bounded room and goal',
        'original correspondences, TF, boot/release and revision hashes', 'current physical frame/scale verified before mission',
        'no motion when missing/stale; retain rejected evidence', None, None),
    'autonomous_mission': (
        None, 'current calibrated goal, valid local scan/odom/TF and reviewed scope',
        'bounded goal, policy and single scoped approval', 'mission state and terminal receipt',
        'observed pose, local clearance, command stream and terminal zero', 'bounded speed, time, travel and input age',
        'raw scan/odom/TF, command/observation and safety journal', 'goal reached without collision; incomplete sensing fails closed',
        'local watchdog zero/OFF and raw export', None, None),
    'obstacle_replan': (
        None, 'active valid mission and fresh calibrated scan/pose',
        'blocked path and bounded replanning budget', 'stop/replan/continue or no-path result',
        'zero output before reassessment; verified new path or terminal block', 'finite search and mission deadlines',
        'raw scan/pose, candidate path and local guard decisions', 'no stale/unknown traversal; collision remains penalty',
        'terminal zero/OFF on no path or stale sensor', None, None),
    'twin_observation_replay': (
        'POST /v1/product/bedroom/replay', 'verified source-bound trace and scene revision',
        'trace hash and bounded frame index', 'engine visual receipt and frame identity',
        'Burger pose from observed source, not inferred command integration', 'bounded saved frames; no physical command',
        'trace source hashes, odom/TF originals and engine receipt', 'same frame and revision after save/reopen',
        'retain source; never mutate physical authority',
        'tests/integration/test_bedroom_review.py#test_replay_recomputed_bound_and_separate_artifacts', None),
    'same_condition_comparison': (
        'POST /v1/product/bedroom/compare', 'two verified traces with same scene/start/goal/profile/policy/map',
        'trace IDs and condition manifest', 'axis-separated comparison and canonical hash',
        'observed outcomes with unknown collision unfilled', 'bounded comparison; no robot command',
        'both source traces and condition hashes', 'reject changed/unknown conditions; no synthetic=physical claim',
        'retain both originals and rejected reason',
        'tests/integration/test_bedroom_rehearsal.py#test_compare_rejects_changed_conditions_or_record_integrity', None),
    'safe_cleanup_and_export': (
        None, 'ended or failing owned session; raw originals retained',
        'job/boot/release and allowlisted file request', 'OFF result and per-file transfer receipt',
        'independent stop state plus full raw/frame/footer verification', 'bounded paths, sizes and transfer attempts',
        'worker report, raw files, logs and SHA256 manifest', 'no COMPLETE if missing/drop/corrupt/unbound',
        'retain remote originals; transfer-only retry', None, None),
    'saved_evidence_resume': (
        'POST /v1/product/robot/physical/evidence/resume', 'saved ended real-transport report; no active operation',
        'job_id and unique request_id', 'background transfer status and receipt',
        'missing/corrupt files identified; no new trial or motion', 'allowlist files and fixed size ceilings',
        'saved report, exact raw files and transfer receipt', 'valid original binding or explicit INCOMPLETE',
        'retain remote originals and past failure',
        'tests/integration/test_robot_evidence_recovery.py#test_authenticated_explicit_resume_never_starts_robot_operation', None),
}

CONTRACTS = MappingProxyType(_ROWS)
FIELDS = ('product_entry', 'preconditions', 'request_schema', 'response_schema',
          'expected_observations', 'bounds', 'raw_artifacts', 'acceptance',
          'cleanup', 'integration_test_id', 'physical_test_id')
