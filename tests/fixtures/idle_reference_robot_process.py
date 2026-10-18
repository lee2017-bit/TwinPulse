# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""TEST ONLY: actual stdin/worker loop with synthetic ROS-shaped observations.

No ROS, SSH, devices, real calibration or admission. Never deployed.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
for folder in (ROOT,ROOT/'packages/twinpulse_core/src',ROOT/'packages/twinpulse_robot_safety'):
    sys.path.insert(0,str(folder))
import json
import time
import hashlib
from copy import deepcopy
from teleop_worker import InputStream,emit
from tests.fixtures.manual_robot_process import mission_fixture
from tests.fixtures.observed_robot_process import ObservedLink
from observed_runtime import RobotObservedFactory
from mission_runtime import run_idle_localization


def main(state):
    report={'mode':'localize','physical_validation':'SYNTHETIC_TEST_ONLY','boot_id':'fake-boot',
        'release_id':'c'*64,'robot_session_id':'synthetic-idle','status':'FAILED',
        'cleanup_confirmed':False,'sensor_cleanup_confirmed':False}
    link=None
    try:
        stream=InputStream(max_line=16384);request=mission_fixture(state,stream)
        (state/'reference-received.json').write_text(json.dumps(request['full_reference']))
        world=json.loads((state/'synthetic-world.json').read_text())
        session='synthetic-idle-'+request['mission_id'] if world.get('unique_sessions') else 'synthetic-idle'
        report['robot_session_id']=session
        link=ObservedLink({'project_id':request['adaptive_scope']['project_id'],'session_id':session,
            'boot_id':'fake-boot','release_id':'c'*64,'source_revision':'c'*64,'origin':'live_ros'},world=world)
        emit({'state':'SESSION_EVENT','event':{'schema':'robot-session-1.0','robot_session_id':session,
            'event_index':1,'clock_domain':'robot_monotonic','t':time.monotonic(),'kind':'session_started',
            'data':{'mode':'localize','boot_id':'fake-boot','release_id':'c'*64}}})
        factory=RobotObservedFactory(link,request,output=emit,clock=time.monotonic)
        factory.prepare()
        if world.get('profile_processing'):
            # Fixture-only wall-time diagnostics. No fabricated freshness,
            # estimator pose, relaxed guard or production profile is supplied.
            report['phase_timings_s']=[]
            original_current=factory.current
            def measured_current(pose,now):
                started=time.monotonic()
                try:return original_current(pose,now)
                finally:report['phase_timings_s'].append({'phase':'current_match',
                    'elapsed_s':time.monotonic()-started})
            factory.current=measured_current
        if world.get('stable_review_test_only'):
            # Explicit estimator double, NOT measured localization success.
            # Retain the first fresh synthetic binding exactly until the first
            # actual guarded output; transport and native loop remain real.
            original_preview=factory.preview_current;original_current=factory.current
            frozen=original_preview()
            def stable():
                value=deepcopy(frozen);value['sample_s']=time.monotonic()-.02
                return value
            factory.preview_current=stable
            factory.current=lambda pose,now:(stable() if factory.mission is not None
                and not factory.mission.approved_output_consumed else original_current(pose,now))
            if world.get('post_enable_pose_change_test_only'):
                enable=link.enable
                def moved_during_enable():
                    enable();frozen['pose_map'][0]+=world.get('post_enable_delta_test_only',.001)
                link.enable=moved_during_enable
        if world.get('large_observation'):
            # Exercise full compressed/chunked transport without changing the
            # native estimator's pose, source, cells or guard thresholds.
            original=factory.preview_current
            padding=''.join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(1800))
            def enlarged():
                value=original();value['transport_test_padding']=padding;return value
            factory.preview_current=enlarged
        writer=emit
        if world.get('output_delay_s'):
            def writer(value):
                if value.get('state')=='LOCALIZATION_OBSERVATION':time.sleep(world['output_delay_s'])
                emit(value)
        index=[1]
        def record(kind,**data):
            index[0]+=1
            emit({'state':'SESSION_EVENT','event':{'schema':'robot-session-1.0','robot_session_id':session,
                'event_index':index[0],'clock_domain':'robot_monotonic','t':time.monotonic(),'kind':kind,'data':data}})
            if kind=='mission_decision':factory.record_visual()
        factory.handoff_sink=lambda value:(state/'goal-handoff.json').write_text(json.dumps(value))
        report.update(run_idle_localization(link,stream,writer,request,factory,record=record,
            consume=lambda:(state/('consumed-'+request['mission_id'])).touch(exist_ok=False)))
    except Exception as exc:
        from twinpulse_core.cleanup_diagnostics import checked_notes
        report.update(status='FAILED',reason=str(exc),error_type=type(exc).__name__,
            cleanup_errors=checked_notes(getattr(exc,'mission_cleanup_errors',[])))
    finally:
        if link:
            link.halt()
            report['synthetic_published']=link.events
            report['synthetic_final_pose']=list(link.pose)
            report['cleanup_confirmed']=not link.enabled
            report['sensor_cleanup_confirmed']=True
        (state/'idle-report.json').write_text(json.dumps(report))
        emit({'state':'FINISHED','report':report})
    return 0 if report['status'] in {'MISSION_CANCELLED','MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED'} else 2


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1])))
