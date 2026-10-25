# SPDX-License-Identifier: Apache-2.0
"""Scoped data/PC-repair evidence gate, explicitly not physical driving PASS."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-data-priority-20261025-01'
RUNTIME=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
data=read(OUT/'data-result01.json');installed=read(OUT/'installed01.json');source=read(OUT/'source-comparison01.json')
tests=read(OUT/'tests07/result.json');fleet=read(OUT/'repair-cold-fleet01.json');aria=(OUT/'repair-cold-ui01.aria.txt').read_text(encoding='utf-8')
old=read(ROOT/'outputs/robot-environment-field-20261025-01/result01.json')
task=RUNTIME/'projects/chat_mvmcf9wa_18f1e6d1/robot-tasks/9ab857c208416c83892dfa59bc09de2d/task.json'
checks=dict(stationary_raw_complete=data['status']=='PASS_STATIONARY_ACQUISITION_ONLY' and all(data['checks'].values()),
    only_sensor_not_pose=data['scan_event_count']==331 and data['heartbeats_with_pose']==0,
    original_failed_task_unchanged=sha(task)==old['task_sha256'] and read(task)['state']=='FAILED',
    original_failure_receipt_unchanged=sha(Path(old['receipt_path']))==old['receipt_sha256'],
    package_verified=installed['status']=='PASS' and all(installed['checks'].values()),
    same_source_closure=source['status']=='PASS' and source['manifest_members']==584,
    final_supplementary_regression=tests['status']=='PASS' and tests['tests']==584 and not tests['skipped'],
    cold_failure_visible='Physical task pose or observed map changed before admission.' in aria,
    cold_no_authority=all(r['connection_state']=='DISCONNECTED' and not r['capabilities']['drive'] and not r['live_heartbeat'] for r in fleet['robots'] if r['kind']=='physical'),
    cold_no_run_radio='radio "Run task"' not in aria,
    no_live_launcher_lock=not (RUNTIME/'launcher.lock').exists())
copies=[]
for suffix,launch in [('01','afc3786f48dc4a9e92a106189190c5f0'),('02','959463f538404606a8265b6ef9981246')]:
    folder=OUT/('runtime-copies'+suffix)/launch;copy=read(folder/'copy-receipt.json');exit=read(folder/'cleanup-receipt.json');engine=read(folder/'engine-result.json')
    exact=[r for r in copy['files'] if r['status']=='EXACT_COPY']
    checks['archive_'+suffix]=len(exact)==9 and all(sha(folder/r['name'])==r['sha256'] and (folder/r['name']).stat().st_size==r['bytes'] for r in exact)
    checks['normal_roots_'+suffix]=exit['exit_evidence_complete'] and exit['owned_processes_stopped'] and all(r['return_code']==0 and r['root_disposition']=='EXITED_DURING_GRACE' for r in exit['process_exit_observations'].values())
    checks['inner_cleanup_'+suffix]=engine['cleanup_status']=='PRE_CLOSE_COMPLETE' and not engine['cleanup_errors']
    copies.append(dict(launch_id=launch,exact=len(exact),unavailable=[r['name'] for r in copy['files'] if r['status']!='EXACT_COPY']))
    if suffix=='02':checks['cold_no_robot_post']='POST /v1/product/robot-fleet' not in (folder/'backend.log').read_text(encoding='utf-8',errors='replace')
console=(OUT/'tests07/console.txt').read_text(encoding='utf-8')
required=['test_actual_500ms_policy_refreshes_preplanning_ring_once_before_child',
    'test_new_ring_expired_by_storage_is_not_restamped_or_retried',
    'test_guard_preserves_first_exact_500ms_rejection_without_io',
    'test_rejection_storage_failure_cannot_replace_original_admission_error',
    'test_execute_stops_before_diagnostic_io_and_preserves_terminal_primary_error',
    'test_snapshot_and_grid_compute_time_never_rejuvenate_source_age',
    'test_missing_future_and_nonfinite_pc_source_clock_fail_closed',
    'test_real_500ms_adapter_queued_pin_cannot_refresh_itself_before_wire',
    'test_physical_current_accessor_does_not_erase_slow_snapshot_time']
checks['required_boundary_tests']=all(any(line.startswith(name+' ') and line.endswith(' ... ok') for line in console.splitlines()) for name in required)
value=dict(status='PASS_PC_REPAIR_AND_STATIONARY_DATA_ONLY' if all(checks.values()) else 'FAIL',checks=checks,
    checks_passed=sum(checks.values()),checks_total=len(checks),release_id=installed['package']['build_id'],
    source_manifest_sha256=installed['package']['source_manifest_sha256'],files=installed['package']['files'],
    source_changed_paths=[r['path'] for r in source['changed']],archives=copies,
    stationary_data=dict(events=data['events'],bytes=data['bytes'],scan_events=data['scan_event_count'],scan_span_s=data['scan_span_s']),
    original_cause='UNCONFIRMED_EXACT_GUARD_BRANCH',new_physical_driving='NOT_RUN',
    physical_whole_room_coverage=False,automatic_retry=False,ttl_relaxed=False,model_calls_this_turn=0,
    retained_failures=['tests02','tests05','unit-error01.json','verification-errors01.json','../robot-environment-field-20261025-01/result01.json'])
with (OUT/'acceptance01.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print(json.dumps(value))
raise SystemExit(0 if all(checks.values()) else 1)
