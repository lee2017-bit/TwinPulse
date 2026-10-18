# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reviewed robot-local adapter; the existing worker owns devices and cleanup.

This never opens ROS, serial or a subprocess. The fixed qualification document
must be reviewed and byte-bound to the release; none is shipped for this robot.
"""
from mission_runtime import read_document
from twinpulse_core.current_mission_evidence import CurrentMissionEvidence,IdleCurrentEvidence
from twinpulse_core.observed_mission import ObservedMission
from twinpulse_core.cold_start_mission import ColdStartMission
from twinpulse_core.adaptive_mission_contract import adaptive_scope
from twinpulse_core.mission_correction_contract import correction_proposal,checked_reply
import secrets
import threading
from twinpulse_core.mission_evidence_contract import mission_evidence, evidence_bytes, FILE_NAME


def reviewed_observed_release(release, manifest, calibration_hash):
    if not (release/'adaptive-qualification.json').is_file():raise ValueError('ADAPTIVE_QUALIFICATION_MISSING')
    record, digest = read_document(release/'adaptive-qualification.json')
    if manifest['files'].get('adaptive-qualification.json') != digest:
        raise ValueError('ADAPTIVE_QUALIFICATION_NOT_IN_RELEASE')
    keys = {'schema', 'basis', 'timing_basis', 'transform_basis', 'calibration_sha256',
            'guard_sha256', 'evidence_file', 'evidence_sha256'}
    if (set(record) != keys or record['schema'] != 'adaptive-qualification-1.0'
            or record['basis'] != 'REVIEWED_TARGET_AND_SENSOR_EVIDENCE'
            or record['timing_basis'] != 'VERIFIED_ACQUISITION'
            or record['transform_basis'] != 'measured_sensor_extrinsic'
            or record['calibration_sha256'] != calibration_hash
            or record['guard_sha256'] != manifest['files'].get('bin/turtlebot3_ros')
            or record['evidence_file'] != 'adaptive-sensor-evidence.json'
            or record['evidence_sha256'] != manifest['files'].get('adaptive-sensor-evidence.json')):
        raise ValueError('ADAPTIVE_QUALIFICATION_CONTEXT')
    # Require the reviewed evidence bytes, not only a browser flag or digest.
    if not (release/'adaptive-sensor-evidence.json').is_file():raise ValueError('ADAPTIVE_QUALIFICATION_EVIDENCE_MISSING')
    evidence, evidence_hash = read_document(release/'adaptive-sensor-evidence.json')
    if evidence_hash != record['evidence_sha256'] or not evidence:
        raise ValueError('ADAPTIVE_QUALIFICATION_EVIDENCE')
    return record


class RobotObservedFactory:
    def __init__(self, link, request, *, output, clock):
        self.link = link; self.request = request; self.output = output; self.clock = clock
        self.scope = adaptive_scope(request['adaptive_scope'])
        self.context = dict(link.observation_window.context)
        if self.context['project_id'] != self.scope['project_id'] or self.context['origin'] != 'live_ros':
            raise ValueError('ADAPTIVE_CURRENT_SOURCE_CONTEXT')
        full=request.get('full_reference')
        if self.scope['schema']=='observed-mission-scope-6.0':
            from twinpulse_core.reference_transport import checked_reference
            full=checked_reference(full,self.scope)
        reference=full['map'] if full else self.scope['reference']
        alignment=full['photo_alignment'] if full else self.scope['alignment']
        self.tracker = CurrentMissionEvidence(reference, alignment,
            self.context, self.scope['goal']['room_revision'], local_survey=self.scope['goal']['mode']!='NAVIGATE_TWIN_GOAL')
        self.mission = None; self.last_emit = -1.
        self.latest_resources=None
        self.idle_evidence=IdleCurrentEvidence(self.tracker,self.link.observation_window,self.request['binding'],
            snapshot=self.idle_snapshot,disabled=lambda:getattr(self.link,'enabled',None) is False,clock=self.clock)
        self.correction_lock=threading.RLock();self.proposal=None;self.reply=None;self.proposal_sent=False

    def commit_correction(self,result,cancelled):
        # Only the control thread emits the proposal AFTER a zero-output tick.
        # Waiting in the fit thread must not block scan/input/Stop processing.
        with self.correction_lock:
            if self.proposal is not None:raise ValueError('CORRECTION_ALREADY_CONSUMED')
            self.proposal=correction_proposal(self.scope,self.request['mission_id'],
                self.request['request_sha256'],secrets.token_hex(12),result,self.clock())
        while True:
            if cancelled.wait(.005):raise ValueError('MISSION_CORRECTION_CANCELLED_OR_EXPIRED')
            with self.correction_lock:
                if self.clock()>=self.proposal['expires_s']:raise ValueError('CORRECTION_ACK_EXPIRED')
                if self.reply is not None:
                    if self.reply['reason']:raise ValueError(self.reply['reason'])
                    return self.reply['binding']

    def accept_correction(self,packet):
        with self.correction_lock:
            if (self.proposal is None or not self.proposal_sent or self.reply is not None or self.mission is None
                    or self.mission.cancelled.is_set() or self.mission.stage!='ALIGN'
                    or self.mission.proposed!=(0.,0.) or self.mission.mission.status!='RUNNING'):
                raise ValueError('CORRECTION_ACK_REQUIRES_OWNED_IDLE')
            reply=checked_reply(packet,self.proposal,self.scope,self.clock())
            self.output({'state':'ADAPTIVE_CORRECTION_ACCEPTED','proposal_revision':self.proposal['revision'],
                         'reply_revision':reply['revision'],'binding':reply['binding'],'reason':reply['reason']})
            self.reply=reply

    def current(self, pose, now):
        return self.current_with(self.tracker,pose,now)

    def idle_snapshot(self):
        self.link.fresh();self.link.fresh_scan()
        return self.link.navigation_snapshot()

    def preview_current(self):
        # Only the native owning worker can call this while it holds its idle
        # link. No ROS/serial startup or saved terminal-pose restoration here.
        evidence=self.idle_evidence.sample()
        resources=getattr(self.link,'task_resources',None)
        if callable(resources):evidence={**evidence,'task_resources':resources()}
        return evidence

    def current_with(self,tracker,pose,now):
        # Matching uses the same current ROS stream, not the last saved pose.
        self.link.fresh_scan()
        snapshot=getattr(self.link,'current_navigation_snapshot',None)
        if snapshot is None:raise ValueError('ADAPTIVE_TICK_SNAPSHOT_REQUIRED')
        value=tracker.update_window(self.link.observation_window,
            snapshot, self.request['binding'], now)
        resources=getattr(self.link,'task_resources',None)
        self.latest_resources=resources() if callable(resources) else None
        return value

    def prepare(self):
        # Global matching can be slow. Do it with wheels disabled, BEFORE the
        # short input gate is created. The result is only a hypothesis: every
        # output still rechecks new source data after this operation completes.
        if getattr(self.link,'enabled',False):raise ValueError('ADAPTIVE_BOOTSTRAP_REQUIRES_WHEELS_OFF')
        self.output({'state':'PREPARING','mode':'mission','reason':'CURRENT_LOCALIZATION_WHEELS_DISABLED'})
        snapshot=self.link.navigation_snapshot()
        now=self.clock()
        value=self.tracker.update_window(self.link.observation_window,snapshot,self.request['binding'],now)
        if value['state'] not in {'TRACKING_CANDIDATE','SESSION_LOCAL_OBSERVED'}:
            raise ValueError('ADAPTIVE_INITIAL_LOCALIZATION_'+value['state'])
        self.link.spin(.01)
        self.link.fresh()
        if self.scope['goal']['mode']=='NAVIGATE_TWIN_GOAL':
            # Slow global search was only a seed. Read a new disabled-wheel
            # sample and verify processing age before publishing any preview.
            self.preview_current()

    def __call__(self, started):
        if self.scope.get('phase')=='IDLE_LOCALIZATION_ONLY':
            raise ValueError('IDLE_LOCALIZATION_CANNOT_EXECUTE_MISSION')
        self.idle_evidence.handoff()
        if self.scope['goal']['mode'] in {'SURVEY_THEN_NAVIGATE','SURVEY_ONLY'}:
            self.mission=ColdStartMission(self.scope['goal'],started,tracker=self.tracker,current=self.current_with,
                nominal=self.scope['nominal'],provenance='live_sensor',frame_id='odom',context=self.context,
                photo_policy='correct_walls' if self.scope['schema'] in {'observed-mission-scope-3.0','observed-mission-scope-5.0'} else 'align_only',
                commit_correction=self.commit_correction)
        else:
            self.mission = ObservedMission(self.scope['goal'], started, provider=self.current,
                provenance='live_sensor', frame_id='odom', context=self.context,
                approved_preview=getattr(self,'approved_preview',None))
        return self.mission

    def accept_goal_handoff(self,value):
        from twinpulse_core.reference_transport import checked_goal_handoff
        # New source sample after the entire transfer, still wheel-disabled.
        evidence=self.preview_current()
        checked=checked_goal_handoff(value,self.scope,self.request['mission_id'],
            evidence,self.context,self.clock())
        sink=getattr(self,'handoff_sink',None)
        if callable(sink):sink(checked)
        self.scope=checked['scope'];self.approved_preview=checked['preview']
        self.request['adaptive_scope']=self.scope
        self.request['duration_s']=self.scope['goal']['duration_s']
        self.idle_evidence.handoff()
        return checked

    def record_visual(self):
        with self.correction_lock:
            if (self.proposal is not None and not self.proposal_sent and self.mission
                    and self.mission.stage=='ALIGN' and self.mission.proposed==(0.,0.)
                    and not self.mission.cancelled.is_set()):
                self.proposal_sent=True
                self.output({'state':'ADAPTIVE_CORRECTION_PROPOSAL','proposal':self.proposal})
        if self.mission and self.clock()-self.last_emit >= .2:
            self.last_emit = self.clock()
            self.output({'state':'ADAPTIVE_VISUAL', 'visual':self.mission.visual(self.request['mission_id'])})
            if isinstance(self.mission,ObservedMission):
                from twinpulse_core.mission_telemetry import telemetry
                self.output({'state':'ADAPTIVE_TELEMETRY','telemetry':telemetry(self.mission,
                    self.request['mission_id'],self.scope,self.latest_resources,self.clock())})

    def visual(self):
        return self.mission.visual(self.request['mission_id']) if self.mission else None

    def save_evidence(self, directory):
        """Call only after independent motor/sensor cleanup; never stdout-map.

        Exclusive historical file, bound to the original request and source.
        Interrupted/failed fit remains evidence, never a successful alignment.
        """
        import os
        from pathlib import Path
        idle=getattr(self,'idle_evidence',None)
        if idle is not None:idle.close()
        mission = self.mission
        if mission is None or getattr(mission,'survey_map',None) is None:
            return None
        worker = getattr(mission,'worker',None)
        if worker is not None and worker.is_alive():
            raise ValueError('MISSION_EVIDENCE_FIT_STILL_RUNNING')
        value = mission_evidence(self.scope,self.request['mission_id'],
            self.request['request_sha256'],self.context,mission.survey_map,mission.fit_result)
        data, descriptor = evidence_bytes(value)
        path = Path(directory)/FILE_NAME
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError('MISSION_EVIDENCE_PATH_UNSAFE')
        with path.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        return descriptor
