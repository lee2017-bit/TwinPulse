# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Real ROS Humble transport. Only imported by explicitly launched robot worker."""
import time
import math
try:
    from observation_stream import ObservationWindow, from_ros_message
except ModuleNotFoundError as exc:
    if exc.name != 'observation_stream': raise
    from twinpulse_core.observation_stream import ObservationWindow, from_ros_message
from teleop_contract import RequestedStop
from stop_policy import OBSERVE_S, POLICY, MM_PER_TICK
try:
    from twinpulse_core.local_navigation import checked_command
except ModuleNotFoundError as exc:
    if exc.name not in {'twinpulse_core','twinpulse_core.local_navigation'}:raise
    from local_navigation import checked_command  # Backward-compatible older bundle.
try:
    from ros_observations import RosObservations, scan_preview
except ModuleNotFoundError as exc:
    if exc.name!='ros_observations':raise
    from twinpulse_core.ros_observations import RosObservations, scan_preview
try:
    from twinpulse_core.navigation_binding import navigation_inputs
except ModuleNotFoundError as exc:
    if exc.name not in {'twinpulse_core','twinpulse_core.navigation_binding'}:raise
    from navigation_binding import navigation_inputs


class RosLink:
    def __init__(self, base, raw_path=None):
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from geometry_msgs.msg import TwistStamped
        from std_msgs.msg import String
        from std_srvs.srv import Trigger, SetBool
        from turtlebot3_msgs.msg import SensorState
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import LaserScan
        if raw_path is not None:
            from rclpy.serialization import serialize_message
            from raw_ros_record import RawRosRecorder
        self.ros, self.Twist, self.Trigger, self.Power = rclpy, TwistStamped, Trigger, SetBool
        rclpy.init()
        self.node = rclpy.create_node('twinpulse_manual_control', namespace='/tp_guard_stationary')
        self.base = base
        self.raw = RawRosRecorder(raw_path, serializer=serialize_message) if raw_path is not None else None
        self.received_counts = {'odom': 0, 'scan': 0, '/tf': 0, '/tf_static': 0}
        self.moving_command_ns = []
        self.sensor = None
        self.sensor_t = self.guard_t = 0.
        self.reason = ''
        self.rows = []
        self.anchor = None
        self.changed = time.monotonic()
        self.pub = self.node.create_publisher(TwistStamped, 'guarded_cmd_vel', 1)
        self.arm = self.node.create_client(Trigger, 'motion_guard/arm')
        self.stop = self.node.create_client(Trigger, 'motion_guard/stop')
        self.power = self.node.create_client(SetBool, 'motor_power')
        self.node.create_subscription(SensorState, 'sensor_state', self._sensor, qos_profile_sensor_data)
        self.node.create_subscription(String, 'motion_guard/status', self._guard, 1)
        self.enabled = False
        self.navigation = RosObservations()
        self.observation_window = ObservationWindow({'project_id':'default','session_id':'UNBOUND',
            'boot_id':'UNBOUND','release_id':'UNBOUND','source_revision':'UNBOUND','origin':'live_ros'})
        self.observation_sequence = 0
        self.latest_scan_preview = None
        self.latest_scan_fault = 'NOT_RECEIVED'
        self.last_scan_t = 0.
        self.require_scan_fresh = False
        # Passive subscriptions only. No lidar startup, TF assumption or motion gate.
        self.node.create_subscription(Odometry, 'odom', self._odom, qos_profile_sensor_data)
        # The isolated COIN candidate publishes /scan at the root namespace.
        self.node.create_subscription(LaserScan, '/scan', self._scan, qos_profile_sensor_data)
        from rclpy.qos import QoSProfile, DurabilityPolicy
        from tf2_msgs.msg import TFMessage
        self.node.create_subscription(TFMessage, '/tf',
                                      lambda msg: self._tf('/tf',msg), qos_profile_sensor_data)
        static_qos=QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.observation_qos={'odom':qos_profile_sensor_data,'scan':qos_profile_sensor_data,
                             '/tf':qos_profile_sensor_data,'/tf_static':static_qos}
        self.node.create_subscription(TFMessage, '/tf_static',
                                      lambda msg: self._tf('/tf_static',msg),
                                      static_qos)

    def bind_observations(self, context):
        self.observation_window = ObservationWindow(context)

    def observations_since(self, sequence):
        return self.observation_window.events_since(sequence)

    def observation_health(self):
        health=self.observation_window.health_at(time.monotonic_ns())
        from rclpy.qos import qos_check_compatible, QoSCompatibility
        for topic,requested in self.observation_qos.items():
            try:
                infos=self.node.get_publishers_info_by_topic('/scan' if topic=='scan' else topic)
                if len(infos)!=1:
                    health['faults'][topic]='ENDPOINT_MISSING' if not infos else 'ENDPOINT_MULTIPLE_OR_UNKNOWN'
                else:
                    compatible,_=qos_check_compatible(infos[0].qos_profile,requested)
                    if compatible==QoSCompatibility.ERROR:health['faults'][topic]='ENDPOINT_QOS_INCOMPATIBLE'
                    elif compatible==QoSCompatibility.WARNING:health['faults'][topic]='ENDPOINT_QOS_UNVERIFIED'
            except Exception:health['faults'][topic]='ENDPOINT_INSPECTION_FAILED'
        return health

    def _common_observation(self, topic, msg, metadata):
        try: value = from_ros_message(topic, msg)
        except (ValueError,TypeError,AttributeError,OverflowError): value = {}
        self.observation_window.receive(topic,value,metadata['sequence'],metadata['receipt_monotonic_ns'],
            ros_now_ns=self.node.get_clock().now().nanoseconds,
            publishers=self.node.count_publishers('/scan' if topic=='scan' else topic))

    def _tf(self, topic, msg):
        self._common_observation(topic,msg,self._record(topic,msg))

    def _navigation(self,kind,msg):
        # Match the actual subscription. A relative `scan` would resolve to
        # /tp_guard_stationary/scan, while the owned driver publishes /scan.
        topic='/scan' if kind=='scan' else kind
        self.navigation.receive(kind,msg,self.node.get_clock().now().nanoseconds,
                                time.monotonic(),self.node.count_publishers(topic))

    def _record(self, topic, msg):
        receipt = time.monotonic_ns()
        raw = getattr(self, 'raw', None)
        if raw is not None and not raw.record(topic, msg, receipt_monotonic_ns=receipt):
            raise ValueError('RAW_RECORDING_INCOMPLETE')
        counts = getattr(self, 'received_counts', None)
        if counts is not None and topic in counts:
            counts[topic] += 1
        self.observation_sequence = getattr(self,'observation_sequence',0)+1
        metadata = {'sequence':raw.next_sequence-1 if raw is not None else self.observation_sequence,
                    'receipt_monotonic_ns':receipt}
        sink=getattr(self,'record_sink',None)
        if sink is not None:sink(topic,msg,metadata)
        return metadata

    def _odom(self,msg):
        metadata = self._record('odom',msg)
        self._common_observation('odom',msg,metadata)
        self._navigation('odom',msg)

    def _scan(self,msg):
        metadata = self._record('scan',msg)
        self._common_observation('scan',msg,metadata)
        self.last_scan_t = time.monotonic()
        diagnostic={}
        self.latest_scan_preview = scan_preview(msg,self.node.get_clock().now().nanoseconds,self.last_scan_t,diagnostic=diagnostic)
        self.latest_scan_fault = diagnostic['reason']
        self._navigation('scan',msg)

    def scan_preview(self):return getattr(self,'latest_scan_preview',None)

    def scan_display_fault(self):return getattr(self,'latest_scan_fault','NOT_RECEIVED')

    def fresh_scan(self):
        if (self.received_counts['scan'] < 3 or
                time.monotonic() - self.last_scan_t >= .25 or
                self.node.count_publishers('/scan') != 1):
            raise ValueError('ROS_SCAN_STALE_OR_PUBLISHER_UNOWNED')

    def navigation_snapshot(self):return self.navigation.snapshot(time.monotonic())

    def navigation_step(self, mission, binding, command_created_s, *, before_publish=lambda:None):
        """Checked local tick for the explicitly qualified mission owner.

        The owning worker must establish qualification/lease, run a bounded loop,
        and perform independent final OFF. The shipped profile keeps it disabled.
        Both checks use current observations, including after slow motor arming.
        Failure latches the mission and attempts immediate ROS stop/OFF; a stop
        failure remains an error, never a successful arrival.
        """
        def decision():
            self.fresh()
            if self.node.count_publishers('odom')!=1 or self.node.count_publishers('/scan')!=1:
                raise ValueError('NAVIGATION_ENDPOINT_OWNERSHIP')
            snapshot=self.navigation_snapshot()
            now=time.monotonic()
            pose,scan=navigation_inputs(snapshot,binding,now)
            self.current_navigation_snapshot=snapshot
            result=mission.step(pose,scan,now,command_created_s=command_created_s)
            return {**result,'navigation':self.navigation_evidence(snapshot,pose,scan,binding)}
        arm_attempted=False
        try:
            if mission.provenance!='live_sensor' or mission.frame_id!='odom':
                raise ValueError('NAVIGATION_MISSION_SOURCE')
            before_publish()
            result=decision()
            if not result['allowed']:raise ValueError(result['reason'])
            # Current matching and whole-route validation can consume much of
            # a slice. Drain ORIGINAL queued keepalives/Stop before also paying
            # arming latency, with the same gate and command-created timestamp.
            # This cannot renew expired input or fabricate a fresh observation.
            before_publish()
            if not (result['linear_m_s'] or result['angular_rad_s']):
                if self.enabled:
                    if mission.mission.status=='RUNNING':
                        self.publish(0.,0.,time.monotonic()-command_created_s,
                                     navigation_binding=binding,before_publish=before_publish)
                        note=getattr(mission,'note_output',None)
                        if callable(note):note(time.monotonic(),0.,0.)
                    else:self.halt()
                return result
            arm_attempted=True
            reviewed=getattr(mission,'approved_preview',None) is not None
            if reviewed and not self.enabled:
                # Arming can service ROS callbacks and take substantial time.
                # Do NOT spend that time and two full observed-route decisions
                # in one command slice. Recheck source/scan/age after arming,
                # publish no movement, then let the owning loop pump inputs and
                # receive a fresh observation before the next decision. The
                # original gate, mission clock and first-output review remain.
                self.enable();before_publish()
                self.navigation_stop_check(binding,result['linear_m_s'],result['angular_rad_s'],
                                           time.monotonic()-command_created_s)
                snapshot=self.navigation_snapshot()
                pose,scan=navigation_inputs(snapshot,binding,time.monotonic())
                if hasattr(mission,'current_pose_valid'):mission.current_pose_valid=False
                return {**result,'linear_m_s':0.,'angular_rad_s':0.,
                        'reason':'ARMED_AWAITING_FRESH_REVIEWED_TICK',
                        'navigation':self.navigation_evidence(snapshot,pose,scan,binding)}
            if not reviewed:
                self.enable()
                before_publish()
                result=decision()  # Never publish from a pre-enable scan or pose.
                if not result['allowed']:raise ValueError(result['reason'])
                if not (result['linear_m_s'] or result['angular_rad_s']):
                    if self.enabled:
                        if mission.mission.status=='RUNNING':
                            self.publish(0.,0.,time.monotonic()-command_created_s,
                                         navigation_binding=binding,before_publish=before_publish)
                            note=getattr(mission,'note_output',None)
                            if callable(note):note(time.monotonic(),0.,0.)
                        else:self.halt()
                    return result
            validate=getattr(mission,'validate_first_output',None)
            if callable(validate):validate(time.monotonic())
            published=self.publish(result['linear_m_s'],result['angular_rad_s'],
                         time.monotonic()-command_created_s,navigation_binding=binding,before_publish=before_publish)
            note=getattr(mission,'note_output',None)
            if callable(note):note(time.monotonic(),result['linear_m_s'],result['angular_rad_s'])
            if callable(validate):mission.approved_output_consumed=True
            return published
        except RequestedStop:
            # The owning loop handles the bounded finish/force distinction and
            # unconditionally halts in finally, including after partial arming.
            raise
        except Exception as primary:
            if mission.mission.status in {'RUNNING','ARRIVED'}:mission.mission.stop('NAVIGATION_OUTPUT_FAILED')
            if arm_attempted or self.enabled:
                try:self.halt()
                except Exception as cleanup:
                    from cleanup_notes import retain_cleanup
                    retain_cleanup(primary,'navigation_halt',cleanup)
            raise

    def navigation_stop_check(self,binding,v,w,age):
        self.fresh()
        if self.node.count_publishers('odom')!=1 or self.node.count_publishers('/scan')!=1:
            raise ValueError('NAVIGATION_ENDPOINT_OWNERSHIP')
        _,scan=navigation_inputs(self.navigation_snapshot(),binding,time.monotonic())
        result=checked_command(v,w,age,scan,time.monotonic(),require_scan=True,provenance='live_sensor')
        if not result['allowed']:raise ValueError(result['reason'])

    @staticmethod
    def navigation_evidence(snapshot,pose,scan,binding):
        return {'pose_xy_yaw':list(pose.xy_yaw),'pose_sample_s':pose.sample_s,
                'scan_sample_s':scan.oldest_sample_s,
                'odom_stamp_ns':snapshot['odom']['source_stamp_ns'],
                'scan_stamp_ns':snapshot['scan']['source_stamp_ns'],
                'evidence_sha256':binding.evidence_sha256,
                'clear_radius_m':scan.clear_radius_m,'alignment_verified':False}

    def _sensor(self, msg):
        self._record('sensor_state',msg)
        now = time.monotonic()
        pair = [msg.left_encoder, msg.right_encoder]
        if self.anchor is None or any(abs(a-b) > 2 for a, b in zip(pair, self.anchor)):
            self.anchor, self.changed = pair, now
        self.sensor, self.sensor_t = msg, now
        age = (self.node.get_clock().now().nanoseconds - msg.header.stamp.sec*10**9 - msg.header.stamp.nanosec)/1e9
        self.rows.append({'t': now, 'encoders': pair, 'torque': bool(msg.torque),
                          'voltage_v': float(msg.battery) if math.isfinite(msg.battery) else None,
                          'source_age_s': age})
        if len(self.rows) > 10000:
            if getattr(self,'persistent_manual',False):
                # Release checks use a list cursor. Never move that cursor's
                # backing samples during the bounded stop-observation window.
                if not getattr(self,'release_observing',False):del self.rows[:1000]
                elif len(self.rows)>10100:raise ValueError('SENSOR_BUDGET')
            else:raise ValueError('SENSOR_BUDGET')

    def _guard(self, msg):
        self._record('motion_guard/status',msg)
        self.reason, self.guard_t = msg.data, time.monotonic()

    def spin(self, seconds=.01):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.base.poll() is not None: raise ValueError('BASE_EXITED')
            self.ros.spin_once(self.node, timeout_sec=.005)

    def fresh(self):
        now = time.monotonic()
        if not self.sensor or now-self.sensor_t >= .2 or now-self.guard_t >= .2:
            raise ValueError('TELEMETRY_STALE')
        s = self.sensor
        age = (self.node.get_clock().now().nanoseconds - s.header.stamp.sec*10**9-s.header.stamp.nanosec)/1e9
        if (not 0 <= age < .2 or not math.isfinite(s.battery) or s.battery <= 11.1 or s.button):
            raise ValueError('BATTERY_BUTTON_OR_SOURCE_AGE')
        if (self.node.count_publishers('guarded_cmd_vel') != 1 or self.pub.get_subscription_count() != 1
                or self.node.count_publishers('cmd_vel') != 0
                or self.node.count_publishers('sensor_state') != 1
                or self.node.count_publishers('motion_guard/status') != 1):
            raise ValueError('ENDPOINT_OWNERSHIP')

    def call(self, client, request):
        if not client.service_is_ready(): raise ValueError('SERVICE_UNAVAILABLE')
        future = client.call_async(request)
        end = time.monotonic() + .5
        while not future.done() and time.monotonic() < end: self.spin(.005)
        if not future.done() or future.exception() or not future.result().success:
            raise ValueError('SERVICE_FAILED')

    def task_resources(self):
        self.fresh()
        s=self.sensor
        age=(self.node.get_clock().now().nanoseconds-s.header.stamp.sec*10**9-s.header.stamp.nanosec)/1e9
        return {'schema':'task-resources-1.0','sample_s':self.sensor_t,'source_age_s':age,
                'voltage_v':float(s.battery),'motor_disabled':not self.enabled and not bool(s.torque)}

    def torque(self, enabled):
        request = self.Power.Request(); request.data = enabled
        self.call(self.power, request)

    def preflight(self):
        end = time.monotonic() + 12
        while time.monotonic() < end:
            safety=getattr(self,'preflight_safety',None)
            if safety is not None:safety()
            self.spin(.02)
            if (len(self.rows) >= 10 and self.arm.service_is_ready() and self.stop.service_is_ready()
                    and self.power.service_is_ready() and self.pub.get_subscription_count() == 1): break
        self.spin(.25); self.fresh()
        if self.sensor.torque or self.reason != 'explicit_stop' or time.monotonic()-self.changed < .2:
            raise ValueError('INITIAL_IDLE_UNCONFIRMED')

    def enable(self):
        self.fresh()
        if self.enabled: return
        before = [self.sensor.left_encoder, self.sensor.right_encoder]
        self.call(self.stop, self.Trigger.Request())
        self.torque(True)
        self.spin(.06); self.fresh()
        if not self.sensor.torque or any(abs(a-b)>2 for a,b in zip(before,[self.sensor.left_encoder,self.sensor.right_encoder])):
            raise ValueError('ENABLE_READBACK_OR_UNEXPECTED_MOVEMENT')
        self.call(self.arm, self.Trigger.Request())
        self.enabled = True

    def publish(self, v, w, source_age, *, navigation_binding=None, before_publish=None):
        started=time.monotonic()
        source_created=started-source_age if type(source_age) in (int,float) else None
        self.fresh()
        if before_publish is not None:
            before_publish()
            self.fresh()
        if getattr(self, 'require_scan_fresh', False):
            self.fresh_scan()
        if not self.sensor.torque or self.reason not in {'explicit_stop', 'armed_waiting_for_command', 'active'}:
            raise ValueError('GUARD_OR_TORQUE_STOP')
        scan=None;navigation=None
        if navigation_binding is not None:
            if self.node.count_publishers('odom')!=1 or self.node.count_publishers('/scan')!=1:
                raise ValueError('NAVIGATION_ENDPOINT_OWNERSHIP')
            snapshot=self.navigation_snapshot()
            pose,scan=navigation_inputs(snapshot,navigation_binding,time.monotonic())
            navigation=self.navigation_evidence(snapshot,pose,scan,navigation_binding)
        # Account for work in this final output boundary, not only the caller's age.
        if source_created is not None:
            source_age=time.monotonic()-source_created
        decision=checked_command(v,w,source_age,scan,time.monotonic(),
                                 require_scan=navigation_binding is not None,provenance='live_sensor',
                                 supervised_manual=getattr(self,'manual_speed_profile',False) is True and navigation_binding is None)
        if not decision['allowed']:raise ValueError(decision['reason'])
        msg = self.Twist(); msg.header.frame_id = 'base_link'
        stamp = self.node.get_clock().now().nanoseconds - int(source_age*10**9)
        msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp, 10**9)
        msg.twist.linear.x, msg.twist.angular.z = float(v), float(w)
        RosLink._record(self,'guarded_cmd_vel',msg)
        # Recording/enqueue is part of the original input age, never a fresh lease.
        if source_created is not None and time.monotonic()-source_created>=.25:
            raise ValueError('INPUT_DEADLINE_EXPIRED')
        # The fleet owner installs this measured native guard. It runs at the
        # actual publisher boundary, after recording and arming work. Legacy
        # sessions are unchanged; absence never authorizes the new fleet path.
        native_guard = getattr(self, 'native_output_guard', None)
        if native_guard is not None:
            native_guard(v, w, source_created)
        if source_created is not None and time.monotonic()-source_created>=.25:
            raise ValueError('INPUT_DEADLINE_EXPIRED')
        if (v or w) and hasattr(self, 'moving_command_ns'):
            self.moving_command_ns.append(time.monotonic_ns())
            if getattr(self,'persistent_manual',False) and len(self.moving_command_ns)>10000:
                del self.moving_command_ns[:1000]
        self.pub.publish(msg)
        return {**decision,'navigation':navigation,'published_source_age_s':source_age} if navigation is not None else decision

    def halt(self):
        self.enabled = False
        errors = []
        for action in (lambda: self.call(self.stop,self.Trigger.Request()), lambda: self.torque(False)):
            try: action()
            except Exception as exc: errors.append(type(exc).__name__)
        self.spin(.25); self.fresh()
        if errors or self.sensor.torque or time.monotonic()-self.changed < .2:
            raise ValueError('STOP_READBACK_UNCONFIRMED')

    def release(self):
        self.release_observing=True
        try:return self._release()
        finally:self.release_observing=False

    def _release(self):
        """Ordinary key release: stop/OFF immediately, then bounded readback.

        This does not mint qualification or replace final independent OFF.
        Keep the 2-tick / 200ms idle requirement, but do not confuse the old
        250ms cleanup wait with the time available to observe a moving release.
        No command is published while waiting; re-arm needs a new input.
        """
        self.enabled = False
        start = time.monotonic()
        index = len(self.rows)
        previous = [self.sensor.left_encoder, self.sensor.right_encoder]
        travel = [0, 0]
        errors = []
        for action in (lambda: self.call(self.stop, self.Trigger.Request()), lambda: self.torque(False)):
            try: action()
            except Exception as exc: errors.append(type(exc).__name__)
        if errors: raise ValueError('RELEASE_SERVICE_UNCONFIRMED')
        end = start + OBSERVE_S + POLICY['max_sample_gap_s']
        while time.monotonic() < end:
            self.spin(.005); self.fresh()
            for row in self.rows[index:]:
                for i in range(2): travel[i] += abs(row['encoders'][i]-previous[i])
                previous = row['encoders']
            index = len(self.rows)
            if max(travel)*MM_PER_TICK > POLICY['wheel_travel_limit_mm']:
                raise ValueError('RELEASE_TRAVEL_EXCEEDED')
            if (not self.sensor.torque and self.reason == 'explicit_stop'
                    and time.monotonic()-max(self.changed, start) >= .2):
                return
        raise ValueError('RELEASE_IDLE_UNCONFIRMED')

    def close(self):
        try:
            self.node.destroy_node()
            self.ros.shutdown()
        finally:
            raw_result = self.raw.close() if self.raw is not None else None
        return raw_result
