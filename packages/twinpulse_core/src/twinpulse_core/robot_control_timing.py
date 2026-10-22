# SPDX-License-Identifier: Apache-2.0
"""Shared App/robot engineering policy, not physical qualification.

Original clocks, sequence/generation fences and Stop remain mandatory. A
longer input lifetime never refreshes an old input or a restored session.
"""
ROS_RECEIPT_S = .2
ROS_SOURCE_S = .2
INPUT_TTL_S = .35
INPUT_TTL_MS = 350
ODOM_SAMPLE_INTERVAL_S = .3
OPERATOR_PRESENCE_S = .5
NATIVE_RECEIPT_S = .35
ICP_COMPUTE_S = .08
ROS_SERVICE_S = .5
TRACKING_RESULT_S = .6
# Fixed per-operation lossless recording budget, not a motion timeout. The
# 2026-10-20 all-load capture used 268MB in 524s; 900s at that rate is 461MB.
# 768MiB keeps a finite ~1.7x allowance for that observed session rate. It is
# not a guarantee for arbitrary workloads. Producer, PC and cold reader agree.
EVENT_ARCHIVE_BYTES = 768 * 1024 * 1024
EVENT_ARCHIVE_SEGMENTS = 256
TIMING_POLICY = {
    'schema': 'robot-control-timing-1.1',
    'revision': '2026-10-20-input350-odom300',
    'basis': 'user_selected_input350_odom300_pending_physical_requalification',
    'adaptive': False,
    'limits': {
        'ros_receipt': dict(seconds=ROS_RECEIPT_S, clock='robot_monotonic', failure='pause', recovery='fresh_sample_and_new_input'),
        'ros_source': dict(seconds=ROS_SOURCE_S, clock='ros_header_vs_ros_now', failure='pause', recovery='fresh_source_and_new_input'),
        'original_input': dict(seconds=INPUT_TTL_S, clock='robot_nonce_plus_original_pc_age', failure='pause', recovery='new_input_no_replay'),
        'odom_sample_interval': dict(seconds=ODOM_SAMPLE_INTERVAL_S, clock='consecutive_original_odom_sample_times', failure='TASK_ODOM_SAMPLE_GAP', recovery='fresh_sample_and_new_input'),
        'operator_presence': dict(seconds=OPERATOR_PRESENCE_S, clock='robot_monotonic', failure='pause', recovery='new_presence_and_input'),
        'native_receipt': dict(seconds=NATIVE_RECEIPT_S, clock='robot_monotonic_not_acquisition', failure='inconclusive_or_pause', recovery='new_complete_ring'),
        'icp_compute': dict(seconds=ICP_COMPUTE_S, clock='child_monotonic', failure='inconclusive', recovery='new_pair_not_wheel_fallback'),
        'tracking_result': dict(seconds=TRACKING_RESULT_S, clock='original_input_frame_receipt', failure='stale', recovery='new_pair'),
        'ros_service': dict(seconds=ROS_SERVICE_S, clock='robot_monotonic', failure='execution_unknown_until_readback', recovery='readback_no_motion_retry'),
        'cpp_output_guard': dict(seconds=.4, clock='robot_cpp_steady', failure='zero_output', recovery='explicit_rearm', owner='command_guard.hpp'),
    },
}
