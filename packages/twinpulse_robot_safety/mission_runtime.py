# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Robot-local bounded mission loop; no connection, deployment or sensor startup.

The existing worker owns qualification, flock, base watchdog and final OFF.
The shipped profile does not opt into this entry and ships no calibration.
"""
import hashlib
import json
import math
import re
import secrets
import time
import sys
from cleanup_notes import retain_cleanup

from teleop_contract import InputGate, DIRECTIONS, TERMINAL_STOPS, RequestedStop, finish_segment
try:
    from twinpulse_core.local_navigation import CheckedMission, finite
    from twinpulse_core.navigation_binding import PlanarBinding
except ModuleNotFoundError as exc:
    if exc.name not in {'twinpulse_core','twinpulse_core.local_navigation','twinpulse_core.navigation_binding'}:raise
    from local_navigation import CheckedMission, finite
    from navigation_binding import PlanarBinding

POLICY='qualified_session_reviewed_planar_frames_v1'
try:
    from mission_contract import bootstrap_packet, document_hash
except ModuleNotFoundError:
    from twinpulse_core.mission_contract import bootstrap_packet, document_hash


def read_document(path):
    if path.is_symlink() or path.resolve()!=path.absolute():raise ValueError('MISSION_FILE_PATH')
    with path.open('rb') as stream:raw=stream.read(16385)
    if len(raw)>16384:raise ValueError('MISSION_FILE_SIZE')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('MISSION_DUPLICATE_KEY')
            result[key]=value
        return result
    def invalid(_):raise ValueError('MISSION_NONFINITE_JSON')
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=invalid)
    if not isinstance(value,dict):raise ValueError('MISSION_DOCUMENT_SHAPE')
    return value,hashlib.sha256(raw).hexdigest()


def load_calibration(release, manifest):
    """Fixed files, fresh same-boot request, calibration bytes in reviewed release.

    Hash binding is integrity, not independent verification of calibration or
    user consent. Only an explicitly approved, reviewed deployment may opt in.
    No photo/synthetic calibration is accepted as a robot calibration record.
    """
    if not (release/'navigation-calibration.json').is_file():raise ValueError('MISSION_CALIBRATION_MISSING')
    calibration,calibration_hash=read_document(release/'navigation-calibration.json')
    if manifest['files'].get('navigation-calibration.json')!=calibration_hash:
        raise ValueError('MISSION_CALIBRATION_NOT_IN_RELEASE')
    keys={'schema','basis','odom_child_frame','scan_frame','child_to_base','base_to_scan',
          'footprint_radius_m','evidence_sha256','guard_sha256','namespace'}
    if (set(calibration)!=keys or calibration['schema']!='planar-calibration-1.0'
            or calibration['basis']!='reviewed_robot_frames'
            or calibration['namespace']!='/tp_guard_stationary'
            or calibration['guard_sha256']!=manifest['files'].get('bin/turtlebot3_ros')):
        raise ValueError('MISSION_CALIBRATION_CONTEXT')
    for key in ('child_to_base','base_to_scan'):
        if not isinstance(calibration[key],list):raise ValueError('MISSION_CALIBRATION_SHAPE')
    binding=PlanarBinding(calibration['odom_child_frame'],calibration['scan_frame'],
        tuple(calibration['child_to_base']),tuple(calibration['base_to_scan']),
        calibration['footprint_radius_m'],calibration['evidence_sha256'])
    if not binding.valid():raise ValueError('MISSION_CALIBRATION_INVALID')
    return binding,calibration_hash


def validate_request(request, request_hash, binding, calibration_hash, manifest, boot, now):
    adaptive = request.get('schema') == 'robot-observed-mission-request-1.0'
    if adaptive:
        from twinpulse_core.adaptive_mission_contract import adaptive_scope
        if set(request) != {'schema','mission_id','boot_id','release_id','calibration_sha256',
                            'created_s','expires_s','duration_s','adaptive_scope','scope_sha256'}:
            raise ValueError('MISSION_REQUEST_SHAPE')
        scope = adaptive_scope(request['adaptive_scope'])
        if request['scope_sha256'] != document_hash(scope) or request['duration_s'] != scope['goal']['duration_s']:
            raise ValueError('ADAPTIVE_REQUEST_SCOPE_CHANGED')
        # Reuse all legacy boot/release/time validation; the placeholder is
        # never followed. The actual factory plans from fresh observations.
        legacy = {k:v for k,v in request.items() if k not in {'adaptive_scope','scope_sha256'}}
        legacy.update(schema='robot-mission-request-1.0',waypoints=[[0.,0.]])
        checked = validate_request(legacy, request_hash, binding, calibration_hash, manifest, boot, now)
        return {**checked, 'adaptive_scope': scope, 'scope_sha256': request['scope_sha256']}
    if set(request)!={'schema','mission_id','boot_id','release_id','calibration_sha256',
                       'created_s','expires_s','duration_s','waypoints'}:
        raise ValueError('MISSION_REQUEST_SHAPE')
    if (request['schema']!='robot-mission-request-1.0' or request['boot_id']!=boot
            or request['release_id']!=manifest['source_id'] or request['calibration_sha256']!=calibration_hash
            or not isinstance(request['mission_id'],str) or not re.fullmatch('[a-f0-9]{32}',request['mission_id'])):
        raise ValueError('MISSION_REQUEST_CONTEXT')
    if (not all(finite(x) for x in (now,request['created_s'],request['expires_s'],request['duration_s']))
            or not 0<=request['created_s']<=now<request['expires_s']<=request['created_s']+90
            or not 0<request['duration_s']<=45):raise ValueError('MISSION_REQUEST_EXPIRED_OR_DURATION')
    points=request['waypoints']
    if not isinstance(points,list) or any(not isinstance(p,list) for p in points):
        raise ValueError('MISSION_REQUEST_WAYPOINTS')
    points=tuple(tuple(p) for p in points)
    # Validate without starting a clock or granting any execution permission.
    CheckedMission(points,now,provenance='live_sensor',frame_id='odom',duration_s=request['duration_s'])
    return {**request,'waypoints':points,'request_sha256':request_hash,'binding':binding}


def load_request(release, state, manifest, boot, now):
    binding,calibration_hash=load_calibration(release,manifest)
    request,request_hash=read_document(state/'mission-request.json')
    return validate_request(request,request_hash,binding,calibration_hash,manifest,boot,now)


def receive_request(release, manifest, boot, incoming, output, *, clock=time.monotonic, sleep=time.sleep):
    """One bounded stdin bootstrap before devices; no shared request-file overwrite.

    Robot monotonic context avoids treating the PC clock as the robot clock.
    It is consumed once in this worker; an old context/nonce cannot start a new one.
    """
    binding,calibration_hash=load_calibration(release,manifest)
    issued=clock()
    context={'state':'MISSION_CONTEXT','boot_id':boot,'release_id':manifest['source_id'],
             'calibration_sha256':calibration_hash,'issued_s':issued,'nonce':secrets.token_hex(12)}
    output(context)
    while True:
        now=clock()
        if not finite(now) or not issued<=now<issued+2:raise ValueError('MISSION_BOOTSTRAP_EXPIRED')
        packet=incoming.receive()
        if packet is None:sleep(.005);continue
        if (not isinstance(packet,dict) or set(packet)!={'action','nonce','request'}
                or packet['action']!='mission_request' or packet['nonce']!=context['nonce']
                or not isinstance(packet['request'],dict)):
            raise ValueError('MISSION_BOOTSTRAP_INVALID')
        request=packet['request']
        if request.get('schema') == 'robot-observed-mission-request-1.0':
            from twinpulse_core.adaptive_mission_contract import adaptive_bootstrap
            expected=adaptive_bootstrap(context,request.get('mission_id'),request.get('adaptive_scope'))
        else:
            expected=bootstrap_packet(context,request.get('mission_id'),{'frame_id':'odom',
                'waypoints':request.get('waypoints'),'duration_s':request.get('duration_s')})
        if packet!=expected:raise ValueError('MISSION_BOOTSTRAP_CONTEXT')
        result=validate_request(request,document_hash(request),binding,calibration_hash,manifest,boot,now)
        if request.get('adaptive_scope',{}).get('schema')=='observed-mission-scope-6.0':
            from twinpulse_core.reference_transport import ReferenceReceiver,checked_reference
            receiver=ReferenceReceiver(request['adaptive_scope']['reference']['payload'],context['nonce'])
            deadline=clock()+30.;previous=clock()
            while not receiver.done:
                output({'state':'REFERENCE_NEXT','nonce':context['nonce'],'index':receiver.index})
                while True:
                    now=clock()
                    if not finite(now) or now<previous or now>=deadline:raise ValueError('REFERENCE_TRANSPORT_EXPIRED')
                    previous=now;part=incoming.receive()
                    if part is not None:break
                    sleep(.005)
                if isinstance(part,dict) and part.get('action') in {'close','force_stop','finish_stop','stop'}:
                    raise ValueError('REFERENCE_TRANSPORT_CANCELLED')
                value=receiver.accept(part)
            result['full_reference']=checked_reference(value,result['adaptive_scope'])
        return result


def run_idle_localization(link,incoming,output,request,factory,*,clock=time.monotonic,safety=lambda:None,record=None,consume=None):
    """Scoped no-motion worker. Query data never renews the input watchdog.

    Every query samples again. Only an explicit exact-plan transfer can enter
    driving in this same worker; it retains the input gate and original 45s
    budget. Refresh/query alone never authorizes movement.
    """
    from twinpulse_core.reference_transport import hex_id,observation_packet,ReferenceSender,encode,OBSERVATION_CHUNK
    if request['adaptive_scope'].get('phase')!='IDLE_LOCALIZATION_ONLY':
        raise ValueError('IDLE_LOCALIZATION_SCOPE_REQUIRED')
    gate=InputGate(clock);start=clock();previous=start;emitted=-math.inf;queries=set();pending=None
    handoff=None;handoff_deadline=None
    try:
        while True:
            now=clock();safety();link.fresh()
            if not finite(now) or now<previous:raise ValueError('IDLE_LOCALIZATION_CLOCK_FAULT')
            previous=now
            if now>=request['expires_s'] or now-start>=45.:raise ValueError('IDLE_LOCALIZATION_EXPIRED')
            if getattr(link,'enabled',None) is not False:raise ValueError('IDLE_LOCALIZATION_WHEELS_NOT_DISABLED')
            gate.check()
            if now-emitted>=.05:
                output({'state':'READY','mode':'localize','challenge':gate.challenge(),'input_sequence':gate.sequence})
                emitted=now
            for _ in range(8):
                packet=incoming.receive()
                if packet is None:break
                if type(packet) is dict and packet.get('action')=='goal_handoff_begin':
                    from twinpulse_core.reference_transport import ReferenceReceiver
                    if (set(packet)!={'action','payload','nonce'} or pending is not None or handoff is not None
                            or not gate.active or record is None or consume is None):
                        raise ValueError('GOAL_HANDOFF_NOT_AVAILABLE')
                    gate.check();handoff=ReferenceReceiver(packet['payload'],packet['nonce'])
                    handoff_deadline=min(start+45.,clock()+2.)
                    output({'state':'GOAL_HANDOFF_NEXT','nonce':handoff.nonce,'index':0})
                elif type(packet) is dict and packet.get('action')=='reference_chunk':
                    if handoff is None:raise ValueError('UNEXPECTED_GOAL_HANDOFF_CHUNK')
                    gate.check()
                    if clock()>=handoff_deadline:raise ValueError('GOAL_HANDOFF_TRANSFER_EXPIRED')
                    value=handoff.accept(packet)
                    if value is None:
                        output({'state':'GOAL_HANDOFF_NEXT','nonce':handoff.nonce,'index':handoff.index})
                    else:
                        safety();link.fresh();gate.check()
                        checked=factory.accept_goal_handoff(value)
                        gate.check();safety();link.fresh()
                        if getattr(link,'enabled',None) is not False:raise ValueError('GOAL_HANDOFF_WHEELS_NOT_DISABLED')
                        # No new clock budget or InputGate: preparing/previewing
                        # counts against the original bounded 45-second session.
                        request['expires_s']=min(request['expires_s'],start+45.)
                        if clock()>=request['expires_s']:raise ValueError('GOAL_HANDOFF_SESSION_EXPIRED')
                        output({'state':'GOAL_HANDOFF_ACCEPTED','plan_id':checked['preview']['plan_id'],
                            'payload':handoff.descriptor,'scope':checked['scope']})
                        return run_mission(link,incoming,output,request,record=record,consume=consume,
                            clock=clock,transport_safety=safety,mission_factory=factory,input_gate=gate)
                elif type(packet) is dict and packet.get('action')=='localization_query':
                    if handoff is not None:raise ValueError('GOAL_HANDOFF_QUERY_REJECTED')
                    if (set(packet)!={'action','query_id'} or not hex_id(packet['query_id'],32)
                            or packet['query_id'] in queries or len(queries)>=256 or pending is not None):
                        raise ValueError('IDLE_LOCALIZATION_QUERY_INVALID')
                    gate.check()
                    if not gate.active:raise ValueError('IDLE_LOCALIZATION_INPUT_REQUIRED')
                    received_s=clock();queries.add(packet['query_id']);value=factory.preview_current()
                    answer=observation_packet(packet['query_id'],value,clock(),received_s=received_s)
                    gate.check();safety();link.fresh()
                    if getattr(link,'enabled',None) is not False:raise ValueError('IDLE_LOCALIZATION_WHEELS_NOT_DISABLED')
                    if not 0<=clock()-value['sample_s']<.2:raise ValueError('IDLE_LOCALIZATION_CURRENT_EVIDENCE_STALE')
                    if len(encode(answer,4*1024*1024))<=60000:output(answer)
                    else:
                        pending={'sender':ReferenceSender(answer,chunk_size=OBSERVATION_CHUNK),'query_id':packet['query_id'],'sample_s':value['sample_s']}
                        output({'state':'LOCALIZATION_BEGIN','query_id':packet['query_id'],
                                'payload':pending['sender'].descriptor})
                elif type(packet) is dict and packet.get('action')=='localization_next':
                    if (set(packet)!={'action','query_id','index'} or pending is None
                            or packet['query_id']!=pending['query_id']):
                        raise ValueError('IDLE_LOCALIZATION_ACK_INVALID')
                    gate.check();safety();link.fresh()
                    if getattr(link,'enabled',None) is not False:raise ValueError('IDLE_LOCALIZATION_WHEELS_NOT_DISABLED')
                    if not 0<=clock()-pending['sample_s']<.2:raise ValueError('IDLE_LOCALIZATION_CURRENT_EVIDENCE_STALE')
                    sender=pending['sender'];chunk=sender.chunk(packet['query_id'][:24],packet['index'])
                    output({'state':'LOCALIZATION_CHUNK','query_id':packet['query_id'],'chunk':chunk})
                    if sender.index*sender.chunk_size>=len(sender.raw):pending=None
                else:
                    action,age=gate.accept(packet)
                    # Match the driving loop's input evidence. Query/reference
                    # packets never renew the gate, and clock domains remain
                    # separate; this records acceptance, not inferred delivery.
                    if record is not None:
                        record('accepted',sequence=packet['sequence'],action=action,source_age_s=age)
                    if action in {'close','stop','finish_stop','force_stop'}:
                        return {'status':'MISSION_CANCELLED','reason':None,'idle_close_reason':'IDLE_LOCALIZATION_CLOSED_NO_MOTION'}
                    if action!='watch':raise ValueError('IDLE_LOCALIZATION_DIRECTION_REJECTED')
            gate.check()
            if not gate.active and now-start>=2.:raise ValueError('NO_OPERATOR_INPUT')
            link.spin(.005)
    finally:factory.idle_evidence.close()


def run_mission(link, incoming, output, request, *, record, consume, clock=time.monotonic,
                transport_safety=lambda:None, mission_factory=None,input_gate=None):
    """One mission consent, local decisions, automatic challenge heartbeat only.

    No per-direction approval. watch retains link liveness, not permission to
    override a blocked mission. Existing 250ms input/60s session limits remain.
    The lower base command-expiry watchdog is still required for a stalled loop.
    A host Python loop is not an independently certified emergency-stop system.
    """
    gate=input_gate if input_gate is not None else InputGate(clock);first_deadline=clock()+2;last_clock=clock()
    last_emit=last_tick=last_raw=-math.inf;mission=None;tick=0;status='FAILED'
    last_output_s=None;last_velocity=(0.,0.)

    def pump():
        nonlocal last_clock,last_emit
        now=clock()
        transport_safety()
        if not finite(now) or now<last_clock:raise ValueError('MISSION_CLOCK_FAULT')
        last_clock=now
        gate.check()
        if now>=request['expires_s']:raise ValueError('MISSION_REQUEST_EXPIRED')
        if mission is not None and now>=mission.mission.end:raise ValueError('MISSION_EXPIRED')
        if now-last_emit>=.05:
            output({'state':'READY','mode':'mission','challenge':gate.challenge(),'input_sequence':gate.sequence})
            last_emit=now
        # Drain bounded queued keepalives/cancellation before any motor output.
        for _ in range(8):
            packet=incoming.receive()
            if packet is None:break
            if isinstance(packet,dict) and packet.get('action')=='correction_reply':
                if mission_factory is None or not hasattr(mission_factory,'accept_correction'):
                    raise ValueError('UNEXPECTED_CORRECTION_ACK')
                mission_factory.accept_correction(packet)
                # A correction is data, NOT input freshness or a new budget.
                gate.check()
                continue
            action,age=gate.accept(packet)
            record('accepted',sequence=packet['sequence'],action=action,source_age_s=age)
            if action in TERMINAL_STOPS:raise RequestedStop(action,packet['sequence'])
            if action in {'stop','close'}:raise ValueError('MISSION_CANCELLED')
            if action!='watch':raise ValueError('MISSION_REMOTE_DIRECTION_REJECTED')
        gate.check()
        if not gate.active and now>=first_deadline:raise ValueError('NO_OPERATOR_INPUT')

    try:
        while True:
            pump()
            if gate.active and mission is None:
                consume()  # Exclusive persisted marker; no retry of the same request.
                mission=(mission_factory(clock()) if mission_factory is not None else
                    CheckedMission(request['waypoints'],clock(),provenance='live_sensor',
                    frame_id='odom',duration_s=request['duration_s']))
                record('mission_started',mission_id=request['mission_id'],request_sha256=request['request_sha256'])
            now=clock()
            if mission is not None and now-last_tick>=.05:
                if now-last_raw>=1.:
                    record('navigation',snapshot=link.navigation_snapshot());last_raw=now
                tick+=1
                if tick>1000:raise ValueError('MISSION_TICK_BUDGET')
                created=clock()
                result=link.navigation_step(mission,request['binding'],created,before_publish=pump)
                if result['linear_m_s'] or result['angular_rad_s']:
                    last_output_s=clock();last_velocity=(result['linear_m_s'],result['angular_rad_s'])
                record('mission_decision',tick=tick,mission_id=request['mission_id'],
                       status=mission.mission.status,decision=result)
                v,w=result['linear_m_s'],result['angular_rad_s']
                if v or w:
                    action=next(name for name,pair in DIRECTIONS.items() if pair==(v,w))
                    record('published',sequence=tick,action=action,linear_m_s=v,
                           angular_rad_s=w,source_age_s=result['published_source_age_s'])
                if getattr(link,'rows',None):record('observation',sample=link.rows[-1],guard=link.reason)
                last_tick=clock()
                if mission.mission.status=='ARRIVED':status='MISSION_ARRIVED';break
            link.spin(.005);link.fresh()
    except RequestedStop as exc:
        record('stop_requested',sequence=exc.sequence,action=exc.action)
        def safety():
            transport_safety()
            if clock()>=request['expires_s'] or (mission is not None and clock()>=mission.mission.end):
                raise ValueError('MISSION_EXPIRED')
            if last_output_s is not None:
                link.navigation_stop_check(request['binding'],*last_velocity,clock()-last_output_s)
        status=('FORCE_STOPPED' if exc.action=='force_stop' else
                finish_segment(link,incoming,gate,last_output_s,.05,record=record,clock=clock,safety=safety))
    except (Exception,KeyboardInterrupt) as exc:
        if str(exc)=='MISSION_CANCELLED':status='MISSION_CANCELLED'
        else:raise
    finally:
        # A log/output error must not skip stop. Failed stop cannot be reported as success.
        primary=sys.exc_info()[1];cleanup_failure=None
        try:link.halt()
        except Exception as failure:
            if primary is not None:retain_cleanup(primary,'mission_halt',failure)
            else:cleanup_failure=failure
        try:
            if mission is not None and hasattr(mission,'close'):mission.close()
        except Exception as failure:
            if primary is not None or cleanup_failure is not None:
                retain_cleanup(primary if primary is not None else cleanup_failure,'mission_close',failure)
            else:cleanup_failure=failure
        try:
            if cleanup_failure is not None:status='FAILED'
            if mission is not None and hasattr(mission,'diagnostics'):
                for view in mission.views:record('cold_start_view',**view)
                record('cold_start_diagnostics',**mission.diagnostics())
            record('mission_finished',mission_id=request['mission_id'],status=status)
        except Exception as failure:
            if primary is not None or cleanup_failure is not None:
                retain_cleanup(primary if primary is not None else cleanup_failure,'mission_final_record',failure)
            else:cleanup_failure=failure
        if cleanup_failure is not None:raise cleanup_failure
    return {'status':status,'mission_id':request['mission_id'],'mission_ticks':tick}
