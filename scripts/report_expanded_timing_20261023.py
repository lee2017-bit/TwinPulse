# SPDX-License-Identifier: Apache-2.0
"""Derived, local evidence index; no robot access and no PASS fabrication."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-powered-roomplan-20261023-01'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
sessions=[]
for suffix,summary_name in [('07','powered-retry07-timing-summary02.json'),
                            ('08','powered-retry08-timing-summary.json'),
                            ('09','powered-retry09-timing-summary.json')]:
    folder=OUT/('ui-retry'+suffix)
    session=read(folder/'session.json');summary=read(OUT/summary_name)
    robot=next((e['evidence']['robot'] for e in reversed(session['events'])
                if isinstance(e.get('evidence',{}).get('robot'),dict)),{})
    launch=session['identity']['engine']['launch_id']
    archive=OUT/('runtime-copiesretry'+suffix)/launch
    operations=read(folder/'live-final/operation-final.json')
    sessions.append(dict(retry=suffix,launch_id=launch,operation_id=operations['operation_id'],
        release_id=session['identity']['engine']['release_id'],
        timing_values=robot.get('timing_values'),timing_profile_sha256=robot.get('timing_profile_sha256'),
        final_connection=robot.get('connection_state'),cleanup_confirmed=robot.get('cleanup_confirmed'),
        archive=summary['archive'],motions=summary['motions'],drive_rejections=summary['drive_rejections'],
        native_request_response_ms=summary['native_request_response_ms'],
        pc_input_ui_age_ms=summary['pc_input_ui_age_ms'],
        all_original_pauses=summary['pauses'],
        raw_receipt_sha256=digest(folder/'live-final/receipt.json'),
        operation_export_sha256=digest(folder/'live-final/operation-final.json'),
        video=dict(path=str((folder/'app-screen.mp4').relative_to(ROOT)),sha256=digest(folder/'app-screen.mp4'),
                   decode_log_bytes=(folder/'video-decode.log').stat().st_size,
                   scope='ACTUAL_RENDERER_SAMPLED_RECORDING_NOT_ROBOT_CAMERA_OR_COMPLETE_DEMO'),
        launcher_cleanup=read(archive/'cleanup-receipt.json'),runtime_copy=read(archive/'copy-receipt.json')))
latest=sessions[-1];session=read(OUT/'ui-retry09/session.json')
bootstrap_robot=next(e['evidence']['robot'] for e in session['events'] if e['name']=='BOOTSTRAP_RESULT')
final_robot=next(e['evidence']['robot'] for e in session['events'] if e['name']=='FINAL_CLEANUP_CONFIRMED')
product=[
    'packages/twinpulse_robot_safety/stop_policy.py','packages/twinpulse_robot_safety/teleop_worker.py',
    'packages/twinpulse_robot_safety/robot_journal.py','packages/twinpulse_robot_safety/fleet_worker.py',
    'packages/twinpulse_robot_safety/fleet_control.py',
    'packages/twinpulse_app/src/twinpulse_app/physical_live_session.py']
result=dict(schema='expanded-timing-powered-review-1.0',version=620,
    status='PARTIAL_NOT_FULL_CYCLE_PASS',source_manifest_sha256=read(OUT/'build08/dist/TwinPulse/windows-release-manifest.json')['source_manifest_sha256'],
    installation=read(OUT/'installation08.json'),
    authority='Human explicitly approved larger finite timing parameters and same supervised powered retest; no direct SSH control.',
    current_robot_timing=latest['timing_values'],automatic_adaptation=False,
    timing_qualification='ENGINEERING_CUSTOM_NOT_RECOMPUTED_MEASURED_RECOMMENDATION',
    changes=dict(stop_policy='Configured output cutoff +250ms guard-observation bound; dense stop evidence cap225ms, strict policy unchanged.',
        session_monitor='max(2500ms, frozen operator_presence_ms); actual watch ACK RTT cap500ms unchanged.',
        journal='2048 entries and16MiB pending including in-flight flush; archive768MiB unchanged.',
        recording_fault='First cause sticky; cancel owner once through real zero/OFF cleanup, fence queued actions; exact-request rejected Stop is not claimed execution.'),
    supplementary_tests=dict(log='buffer-ack-final04.log',sha256=digest(OUT/'buffer-ack-final04.log'),tests=218,seconds=17.316,result='OK',
        earlier_failed_fixture_log='buffer-ack-final02.log',review='Astra read-only final candidate review: no additional confirmed blocker in scoped source; not physical success proof.'),
    source_sha256={name:digest(ROOT/name) for name in product},
    latest_bootstrap_trials=bootstrap_robot['field']['trials'],
    latest_final_recording=final_robot.get('setup',{}).get('recording'),
    latest_original_stop=dict(reason='FIELD_DIRECTION_COVERAGE_GAP',request_id='731ab421-0dfd-4336-a5e2-211fe2942f91',
        source='ui-retry09/live-final/events-00014.jsonl:546',not_input_or_output_timeout=True,
        guard_policy_unchanged='Positive valid returns, maximum angular gap5degrees; rotation needs360degree coverage.'),
    independent_motion=read(OUT/'powered-retry09-independent-motion.json'),
    remaining=['Ten-second right hold stopped early; not whole continuous PASS.',
        'Identify exact selected latest/last-complete scan and valid angular gap; no missing angle fabricated as free space.',
        'Keyboard, chat/Send Command,90degree/full-turn/restore whole physical journey not completed on this release.',
        'Body displacement, braking, nominal extrinsics and RoomPlan physical alignment remain unqualified.',
        'Earlier retry07 wheel gap, retry08 DEGRADED and incomplete recording retained; clean retry09 does not prove their sole old cause.'],
    final_state=dict(app_and_isaac='NORMAL_ROOT_EXIT_0_WITH_OWNED_JOB_DESCENDANTS_REAPED',
        robot_session='STOP_LIDAR_OFF_DISCONNECTED_CLEANUP_CONFIRMED',
        robot_power='Human last reported ON; no power-off observation. No further motion requested.'),
    sessions=sessions,external_actions=dict(github_upload=0,delete=0,new_sdk=0,direct_ssh_control=0,model_api_calls=0))
target=OUT/'expanded-timing-status.json'
with target.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(dict(status=result['status'],path=str(target),sha256=digest(target))))
