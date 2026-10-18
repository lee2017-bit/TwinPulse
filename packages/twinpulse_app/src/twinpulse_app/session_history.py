# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only, bounded review of PC journals. Never a robot authorization source."""
import hashlib
import json
import math
from pathlib import Path
import re

from .command_broker import BrokerError
from .physical_controller import valid_event, INPUTS, MODES
from .project_store import checked_project_id
from twinpulse_core.mission_contract import scope_document, document_hash
from twinpulse_core.demo_contract import operation_for_action


def reject():
    raise BrokerError('session_archive_invalid','Saved session is missing, changed, oversized or invalid',status=409)


def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate')
        result[k]=v
    return result


def decode(raw):
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:reject())


def read_bytes(path, limit):
    if path.is_symlink() or path.resolve()!=path.absolute():reject()
    with path.open('rb') as stream:
        before=path.stat()
        raw=stream.read(limit+1)
        after=path.stat()
    if len(raw)>limit or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):reject()
    return raw


def directory(root):
    root=Path(root).resolve()
    base=root/'artifacts/manual-control'
    if base.resolve()!=base or not base.resolve().is_relative_to(root):reject()
    return base


def index_directory(root, project_id):
    try:checked_project_id(project_id)
    except ValueError:reject()
    root=Path(root).resolve()
    base=root/'artifacts/project-session-index'/project_id
    if not base.resolve().is_relative_to(root) or base.resolve()!=base:reject()
    return base


def index_project_session(root, project_id, job):
    """Create an immutable project reference after closing a validated journal."""
    view=review_session(root,job)
    if view['project_id']!=project_id:reject()
    base=index_directory(root,project_id)
    base.mkdir(parents=True,exist_ok=True)
    entry=base/f'{job}.json'
    if entry.exists() or entry.is_symlink():reject()
    result_path=directory(root)/job/'result.json'
    result_hash=hashlib.sha256(read_bytes(result_path,512*1024)).hexdigest() if result_path.exists() else None
    value={'schema':'project-session-index-1.0','project_id':project_id,
           'job_id':job,'journal_sha256':view['sha256'],'result_sha256':result_hash}
    with entry.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,sort_keys=True,separators=(',',':'))
        stream.write('\n')
    return value


def read_index(root, project_id, job):
    if not isinstance(job,str) or not re.fullmatch('[a-f0-9]{32}',job):reject()
    base=index_directory(root,project_id)
    try:value=decode(read_bytes(base/f'{job}.json',4096))
    except (OSError,ValueError,TypeError):reject()
    if (not isinstance(value,dict) or set(value)!={'schema','project_id','job_id','journal_sha256','result_sha256'}
            or value['schema']!='project-session-index-1.0' or value['project_id']!=project_id
            or value['job_id']!=job or not isinstance(value['journal_sha256'],str)
            or re.fullmatch('[a-f0-9]{64}',value['journal_sha256']) is None
            or value['result_sha256'] is not None and (not isinstance(value['result_sha256'],str)
                or re.fullmatch('[a-f0-9]{64}',value['result_sha256']) is None)):reject()
    return value


def list_sessions(root):
    base=directory(root)
    if not base.exists():return {'sessions':[],'historical':True,'motion_authorized':False}
    entries=[]
    for index,path in enumerate(base.iterdir()):
        if index>=1024:reject()
        if re.fullmatch('[a-f0-9]{32}',path.name) and path.is_dir() and path.resolve()==path:
            log=path/'session.jsonl'
            if log.is_file() and not log.is_symlink() and log.resolve()==log:
                entries.append({'job_id':path.name,'modified_s':log.stat().st_mtime})
    return {'sessions':sorted(entries,key=lambda x:(x['modified_s'],x['job_id']),reverse=True)[:20],
            'historical':True,'motion_authorized':False}


def list_project_sessions(root, project_id):
    """Index only explicitly attributed logs; legacy journals stay unassigned."""
    try:checked_project_id(project_id)
    except ValueError:reject()
    base=index_directory(root,project_id)
    if not base.exists():return {'project_id':project_id,'sessions':[],'historical':True,'motion_authorized':False}
    entries=[]
    for index,path in enumerate(base.iterdir()):
        if index>=1024:reject()
        if not re.fullmatch(r'[a-f0-9]{32}\.json',path.name):continue
        job=path.stem
        try:
            read_index(root,project_id,job)
            entries.append({'job_id':job,'modified_s':path.stat().st_mtime})
        except (OSError,ValueError,TypeError,BrokerError):continue
    return {'project_id':project_id,'sessions':sorted(entries,key=lambda x:(x['modified_s'],x['job_id']),reverse=True)[:20],
            'historical':True,'motion_authorized':False}


def review_project_session(root, project_id, job):
    try:checked_project_id(project_id)
    except ValueError:reject()
    reference=read_index(root,project_id,job)
    view=review_session(root,job)
    if view['project_id']!=project_id or view['sha256']!=reference['journal_sha256']:reject()
    result_path=directory(root)/job/'result.json'
    result_hash=hashlib.sha256(read_bytes(result_path,512*1024)).hexdigest() if result_path.exists() else None
    if result_hash!=reference['result_sha256']:reject()
    return view


def valid_pc(row,job,*,adaptive=False,scope=None):
    if not isinstance(row,dict) or set(row)!={'schema','job_id','event_index','clock_domain','t','kind','real_transport','data'}:return False
    finite=lambda v:type(v) in (float,int) and math.isfinite(v) and v>=0
    if (row['schema'] not in {'control-session-1.0','control-session-1.1'} or row['job_id']!=job or row['clock_domain']!='pc_monotonic'
            or not finite(row['t']) or type(row['event_index']) is not int or type(row['real_transport']) is not bool):return False
    data=row['data'];kind=row['kind']
    if not isinstance(data,dict):return False
    if kind=='robot_event':return set(data)=={'event'} and valid_event(data['event'],adaptive=adaptive)
    if kind=='adaptive_visual':return (adaptive and set(data) in ({'revision'},{'revision','validation_s'})
        and isinstance(data['revision'],str) and re.fullmatch('[a-f0-9]{64}',data['revision']) is not None
        and ('validation_s' not in data or finite(data['validation_s']) and data['validation_s']<=1e6))
    if kind=='adaptive_telemetry':
        if not adaptive or not scope or set(data)!={'telemetry'}:return False
        try:
            from twinpulse_core.mission_telemetry import checked_telemetry
            checked_telemetry(data['telemetry'],job,scope)
            return True
        except (ValueError,TypeError,KeyError):return False
    # Additive diagnostics retain exact fields and never establish freshness,
    # current pose, authorization or a successful control receipt.
    if kind=='goal_watch_cycle':
        base={'guard_s','controller_lock_wait_s','sender_s'}
        return (adaptive and scope and scope.get('phase') in {'IDLE_LOCALIZATION_ONLY','REVIEWED_GOAL_EXECUTION'}
            and set(data) in (base,base|{'receipt_check_s','source_guard_s'})
            and all(finite(value) and value<=1e6 for value in data.values()))
    if kind=='goal_handoff_admission_failed':
        signed=lambda value:type(value) in (int,float) and math.isfinite(value) and abs(value)<=1e6
        return (adaptive and scope and scope.get('phase')=='IDLE_LOCALIZATION_ONLY'
            and set(data)=={'phase','error_type','reason','elapsed_s','evidence_age_upper_s'}
            and data['phase'] in ('FRESH_QUERY','RECHECK_REVIEWED_ROUTE','RELEASE_ADMISSION','SEND_HANDOFF')
            and isinstance(data['error_type'],str) and re.fullmatch('[A-Za-z0-9_]{1,80}',data['error_type']) is not None
            and isinstance(data['reason'],str) and re.fullmatch('[A-Z0-9_]{1,160}',data['reason']) is not None
            and finite(data['elapsed_s']) and data['elapsed_s']<=1e6
            and (data['evidence_age_upper_s'] is None or signed(data['evidence_age_upper_s'])))
    if kind in {'localization_validation_rejected','localization_return_rejected',
                'localization_late_after_stop','localization_partial_after_stop'}:
        if not adaptive or not scope or scope.get('phase')!='IDLE_LOCALIZATION_ONLY':return False
        from twinpulse_core.reference_transport import checked_descriptor,hex_id
        if not hex_id(data.get('query_id'),32):return False
        if kind=='localization_partial_after_stop':
            return set(data)=={'query_id','state'} and data['state'] in ('LOCALIZATION_BEGIN','LOCALIZATION_CHUNK')
        if kind=='localization_late_after_stop':
            try:return set(data)=={'query_id','payload'} and checked_descriptor(data['payload'])==data['payload']
            except (ValueError,KeyError,TypeError):return False
        if not isinstance(data.get('reason'),str) or re.fullmatch('[A-Z0-9_]{1,160}',data['reason']) is None:return False
        base={'query_id','reason','round_trip_upper_s'}
        transport=base|{'robot_processing_s','decode_elapsed_s','transport_time_valid','context_valid','reference_valid','authority_absent'}
        binding=base|{'evidence_age_upper_s','decode_elapsed_s','binding_elapsed_s'}
        returned=base|{'evidence_age_upper_s','elapsed_since_receipt_s'}
        allowed=(returned,) if kind=='localization_return_rejected' else (transport,binding,binding|{'commit_wait_s'})
        if set(data) not in allowed:return False
        booleans={'transport_time_valid','context_valid','reference_valid','authority_absent'}
        signed={'round_trip_upper_s','robot_processing_s','evidence_age_upper_s','elapsed_since_receipt_s'}
        for key,value in data.items():
            if key in {'query_id','reason'}:continue
            if key in booleans:
                if type(value) is not bool:return False
            elif key in signed:
                if value is None and kind=='localization_return_rejected' and key in {'round_trip_upper_s','elapsed_since_receipt_s'}:continue
                if type(value) not in (float,int) or not math.isfinite(value) or abs(value)>1e6:return False
            elif not finite(value) or value>1e6:return False
        return True
    if kind=='pc_session_started':
        context=data.get('app_context')
        return (set(data) in ({'mode'},{'mode','project_id'},
                              {'mode','project_id','app_context'}) and data['mode'] in MODES|{'mission'}
                and ('project_id' not in data or isinstance(data['project_id'],str)
                     and re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',data['project_id']) is not None)
                and ('app_context' not in data or isinstance(context,dict)
                     and set(context)=={'app_scene_revision','app_robot_profile_id','capture_status'}
                     and isinstance(context['capture_status'],str)
                     and context['capture_status'] in {'CAPTURED','UNAVAILABLE'}
                     and (context['app_scene_revision'] is None or isinstance(context['app_scene_revision'],str)
                          and re.fullmatch('[a-f0-9]{64}',context['app_scene_revision']) is not None)
                     and (context['app_robot_profile_id'] is None or isinstance(context['app_robot_profile_id'],str)
                          and re.fullmatch('[A-Za-z0-9_.-]{1,128}',context['app_robot_profile_id']) is not None)
                     and (context['capture_status']!='UNAVAILABLE' or
                          context['app_scene_revision'] is None and context['app_robot_profile_id'] is None)))
    if kind=='mission_scope':
        try:
            from twinpulse_core.adaptive_mission_contract import adaptive_scope
            validator=adaptive_scope if adaptive else scope_document
            return (set(data)=={'scope','scope_sha256'} and validator(data['scope'])==data['scope']
                    and document_hash(data['scope'])==data['scope_sha256'])
        except (TypeError,ValueError):return False
    if kind=='mission_request_sent':return (set(data)=={'request_sha256'} and isinstance(data['request_sha256'],str)
        and re.fullmatch('[a-f0-9]{64}',data['request_sha256']) is not None)
    if kind in {'goal_handoff_requested','goal_handoff_accepted'}:
        from twinpulse_core.reference_transport import checked_descriptor,hex_id
        try:return (adaptive and set(data)=={'plan_id','payload'} and hex_id(data['plan_id'],64)
            and checked_descriptor(data['payload'])==data['payload'])
        except (ValueError,TypeError,KeyError):return False
    if kind in {'goal_handoff_begin_sent','goal_handoff_chunk_sent'}:
        from twinpulse_core.reference_transport import checked_descriptor
        try:return (adaptive and set(data)==({'payload'} if kind=='goal_handoff_begin_sent' else {'payload','index'})
            and checked_descriptor(data['payload'])==data['payload']
            and (kind=='goal_handoff_begin_sent' or type(data['index']) is int and 0<=data['index']<700))
        except (ValueError,TypeError,KeyError):return False
    if kind=='localization_request_failed':
        return (adaptive and scope and scope.get('phase')=='IDLE_LOCALIZATION_ONLY'
            and set(data)=={'reason'} and isinstance(data['reason'],str)
            and re.fullmatch('[A-Z0-9_]{1,120}',data['reason']) is not None)
    if kind in {'reference_chunk_sent','localization_query_sent','localization_ack_sent',
                'localization_observation_received','localization_observation'}:
        if not adaptive or not scope or scope.get('phase')!='IDLE_LOCALIZATION_ONLY':return False
        from twinpulse_core.reference_transport import checked_descriptor,hex_id
        try:
            if kind=='reference_chunk_sent':
                return (set(data)=={'index','payload'} and type(data['index']) is int and 0<=data['index']<700
                    and checked_descriptor(data['payload'])==scope['reference']['payload'])
            if not hex_id(data.get('query_id'),32):return False
            if kind in {'localization_query_sent','localization_ack_sent'}:
                keys={'query_id','pipe_write_s'}|({'index'} if kind=='localization_ack_sent' else set())
                return (set(data)==keys and finite(data['pipe_write_s'])
                    and (kind!='localization_ack_sent' or type(data['index']) is int and 0<=data['index']<700))
            checked_descriptor(data['payload'])
            if kind=='localization_observation_received':return set(data)=={'query_id','payload'}
            return (set(data)=={'query_id','payload','issued_s','received_s','sample_s','round_trip_upper_s','current_pose_valid_at_receipt'}
                and data['current_pose_valid_at_receipt'] is True
                and all(finite(data[k]) for k in ('issued_s','received_s','sample_s','round_trip_upper_s'))
                and 0<=data['issued_s']-data['received_s']<=data['round_trip_upper_s']<.2
                and 0<=data['received_s']-data['sample_s']+data['round_trip_upper_s']<.2)
        except (ValueError,KeyError,TypeError):return False
    if kind in {'correction_proposal_received','correction_reply_sent','correction_robot_receipt'}:
        if not adaptive or not scope or scope.get('schema') not in {'observed-mission-scope-3.0','observed-mission-scope-5.0'}:return False
        from twinpulse_core.mission_correction_contract import checked_fit,correction_reply
        try:
            if kind=='correction_proposal_received':
                return (set(data)=={'proposal_revision','fit'} and isinstance(data['proposal_revision'],str)
                    and re.fullmatch('[a-f0-9]{64}',data['proposal_revision']) is not None
                    and checked_fit(data['fit'],scope['nominal'])==data['fit'])
            keys={'reply_revision','proposal_revision','reason'}|({'binding'} if kind=='correction_robot_receipt' else set())
            if set(data)!=keys or any(not isinstance(data[k],str) or not re.fullmatch('[a-f0-9]{64}',data[k]) for k in ('reply_revision','proposal_revision')):return False
            if kind=='correction_robot_receipt':
                correction_reply({'mission_id':job,'scope_sha256':document_hash(scope),
                    'revision':data['proposal_revision'],'nonce':'0'*24},scope,data['binding'],reason=data['reason'])
            elif data['reason'] is not None and (not isinstance(data['reason'],str) or not re.fullmatch('[A-Z0-9_]{1,120}',data['reason'])):return False
            return True
        except (ValueError,TypeError,KeyError):return False
    if kind in ('input_received','pipe_written','pipe_enqueue_requested'):
        fields={'sequence','action'} if kind=='input_received' else {'sequence','action','source_age_ms'}
        operation_id=operation_for_action(data.get('action'))
        timing={'pipe_write_s'} if kind=='pipe_written' else set()
        return (set(data) in (fields, fields|{'operation_id'},fields|timing,fields|timing|{'operation_id'})
                and type(data['sequence']) is int and 1<=data['sequence']<2147483647
                and isinstance(data['action'],str) and data['action'] in INPUTS
                and ('operation_id' not in data or operation_id is not None and data['operation_id']==operation_id)
                and (kind=='input_received' or finite(data['source_age_ms']))
                and ('pipe_write_s' not in data or finite(data['pipe_write_s']) and 0<=data['pipe_write_s']<=1e6))
    if kind=='robot_finished':
        return (set(data)=={'status','reason','robot_session_id','cleanup_confirmed'}
                and type(data['cleanup_confirmed']) is bool
                and all(v is None or isinstance(v,str) and re.fullmatch('[A-Za-z0-9_.-]{1,80}',v)
                        for k,v in data.items() if k!='cleanup_confirmed'))
    return False


def transport_diagnostics(rows):
    """Same-clock intervals and sequence joins, never inferred Wi-Fi latency."""
    received={};written={};accepted={};published={};write_times=[]
    terminal=None
    for row in rows:
        kind,data=row['kind'],row['data']
        if kind=='input_received':
            received[data['sequence']]=row['t']
            if data['action'] in {'close','finish_stop','force_stop'}:
                terminal={'sequence':data['sequence'],'action':data['action']}
        elif kind=='pipe_written':
            written[data['sequence']]=row['t']
            if 'pipe_write_s' in data:write_times.append(data['pipe_write_s'])
        elif kind=='robot_event':
            event=data['event'];payload=event['data']
            if event['kind']=='accepted':accepted[payload['sequence']]=event['t']
            elif event['kind']=='published':published.setdefault(payload['sequence'],event['t'])
    pc_delays=[written[s]-received[s] for s in written.keys()&received.keys() if written[s]>=received[s]]
    robot_delays=[published[s]-accepted[s] for s in published.keys()&accepted.keys() if published[s]>=accepted[s]]
    if terminal is not None:
        s=terminal['sequence'];terminal.update(pipe_written=s in written,robot_accepted=s in accepted,
                                               robot_publication_observed=s in published)
    return {'schema':'control-transport-diagnostic-1.0','interval_basis':'EACH_HOST_MONOTONIC_SEPARATELY',
        'pc_accept_to_pipe_max_s':max(pc_delays,default=None),
        'robot_accept_to_publish_max_s':max(robot_delays,default=None),
        'pc_pipe_write_max_s':max(write_times,default=None),
        'pipe_without_robot_accept_count':len(written.keys()-accepted.keys()),
        'accepted_without_pipe_count':len(accepted.keys()-written.keys()),
        'last_terminal_intent':terminal,'wifi_delay_s':None,'cause':'UNKNOWN_CAUSE',
        'physical_stop_verified':False,'motion_authorized':False}


def review_session(root,job):
    if not isinstance(job,str) or not re.fullmatch('[a-f0-9]{32}',job):reject()
    try:
        base=directory(root)/job
        if base.resolve()!=base:reject()
        raw=read_bytes(base/'session.jsonl',64*1024*1024)
        pieces=raw.split(b'\n');partial_tail=bool(pieces[-1]);pieces=pieces[:-1]
        if not 1<=len(pieces)<=262144 or any(len(line)>65536 for line in pieces):reject()
        rows=[decode(line) for line in pieces]
        persistent=rows[0].get('schema')=='control-session-1.1'
        if not persistent and (len(raw)>8*1024*1024 or len(rows)>8192):reject()
        last_t=-1.;transport=None;robot=[];robot_id=None;robot_t=-1.;sample_t=-1.
        mission_id=None;mission_tick=0;mission_finished=False;started_count=0
        adaptive=False;scope=None;correction_proposal=None;correction_reply=None;correction_receipt=None
        for n,row in enumerate(rows,1):
            if row.get('kind')=='mission_scope' and isinstance(row.get('data'),dict) and isinstance(row['data'].get('scope'),dict):
                scope=row['data']['scope']
                adaptive=scope.get('schema') in {'observed-mission-scope-'+str(i)+'.0' for i in range(1,8)}
            if row.get('schema')!=rows[0].get('schema'):reject()
            if not valid_pc(row,job,adaptive=adaptive,scope=scope) or row['event_index']!=n or row['t']<last_t:reject()
            data=row['data']
            if row['kind']=='correction_proposal_received':
                if correction_proposal is not None:reject()
                correction_proposal=data['proposal_revision']
            elif row['kind']=='correction_reply_sent':
                if correction_proposal!=data['proposal_revision'] or correction_reply is not None:reject()
                if correction_receipt and any(data[k]!=correction_receipt[k] for k in ('reply_revision','proposal_revision','reason')):reject()
                correction_reply=data
            elif row['kind']=='correction_robot_receipt':
                # stdout receipt and the PC writer's post-flush log run on
                # separate threads. Correlate hashes, never infer wire ordering
                # from which thread acquired the journal lock first.
                if (correction_proposal!=data['proposal_revision'] or correction_receipt is not None
                        or correction_reply and any(data[k]!=correction_reply[k] for k in ('reply_revision','proposal_revision','reason'))):reject()
                correction_receipt=data
            if transport is not None and row['real_transport']!=transport:reject()
            last_t,transport=row['t'],row['real_transport']
            if row['kind']=='pc_session_started':
                started_count+=1
                if started_count>1:reject()
            if row['kind']=='robot_event':
                event=row['data']['event']
                if (event['event_index']!=len(robot)+1 or event['t']<robot_t
                        or robot_id is not None and event['robot_session_id']!=robot_id):reject()
                if event['kind']=='observation':
                    sample=event['data']['sample']
                    if sample['t']<max(0,sample_t) or sample['t']>event['t'] or sample['source_age_s']<0:reject()
                    sample_t=sample['t']
                if 'action' in event['data'] and event['data']['action'] not in INPUTS:reject()
                if event['kind']=='mission_started':
                    if mission_id is not None:reject()
                    mission_id=event['data']['mission_id']
                elif event['kind'] in {'mission_decision','mission_finished'}:
                    if mission_finished or (mission_id is not None and event['data']['mission_id']!=mission_id):reject()
                    if event['kind']=='mission_decision':
                        if mission_id is None or event['data']['tick']!=mission_tick+1:reject()
                        mission_tick=event['data']['tick']
                    else:mission_finished=True  # A pre-start cancellation/failure may have no started row.
                robot.append(event);robot_t,robot_id=event['t'],event['robot_session_id']
        complete=False
        try:
            result=decode(read_bytes(base/'result.json',512*1024))
            complete=(not partial_tail and (correction_receipt is None or correction_reply is not None)
                      and isinstance(result,dict) and result.get('session_log_complete') is True
                      and type(result.get('session_event_count')) is int and result['session_event_count']==len(rows)
                      and result.get('real_transport') is transport
                      and (any(r['kind']=='robot_finished' for r in rows)
                           or rows[0]['kind']=='pc_session_started' and rows[0]['data']['mode']=='prepare'))
        except (OSError,ValueError,BrokerError):pass  # Missing/bad final marker never invalidates a valid prefix.
        commands=[]
        sequence_operations={}
        for row in rows:
            if row['kind'] not in {'input_received','pipe_written'}:
                continue
            data=row['data']
            if 'operation_id' not in data:
                continue  # Legacy journal: do not invent a recorded operation ID.
            sequence=data['sequence']
            identity=(data['operation_id'],data['action'])
            previous=sequence_operations.setdefault(sequence,identity)
            if previous!=identity:reject()
        # All projected rows remain in PC journal order. Robot time is separate,
        # never subtracted from PC time or used as a floor-position estimate.
        timeline=[]
        seen_operations={}
        robot_operation_ids={}
        for row in rows:
            event=row['data'].get('event') if row['kind']=='robot_event' else None
            item={'event_index':row['event_index'],'pc_t':row['t'],
                  'robot_t':event['t'] if event else None,
                  'clock_domain':'pc_monotonic','kind':event['kind'] if event else row['kind'],
                  'sequence':None,'action':None,'operation_id':None,
                  'operation_id_basis':'NOT_RECORDED','linear_m_s':None,'angular_rad_s':None,
                  'encoders':None,'observation_sample_t':None,'odom_xy_m':None,'observation_gap':False}
            data=event['data'] if event else row['data']
            item['sequence']=data.get('sequence')
            item['action']=data.get('action')
            if not event and 'operation_id' in data:
                item['operation_id']=data['operation_id']
                item['operation_id_basis']='RECORDED_PC'
                seen_operations[data['sequence']]=(data['operation_id'],data['action'])
            elif event and event['kind'] in {'accepted','published'} and data.get('sequence') in seen_operations:
                identity=seen_operations[data['sequence']]
                if data.get('action')==identity[1]:
                    item['operation_id']=identity[0]
                    item['operation_id_basis']='SEQUENCE_AND_ACTION_CORRELATED_PC'
                    robot_operation_ids[event['event_index']]=identity[0]
            if event and event['kind']=='published':
                item['linear_m_s']=data['linear_m_s'];item['angular_rad_s']=data['angular_rad_s']
            if event and event['kind']=='observation':
                item['encoders']=data['sample']['encoders']
                item['observation_sample_t']=data['sample']['t']
            if event and event['kind']=='navigation' and data['snapshot']['odom'] is not None:
                item['odom_xy_m']=data['snapshot']['odom']['position_m'][:2]
            timeline.append(item)
        next_observation_t=None;next_sample_t=None
        for item in reversed(timeline):
            if item['kind']=='observation':
                next_observation_t=item['robot_t'];next_sample_t=item['observation_sample_t']
            elif item['kind']=='published':
                item['observation_gap']=(next_observation_t is None or item['robot_t'] is None
                                         or next_observation_t-item['robot_t']>.5 or next_sample_t is None
                                         or next_sample_t<item['robot_t'])
        navigation=[e['data']['snapshot'] for e in robot if e['kind']=='navigation']
        missions=[e for e in robot if e['kind'] in {'mission_started','mission_decision','mission_finished'}]
        endings=[r['data'] for r in rows if r['kind']=='robot_finished']
        published=[(i,e) for i,e in enumerate(robot) if e['kind']=='published']
        for index,event in published[-200:]:
            after=None
            for candidate in robot[index+1:]:
                if candidate['t']-event['t']>.5:break
                if candidate['kind']=='observation' and candidate['data']['sample']['t']>=event['t']:
                    after=candidate['data']['sample'];break
            operation_id=robot_operation_ids.get(event['event_index'])
            commands.append({'robot_t':event['t'],**event['data'],'next_observation':after,
                             'operation_id':operation_id,
                             'operation_id_basis':'SEQUENCE_AND_ACTION_CORRELATED_PC' if operation_id else 'NOT_RECORDED'})
        bound=next((r['data'].get('project_id') for r in rows if r['kind']=='pc_session_started'),None)
        start=next((r['data'] for r in rows if r['kind']=='pc_session_started'),None)
        robot_starts=[e['data'] for e in robot if e['kind']=='session_started']
        # Conflicting/repeated starts cannot establish one comparable boot/release.
        robot_start=robot_starts[0] if len(robot_starts)==1 else None
        app_context=start.get('app_context') if start else None
        mission_scopes=[r['data']['scope_sha256'] for r in rows if r['kind']=='mission_scope']
        mission_scope=mission_scopes[0] if len(mission_scopes)==1 else None
        localization=[]
        for row in rows:
            if row['kind']!='localization_observation_received':continue
            item=row['data'];member=base/('localization-'+item['query_id']+'.json')
            if member.exists():
                from twinpulse_core.reference_transport import descriptor,MAX_REFERENCE
                packet=read_bytes(member,MAX_REFERENCE)
                if descriptor(packet)!=item['payload']:reject()
                storage='HASH_VERIFIED_HISTORICAL'
            else:storage='NOT_SAVED'
            localization.append({**item,'packet_storage':storage,'historical':True,
                'current_pose_valid':False,'motion_authorized':False})
        handoffs=[r['data'] for r in rows if r['kind']=='goal_handoff_requested']
        accepted=[r['data'] for r in rows if r['kind']=='goal_handoff_accepted']
        if len(handoffs)>1 or len(accepted)>1 or accepted and accepted!=handoffs:reject()
        if handoffs:
            from twinpulse_core.reference_transport import descriptor,MAX_REFERENCE,decode as decode_payload,goal_handoff,ReferenceSender
            saved=read_bytes(base/'goal-handoff.json',MAX_REFERENCE)
            if descriptor(saved)!=handoffs[0]['payload']:reject()
            scopes=[r for r in rows if r['kind']=='mission_scope']
            requested=next(r for r in rows if r['kind']=='goal_handoff_requested')
            document=decode_payload(saved,MAX_REFERENCE)
            if (not scopes or scopes[0]['event_index']>=requested['event_index']
                    or document!=goal_handoff(scopes[0]['data']['scope'],job,document.get('preview'))
                    or document['preview']['plan_id']!=handoffs[0]['plan_id']):reject()
            sent=[r for r in rows if r['kind'] in {'goal_handoff_begin_sent','goal_handoff_chunk_sent'}]
            if (any(r['event_index']<=requested['event_index'] or r['data']['payload']!=handoffs[0]['payload'] for r in sent)
                    or len([r for r in sent if r['kind']=='goal_handoff_begin_sent'])>1
                    or [r['data']['index'] for r in sent if r['kind']=='goal_handoff_chunk_sent']
                    !=list(range(sum(r['kind']=='goal_handoff_chunk_sent' for r in sent)))):reject()
            if accepted:
                receipt=next(r for r in rows if r['kind']=='goal_handoff_accepted')
                sender=ReferenceSender(document)
                count=(sender.descriptor['bytes']+sender.chunk_size-1)//sender.chunk_size
                if (len(sent)!=count+1 or sent[0]['kind']!='goal_handoff_begin_sent'
                        or receipt['event_index']<=sent[-1]['event_index']
                        or len(scopes)!=2 or scopes[1]['event_index']<=receipt['event_index']
                        or scopes[1]['data']['scope']!=document['scope']):reject()
        return {'schema':'control-session-review-1.0','job_id':job,'historical':True,
                'project_id':bound,'attribution':'BOUND' if bound else 'UNATTRIBUTED',
                'mode':start['mode'] if start else None,
                'robot_boot_id':robot_start['boot_id'] if robot_start else None,
                'robot_release_id':robot_start['release_id'] if robot_start else None,
                'comparison_evidence':{
                    'app_context_capture':app_context['capture_status'] if app_context else 'LEGACY_UNKNOWN',
                    'app_scene_revision':app_context['app_scene_revision'] if app_context else None,
                    'app_robot_profile_id':app_context['app_robot_profile_id'] if app_context else None,
                    'mission_scope_sha256':mission_scope,
                    'robot_boot_id':robot_start['boot_id'] if robot_start else None,
                    'robot_release_id':robot_start['release_id'] if robot_start else None,
                    'room_odom_alignment':'UNVERIFIED',
                },
                'transport_diagnostics':transport_diagnostics(rows),
                'timeline':timeline[-1000:] if persistent else timeline,
                'timeline_events_omitted':max(0,len(timeline)-1000) if persistent else 0,
                'timeline_basis':'PC_ORDER_ONLY_ROBOT_CLOCK_SEPARATE',
                'record_status':'COMPLETE_RECORD' if complete else 'INCOMPLETE_RECORD',
                'partial_tail_excluded':partial_tail,'sha256':hashlib.sha256(raw).hexdigest(),
                'provenance':'RECORDED_REAL_TRANSPORT' if transport else 'SYNTHETIC_TRANSPORT',
                'physical_success':None,'motion_authorized':False,'floor_pose_measured':False,
                'clock_domains':['pc_monotonic','robot_monotonic'],'robot_session_id':robot_id,
                'recorded_end':endings[-1] if endings else None,
                'event_count':len(rows),'pc_received':sum(r['kind']=='input_received' for r in rows),
                'pipe_written':sum(r['kind']=='pipe_written' for r in rows),
                'robot_accepted':sum(r['kind']=='accepted' for r in robot),
                'observation_count':sum(r['kind']=='observation' for r in robot),
                'published_count':len(published),'commands':commands,
                'navigation_observations':navigation[-60:],
                'navigation_observations_omitted':max(0,len(navigation)-60),
                'mission_events':missions[-200:],'mission_events_omitted':max(0,len(missions)-200),
                'mission_scopes':[r['data'] for r in rows if r['kind']=='mission_scope'],
                'mission_requests':[r['data'] for r in rows if r['kind']=='mission_request_sent'],
                'localization_observations':localization,
                'goal_handoff':{'requested':bool(handoffs),'accepted':bool(accepted),
                    'review':handoffs[0] if handoffs else None,'historical_only':True,'physical_authority':False},
                'correction_exchange':[{'kind':r['kind'],**r['data']} for r in rows if r['kind'] in
                    {'correction_proposal_received','correction_reply_sent','correction_robot_receipt'}],
                'commands_omitted':max(0,len(published)-200)}
    except (OSError,ValueError,TypeError,KeyError,RecursionError):reject()
