# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Declared demo operations and their current implementation/test evidence.

This is an inventory and a fail-closed PC gate, not a physical permission.
Every operation must have a production entry and a test entry before it can
be marked covered. An offline unit test alone does not clear an integration gap.
"""
import ast
from pathlib import Path
from .demo_operation_manifest import CONTRACTS, FIELDS


# id, source path, symbol, test path, test symbol, implementation/integration state
OPERATIONS = (
    ('project_scene_open', 'packages/twinpulse_app/src/twinpulse_app/project_catalog.py', 'ProjectCatalog',
     'tests/integration/test_a2_project_catalog.py', 'ProjectCatalogTests', 'INTEGRATION_GAP'),
    ('room_goal_preview', 'packages/twinpulse_core/src/twinpulse_core/room_goal.py', 'room_goal_preview',
     'packages/twinpulse_core/tests/test_room_goal.py', 'test_rigid_direction_correct_and_no_authority', 'COVERED_OFFLINE'),
    ('source_prepare', 'scripts/prepare_robot.py', 'bundle',
     'tests/integration/test_robot_preparation.py', 'test_archive_reproducible_and_contains_sources_not_keys', 'COVERED_OFFLINE'),
    ('stationary_raw_odom_scan_tf', 'packages/twinpulse_robot_safety/stationary_observer.py', 'main',
     'packages/twinpulse_robot_safety/tests/stationary_test.py', 'StationaryTests', 'INTEGRATION_GAP'),
    ('ros_lidar_start_scan_stop', 'packages/twinpulse_robot_safety/lidar_capture.py', 'acquire',
     'packages/twinpulse_robot_safety/tests/test_lidar_capture.py', 'test_normal', 'NOT_IMPLEMENTED'),
    ('forward_motion', 'packages/twinpulse_app/src/twinpulse_app/physical_controller.py', 'PhysicalController',
     'tests/integration/test_physical_controller.py', 'test_forward_command_reaches_owned_pipe', 'INTEGRATION_GAP'),
    ('reverse_motion', 'packages/twinpulse_app/src/twinpulse_app/physical_controller.py', 'PhysicalController',
     'tests/integration/test_physical_controller.py', 'test_reverse_command_reaches_owned_pipe', 'INTEGRATION_GAP'),
    ('left_turn', 'packages/twinpulse_app/src/twinpulse_app/physical_controller.py', 'PhysicalController',
     'tests/integration/test_physical_controller.py', 'test_left_turn_reaches_owned_pipe', 'INTEGRATION_GAP'),
    ('right_turn', 'packages/twinpulse_app/src/twinpulse_app/physical_controller.py', 'PhysicalController',
     'tests/integration/test_physical_controller.py', 'test_right_turn_reaches_owned_pipe', 'INTEGRATION_GAP'),
    ('graceful_stop', 'packages/twinpulse_core/src/twinpulse_core/local_navigation.py', 'checked_command',
     'tests/integration/test_physical_controller.py', 'test_graceful_wait_only_remaining_slice_never_renews_or_publishes', 'INTEGRATION_GAP'),
    ('force_stop', 'packages/twinpulse_app/src/twinpulse_app/physical_controller.py', 'PhysicalController',
     'tests/integration/test_physical_controller.py', 'test_force_supersedes_queued_finish_without_resetting_deadline_or_downgrading', 'INTEGRATION_GAP'),
    ('calibrated_goal', 'packages/twinpulse_core/src/twinpulse_core/room_goal.py', 'room_goal_preview',
     'packages/twinpulse_core/tests/test_room_goal.py', 'test_no_reference_never_invents_coordinates', 'NOT_IMPLEMENTED'),
    ('autonomous_mission', 'packages/twinpulse_robot_safety/mission_runtime.py', 'run_mission',
     'packages/twinpulse_robot_safety/tests/mission_test.py', 'test_local_mission_arrives_without_remote_directions_or_repeat_approval', 'NOT_IMPLEMENTED'),
    ('obstacle_replan', 'packages/twinpulse_core/src/twinpulse_core/local_navigation.py', 'CheckedMission',
     'packages/twinpulse_core/tests/test_local_navigation.py', 'test_checked_live_pose_scan_and_command_failures_latch', 'NOT_IMPLEMENTED'),
    ('twin_observation_replay', 'packages/twinpulse_app/src/twinpulse_app/bedroom_rehearsal.py', 'checked_replay',
     'tests/integration/test_bedroom_rehearsal.py', 'BedroomRehearsalTests', 'INTEGRATION_GAP'),
    ('same_condition_comparison', 'packages/twinpulse_core/src/twinpulse_core/route_comparison.py', 'compare_routes',
     'packages/twinpulse_core/tests/test_route_comparison.py', 'test_changed_conditions_cannot_be_compared', 'INTEGRATION_GAP'),
    ('safe_cleanup_and_export', 'scripts/prepare_robot.py', 'export_stationary_files',
     'tests/integration/test_robot_preparation.py', 'PreparationTests', 'INTEGRATION_GAP'),
    ('saved_evidence_resume', 'packages/twinpulse_app/src/twinpulse_app/robot_evidence_recovery.py', 'RobotEvidenceRecovery',
     'tests/integration/test_robot_evidence_recovery.py', 'test_saved_report_retry_is_transfer_only_and_idempotent', 'COVERED_OFFLINE'),
)

PHYSICAL_REQUIRED = frozenset({
    'stationary_raw_odom_scan_tf', 'ros_lidar_start_scan_stop',
    'forward_motion', 'reverse_motion', 'left_turn', 'right_turn',
    'graceful_stop', 'force_stop', 'calibrated_goal', 'autonomous_mission',
    'obstacle_replan', 'twin_observation_replay', 'safe_cleanup_and_export',
    'saved_evidence_resume',
})

# Only actions whose semantics exactly match one DP0 operation are mapped.
# "stop" is a nonterminal manual release, not the terminal graceful stop;
# "watch", "qualify" and "close" also have no one-to-one demo ID yet.
ACTION_OPERATIONS = {
    'forward': 'forward_motion', 'backward': 'reverse_motion',
    'left': 'left_turn', 'right': 'right_turn',
    'finish_stop': 'graceful_stop', 'force_stop': 'force_stop',
}


def operation_for_action(action):
    return ACTION_OPERATIONS.get(action) if isinstance(action, str) else None


def _symbols(path):
    return {node.name for node in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _mapped_test_exists(root, test_id):
    if not isinstance(test_id, str) or test_id.count('#') != 1:
        return False
    relative, symbol = test_id.split('#')
    if not relative.startswith('tests/integration/') or not symbol.startswith('test_'):
        return False
    path = root / relative
    return path.is_file() and symbol in _symbols(path)


def _product_entry_exists(root, entry):
    if not isinstance(entry, str) or not entry.startswith('POST /v1/product/'):
        return False
    path = root / 'packages/twinpulse_app/src/twinpulse_app/api.py'
    return path.is_file() and entry.split(' ', 1)[1] in path.read_text(encoding='utf-8')


def audit(root):
    root = Path(root)
    rows = []
    undeclared_contracts = sorted(set(CONTRACTS) - {item[0] for item in OPERATIONS})
    for operation_id, source, symbol, test, test_symbol, state in OPERATIONS:
        reasons = []
        for kind, name, member in (('SOURCE', source, symbol), ('TEST', test, test_symbol)):
            path = root / name
            if not path.is_file() or member not in _symbols(path):
                reasons.append(kind + '_MISSING')
        if state != 'COVERED_OFFLINE':
            reasons.append(state)
        contract = CONTRACTS.get(operation_id)
        contract_reasons = []
        if contract is None or len(contract) != len(FIELDS):
            contract_reasons.append('CONTRACT_MISSING_OR_MALFORMED')
            details = None
        else:
            details = dict(zip(FIELDS, contract))
            for field in FIELDS[1:9]:
                if not isinstance(details[field], str) or not details[field].strip():
                    contract_reasons.append('CONTRACT_' + field.upper() + '_MISSING')
            entry = details['product_entry']
            if not _product_entry_exists(root, entry):
                contract_reasons.append('PRODUCT_ENTRY_UNMAPPED')
            integration = details['integration_test_id']
            if not _mapped_test_exists(root, integration):
                contract_reasons.append('INTEGRATION_TEST_UNMAPPED')
            if operation_id in PHYSICAL_REQUIRED and details['physical_test_id'] is None:
                contract_reasons.append('PHYSICAL_TEST_UNMAPPED')
        rows.append({'operation_id': operation_id, 'source': source, 'symbol': symbol,
                     'test': test, 'test_symbol': test_symbol,
                     'status': 'COVERED_OFFLINE' if not reasons else 'GAP', 'reasons': reasons,
                     'contract': details, 'contract_reasons': contract_reasons})
    return {'schema_version': 'demo-operation-audit-1', 'pc_demo_ready': False,
            'offline_inventory_complete': all(row['status'] == 'COVERED_OFFLINE' for row in rows),
            'manifest_mapped': not undeclared_contracts and all(not row['contract_reasons'] for row in rows),
            'undeclared_contracts': undeclared_contracts,
            'test_execution': 'NOT_RUN_BY_AUDIT',
            'operations': rows}
