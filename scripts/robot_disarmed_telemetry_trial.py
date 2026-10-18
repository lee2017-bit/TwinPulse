# SPDX-License-Identifier: Apache-2.0
"""Bounded current guarded base observation: no arm, power service or movement.

The verified base sends zero and heartbeat. This is not no-motor-I/O, nor a
physical-stop qualification. Torque state remains independently observed.
"""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
from robot_sensor_only_trial import EXPECTED_RELEASE,require_sensor_stationary,SensorWindowEnded


def main(*,with_native_lidar=False):
    from runtime import ownership,read_board,verify_release,write_json
    from robot_health import parse_board_snapshot
    from stationary import commands,stop_child
    from raw_ros_record import RawRosRecorder
    from rclpy.serialization import serialize_message
    from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
    import rclpy
    from nav_msgs.msg import Odometry
    from turtlebot3_msgs.msg import SensorState
    from tf2_msgs.msg import TFMessage
    from std_msgs.msg import String
    from sensor_msgs.msg import Imu,JointState
    home=Path('/home/twinpulse/.local/share/twinpulse/robot');release=(home/'current').resolve(strict=True)
    if release.name!=EXPECTED_RELEASE:raise ValueError('RELEASE_CHANGED')
    manifest=verify_release(release)
    if manifest['files']['bin/turtlebot3_ros']!='403b148b2bdbf0e4c6fc0540888768f9a5eddd38649b1d20883e61fb7fcdc042':
        raise ValueError('GUARDED_BASE_CHANGED')
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    run_id='disarmed-telemetry-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    out=home/'reports'/run_id;out.mkdir(exist_ok=False,parents=True)
    report=dict(schema_version='disarmed-telemetry-1.0',run_id=run_id,status='STARTED',
                release_id=release.name,boot_id=boot,report_directory=str(out),
                nonzero_commands_sent=0,arm_calls=0,motor_power_calls=0,
                base_io='verified guard startup/shutdown zero plus heartbeat',
                counts={},first={},last={},guard_reasons=[],tf_pairs=[],physical_authority=False)
    base=node=recorder=None;ros_started=False;started=None
    native_thread=None;native_cancel=threading.Event();native_result={};native_data=b''
    def collect_native():
        nonlocal native_data
        from lidar_capture import acquire,SerialChannel
        native_result['began_monotonic_ns']=time.monotonic_ns()
        native_data,chunks=acquire(SerialChannel(),native_result,cancel=native_cancel.is_set)
        native_result['finished_monotonic_ns']=time.monotonic_ns()
        (out/'native-lidar.raw').write_bytes(native_data);write_json(out/'native-lidar-chunks.json',chunks)
    def interrupted(sig,_):
        if sig==signal.SIGALRM and started is not None:raise SensorWindowEnded()
        raise KeyboardInterrupt('DISARMED_TRIAL_SIGNAL_'+str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):signal.signal(sig,interrupted)
    parent=os.getppid()
    if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGHUP,0,0,0)!=0 or os.getppid()!=parent:
        raise RuntimeError('PARENT_DEATH_BINDING_FAILED')
    with ownership() as lease,(out/'base.log').open('xb') as log:
        def snapshot(label):
            if (home/'current').resolve(strict=True)!=release or Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=boot:
                raise ValueError('BOOT_OR_RELEASE_CHANGED')
            target=out/(label+'-board.log');read_board(release,target,lease.fileno())
            value=parse_board_snapshot(target.read_text());require_sensor_stationary(value,report.get('before'))
            return value
        try:
            report['before']=snapshot('before');time.sleep(.5);report['second']=snapshot('second')
            rclpy.init();ros_started=True
            node=rclpy.create_node('twinpulse_disarmed_capture',namespace='/tp_guard_stationary')
            recorder=RawRosRecorder(out/'ros-messages.raw',serializer=serialize_message,max_bytes=8*1024*1024)
            extras=[]
            def receive_extra(topic,kind,msg):
                if len(extras)>=1200:raise RuntimeError('EXTRA_SENSOR_LIMIT')
                extras.append(dict(topic=topic,type=kind,host_receipt_monotonic_ns=time.monotonic_ns(),
                    cdr_base64=base64.b64encode(serialize_message(msg)).decode()))
            node.create_subscription(Imu,'imu',lambda m:receive_extra('imu','sensor_msgs/msg/Imu',m),qos_profile_sensor_data)
            node.create_subscription(JointState,'joint_states',lambda m:receive_extra('joint_states','sensor_msgs/msg/JointState',m),qos_profile_sensor_data)
            def receive(topic,msg):
                nonlocal native_thread
                recorder.record(topic,msg)
                report['counts'][topic]=report['counts'].get(topic,0)+1
                value={'host_receipt_ns':time.monotonic_ns()}
                if topic=='sensor_state':
                    value.update(left_encoder=msg.left_encoder,right_encoder=msg.right_encoder,
                                 torque=bool(msg.torque),battery_v=float(msg.battery),button=int(msg.button))
                    if (abs(msg.left_encoder-report['before']['encoders'][0])>2
                            or abs(msg.right_encoder-report['before']['encoders'][1])>2):
                        raise RuntimeError('DISARMED_ENCODER_CHANGED')
                    if msg.battery<=11.1:raise RuntimeError('LOW_VOLTAGE')
                elif topic=='odom':
                    value.update(frame=msg.header.frame_id,child=msg.child_frame_id,
                        source_stamp_ns=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec,
                        position=[msg.pose.pose.position.x,msg.pose.pose.position.y,msg.pose.pose.position.z],
                        quaternion=[msg.pose.pose.orientation.x,msg.pose.pose.orientation.y,msg.pose.pose.orientation.z,msg.pose.pose.orientation.w])
                elif topic=='motion_guard/status':
                    value['reason']=msg.data
                    if msg.data not in report['guard_reasons']:report['guard_reasons'].append(msg.data)
                    if msg.data in ('active','armed_waiting_for_command'):raise RuntimeError('UNEXPECTED_ARMED_STATE')
                else:
                    value['transforms']=[dict(frame=t.header.frame_id,child=t.child_frame_id,
                        xyz=[t.transform.translation.x,t.transform.translation.y,t.transform.translation.z],
                        quaternion=[t.transform.rotation.x,t.transform.rotation.y,t.transform.rotation.z,t.transform.rotation.w]) for t in msg.transforms]
                    for t in value['transforms']:
                        pair=[t['frame'],t['child']]
                        if pair not in report['tf_pairs']:report['tf_pairs'].append(pair)
                report['first'].setdefault(topic,value);report['last'][topic]=value
                if with_native_lidar and topic=='odom' and native_thread is None:
                    native_thread=threading.Thread(target=collect_native,daemon=True);native_thread.start()
            for topic,kind,qos in (('sensor_state',SensorState,qos_profile_sensor_data),('odom',Odometry,qos_profile_sensor_data),
                ('motion_guard/status',String,1),('/tf',TFMessage,qos_profile_sensor_data),
                ('/tf_static',TFMessage,QoSProfile(depth=50,durability=DurabilityPolicy.TRANSIENT_LOCAL))):
                node.create_subscription(kind,topic,lambda msg,t=topic:receive(t,msg),qos)
            command,_=commands(release,out)
            base=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True,pass_fds=(lease.fileno(),))
            duration=25. if with_native_lidar else 12.
            started=time.monotonic();signal.setitimer(signal.ITIMER_REAL,duration)
            while time.monotonic()-started<duration:
                rclpy.spin_once(node,timeout_sec=.05)
                if base.poll() is not None:raise RuntimeError('BASE_EARLY_EXIT')
                if with_native_lidar and native_thread is not None and not native_thread.is_alive():break
        except SensorWindowEnded:report['deadline_reached']=True
        except BaseException as exc:report['error']=type(exc).__name__+':'+str(exc)[:200]
        finally:
            signal.alarm(0)
            for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):signal.signal(sig,signal.SIG_IGN)
            if started is not None:report['observe_seconds']=round(time.monotonic()-started,3)
            if native_thread is not None:
                native_cancel.set();native_thread.join(timeout=14.)
                report['native_lidar']=native_result
                if native_thread.is_alive():report['cleanup_error']='NATIVE_CAPTURE_CLEANUP_UNCONFIRMED'
            if base is not None:
                try:report['base_exit']=stop_child(base)
                except BaseException as exc:report['cleanup_error']=type(exc).__name__+':'+str(exc)[:200]
            if recorder is not None:report['raw_ros']=recorder.close()
            if 'extras' in locals():
                extra_bytes=('\n'.join(json.dumps(row) for row in extras)+'\n').encode()
                (out/'additional-sensors.ndjson').write_bytes(extra_bytes)
                report['additional_sensors']=dict(sha256=hashlib.sha256(extra_bytes).hexdigest(),
                    counts={t:sum(row['topic']==t for row in extras) for t in ('imu','joint_states')},
                    bytes=len(extra_bytes),schema='sensor-extra-cdr-1.0')
            if node is not None:node.destroy_node()
            if ros_started:rclpy.shutdown()
            if base is None or base.poll() is not None:
                try:report['after']=snapshot('after')
                except BaseException as exc:report['after_error']=type(exc).__name__+':'+str(exc)[:200]
            else:report['after_error']='BASE_EXIT_UNCONFIRMED'
            good=(not any(k in report for k in ('error','cleanup_error','after_error'))
                and report.get('raw_ros',{}).get('complete') is True and report['counts'].get('odom',0)>=3)
            if with_native_lidar:
                good=(good and native_result.get('bytes_received',0)>0
                    and native_result.get('data_quiet_after_stop') is True
                    and native_result.get('port_restored') is True
                    and not any(k in native_result for k in ('acquisition_error','restore_error')))
            report['status']='DISARMED_TELEMETRY_CAPTURED' if good else 'NEEDS_REVIEW'
            write_json(out/'report.json',report)
            raw=(out/'ros-messages.raw').read_bytes() if (out/'ros-messages.raw').is_file() else b''
            print(json.dumps(dict(report,raw_ros_base64=base64.b64encode(raw).decode(),
                native_base64=base64.b64encode(native_data).decode(),
                extra_base64=base64.b64encode(extra_bytes if 'extra_bytes' in locals() else b'').decode()),allow_nan=False),flush=True)
    return 0 if good else 2


if __name__=='__main__':raise SystemExit(main())
