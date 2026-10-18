# SPDX-License-Identifier: Apache-2.0
"""Fixed passive ROS/native observer for the explicitly supervised moving trial.

No base startup, motor power, arm or Twist publisher. Motion is exclusively the
unchanged qualified production controller. Original nonuniform beams are saved.
"""
import base64
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import threading
import time
import uuid


def main(*, translation_only=False):
    import rclpy
    from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
    from rclpy.serialization import serialize_message
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import Imu, JointState
    from turtlebot3_msgs.msg import SensorState
    from tf2_msgs.msg import TFMessage
    from std_msgs.msg import String
    from runtime import verify_release, write_json
    from raw_ros_record import RawRosRecorder
    from lidar_capture import acquire, SerialChannel
    home=Path('/home/twinpulse/.local/share/twinpulse/robot')
    release=(home/'current').resolve(strict=True)
    if release.name!='1cede5493f5a4ade3c46c49049dc9752a8fef3476b76f5a0cc214e16e9ade1ba':raise ValueError('RELEASE_CHANGED')
    verify_release(release)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    run='moving-native-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    out=Path('/dev/shm/twinpulse-moving-native')/run;out.mkdir(parents=True,exist_ok=False)
    report=dict(run_id=run,boot_id=boot,release_id=release.name,counts={},tf_pairs=[],passive_ros=True,
                motion_commands=0,report_directory=str(out),native={},status='STARTED',
                storage_basis='bounded volatile tmpfs, requires verified PC export before power-off')
    cancel=threading.Event();native_data=b'';native_chunks=[];native_thread=None;extras=[];samples=[]
    def interrupted(*_):cancel.set();raise KeyboardInterrupt('OBSERVER_SIGNAL')
    for sig in (signal.SIGHUP,signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    parent=os.getppid()
    if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGHUP,0,0,0)!=0 or os.getppid()!=parent:raise RuntimeError('PARENT_DEATH_FAILED')
    rclpy.init();node=rclpy.create_node('twinpulse_moving_native_observer',namespace='/tp_guard_stationary')
    recorder=RawRosRecorder(out/'ros-messages.raw',serializer=serialize_message,max_bytes=8*1024*1024)
    last_print=0.;last_yaw=None;unwrapped=0.;latest={}
    def native():
        nonlocal native_data,native_chunks
        report['native']['begin_monotonic_ns']=time.monotonic_ns()
        native_data,chunks=acquire(SerialChannel(),report['native'],cancel=cancel.is_set,
                                  capture_seconds=12. if translation_only else 40.,max_bytes=1024*1024)
        native_chunks=chunks
        report['native']['end_monotonic_ns']=time.monotonic_ns()
        (out/'native-lidar.raw').write_bytes(native_data);write_json(out/'native-chunks.json',chunks)
    def receive(topic,msg):
        nonlocal last_print,last_yaw,unwrapped,latest
        if not recorder.record(topic,msg):raise RuntimeError('ROS_RAW_WRITE_FAILED')
        report['counts'][topic]=report['counts'].get(topic,0)+1
        now=time.monotonic()
        if topic=='sensor_state':
            report['last_board']=dict(voltage_v=float(msg.battery),torque=bool(msg.torque),encoders=[msg.left_encoder,msg.right_encoder])
            # Match the unchanged production source guard, not the obsolete
            # 11.4V field-only margin (~50% by the OpenCR display formula).
            if not math.isfinite(msg.battery) or msg.battery<=11.1:cancel.set();raise RuntimeError('LOW_VOLTAGE_GUARD')
        if topic=='odom':
            q=msg.pose.pose.orientation
            yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
            if last_yaw is not None:unwrapped+=math.atan2(math.sin(yaw-last_yaw),math.cos(yaw-last_yaw))
            last_yaw=yaw
            latest=dict(kind='odom',robot_monotonic_s=now,stamp_ns=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec,
                xy=[msg.pose.pose.position.x,msg.pose.pose.position.y],yaw=yaw,unwrapped_yaw=unwrapped,
                native_bytes_ready=report['native'].get('start_sent') is True,
                twist=[msg.twist.twist.linear.x,msg.twist.twist.angular.z],board=report.get('last_board'))
            samples.append(latest)
            if now-last_print>=.1:print(json.dumps(latest,allow_nan=False),flush=True);last_print=now
        if topic in ('/tf','/tf_static'):
            for t in msg.transforms:
                pair=[t.header.frame_id,t.child_frame_id]
                if pair not in report['tf_pairs']:report['tf_pairs'].append(pair)
    def extra(topic,kind,msg):
        if len(extras)>=4000:raise RuntimeError('EXTRA_LIMIT')
        extras.append(dict(topic=topic,type=kind,host_receipt_monotonic_ns=time.monotonic_ns(),
                           cdr_base64=base64.b64encode(serialize_message(msg)).decode()))
    for topic,kind,qos in (('odom',Odometry,qos_profile_sensor_data),('sensor_state',SensorState,qos_profile_sensor_data),
            ('motion_guard/status',String,1),('/tf',TFMessage,qos_profile_sensor_data),
            ('/tf_static',TFMessage,QoSProfile(depth=50,durability=DurabilityPolicy.TRANSIENT_LOCAL))):
        node.create_subscription(kind,topic,lambda m,t=topic:receive(t,m),qos)
    node.create_subscription(Imu,'imu',lambda m:extra('imu','sensor_msgs/msg/Imu',m),qos_profile_sensor_data)
    node.create_subscription(JointState,'joint_states',lambda m:extra('joint_states','sensor_msgs/msg/JointState',m),qos_profile_sensor_data)
    begin=time.monotonic()
    try:
        native_thread=threading.Thread(target=native,daemon=True);native_thread.start()
        while time.monotonic()-begin<(16 if translation_only else 44):
            rclpy.spin_once(node,timeout_sec=.03)
            if cancel.is_set():break
            if native_thread is not None and not native_thread.is_alive():break
    except BaseException as exc:report['error']=type(exc).__name__+':'+str(exc)[:250]
    finally:
        cancel.set()
        if native_thread is not None:native_thread.join(timeout=10)
        report['native_thread_reaped']=native_thread is None or not native_thread.is_alive()
        report['raw_ros']=recorder.close()
        report['samples']=samples
        report['native_chunks']=native_chunks
        extra_bytes=('\n'.join(json.dumps(v) for v in extras)+'\n').encode()
        (out/'additional-sensors.ndjson').write_bytes(extra_bytes)
        report['additional_sensors']=dict(bytes=len(extra_bytes),sha256=hashlib.sha256(extra_bytes).hexdigest(),
            counts={t:sum(v['topic']==t for v in extras) for t in ('imu','joint_states')})
        node.destroy_node();rclpy.shutdown()
        good=(not report.get('error') and report['native_thread_reaped'] and report['raw_ros'].get('complete') is True
            and report['raw_ros'].get('dropped')==0 and report['counts'].get('odom',0)>=3
            and report['additional_sensors']['counts']['imu']>=3
            and report['native'].get('bytes_received',0)>0 and report['native'].get('data_quiet_after_stop') is True
            and report['native'].get('port_restored') is True and not report['native'].get('acquisition_error'))
        report['status']='CAPTURED_REQUIRES_MOTION_CORRELATION' if good else 'NEEDS_REVIEW'
        write_json(out/'report.json',report)
        print(json.dumps(dict(kind='final',report=report,
            native_base64=base64.b64encode(native_data).decode(),raw_ros_base64=base64.b64encode((out/'ros-messages.raw').read_bytes()).decode(),
            extra_base64=base64.b64encode(extra_bytes).decode()),allow_nan=False),flush=True)
    return 0 if good else 2


if __name__=='__main__':raise SystemExit(main())
