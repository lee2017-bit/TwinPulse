# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Historical, hash-bound sensor review of the CURRENT effective Twin.

This adapter produces only checked dependency previews. It never adopts the
legacy automatic-photo ledger, changes pose authority, or dispatches a command.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import uuid4

from twinpulse_core import canonical_sha256
from twinpulse_core.automatic_photo_alignment import align_photo_map
from .command_broker import BrokerError
from .project_store import AutomaticMapStore
from .robot_geometry_evidence import load_geometry_evidence
from .saved_mapping_evidence import saved_observation_source
from .session_history import read_index, review_project_session, read_bytes


CONTEXT_FIELDS = {'schema_version','project_id','input_revision','source_sha256',
    'current_scene_revision','current_state_sha256','physical_authority'}
EVIDENCE_FIELDS = {'map_id','map_revision','source_job_id','raw_sha256','footer_sha256',
    'report_sha256','export_sha256','index_sha256','journal_sha256','result_sha256',
    'boot_id','release_id','robot_session_id','nominal_geometry_sha256','offset_sha256','provenance'}
BINDING_FIELDS = {'schema_version','policy','context','evidence','alignment_sha256',
    'preview_sha256','execution_id','physical_authority'}


def checked_context(value):
    if (not isinstance(value,dict) or set(value)!=CONTEXT_FIELDS or
            value['schema_version']!='scene-sensor-context-1.0' or value['physical_authority'] is not False):
        raise ValueError('SCENE_SENSOR_CONTEXT_INVALID')
    for key in ('input_revision','source_sha256','current_scene_revision','current_state_sha256'):
        if not isinstance(value[key],str) or not re.fullmatch('[a-f0-9]{64}',value[key]):
            raise ValueError('SCENE_SENSOR_CONTEXT_INVALID')
    if not isinstance(value['project_id'],str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',value['project_id']):
        raise ValueError('SCENE_SENSOR_CONTEXT_INVALID')
    return deepcopy(value)


def checked_sensor_binding(value):
    if value is None:return None
    if (not isinstance(value,dict) or set(value)!=BINDING_FIELDS or
            value['schema_version']!='scene-sensor-binding-1.0' or value['policy']!='correct_walls' or
            value['physical_authority'] is not False):raise ValueError('SCENE_SENSOR_BINDING_INVALID')
    checked_context(value['context'])
    evidence=value['evidence']
    if not isinstance(evidence,dict) or set(evidence)!=EVIDENCE_FIELDS:raise ValueError('SCENE_SENSOR_BINDING_INVALID')
    for key,item in evidence.items():
        if key=='provenance':
            if item not in {'SYNTHETIC_TRANSPORT','RECORDED_REAL_TRANSPORT'}:raise ValueError('SCENE_SENSOR_BINDING_INVALID')
        else:
            pattern=('[a-f0-9]{32}' if key in {'map_id','source_job_id'} else
                '[a-f0-9]{64}' if key.endswith(('sha256','revision')) else '[A-Za-z0-9_.:/-]{1,160}')
            if not isinstance(item,str) or not re.fullmatch(pattern,item):raise ValueError('SCENE_SENSOR_BINDING_INVALID')
    for key in ('alignment_sha256','preview_sha256','execution_id'):
        if not isinstance(value[key],str) or not re.fullmatch('[a-f0-9]{32}' if key=='execution_id' else '[a-f0-9]{64}',value[key]):
            raise ValueError('SCENE_SENSOR_BINDING_INVALID')
    return deepcopy(value)


class SceneSensorReview:
    def __init__(self,workflow,root):
        self.workflow=workflow;self.root=Path(root).resolve()
        self.maps=AutomaticMapStore(self.root,workflow._broker.project_id)
        from .scene_sensor_import import SceneSensorImport
        self.surveys=SceneSensorImport(self)

    def context(self,store=None,history=None):
        with self.workflow._lock:
            store=store or self.workflow._scene_edit_store()
            history=history or store.load()
            source=store.source
            if (self.workflow._phase!='draft_ready' or self.workflow._derived_revision is not None or
                    self.workflow._application.site_draft!=source or self.workflow._input is None or
                    self.workflow._input.revision!=source.input_revision.digest):
                raise BrokerError('scene_sensor_stale','The current original/input review changed.',status=409)
            project=store.project_store.load() if store.project_store else None
            if store.project_store and (project is None or project.site_draft!=source):
                raise BrokerError('scene_sensor_stale','The saved original changed.',status=409)
            state=history.effective(source)
            return checked_context(dict(schema_version='scene-sensor-context-1.0',project_id=store.project_id,
                input_revision=source.input_revision.digest,source_sha256=canonical_sha256(source.to_dict()),
                current_scene_revision=state.site.scene.revision,current_state_sha256=history.state_sha256(state),
                physical_authority=False))

    def select(self,body):
        context=self.context()
        if (body['expected_scene_revision']!=context['current_scene_revision'] or
                body['expected_state_sha256']!=context['current_state_sha256']):
            raise BrokerError('scene_sensor_stale','Current Twin state changed; select the saved map again.',status=409)
        saved=self.maps.load(body['map_id'])
        if saved['revision']!=body['expected_map_revision']:
            raise BrokerError('scene_sensor_stale','Saved map revision changed.',status=409)
        return dict(context=context,map_id=body['map_id'],map_revision=saved['revision'])

    def _inputs(self,map_id):
        saved=self.maps.load(map_id)
        self.surveys.validate_map(saved)
        job=saved.get('source_job_id')
        source=saved_observation_source(self.root,self.maps.project_id,job)
        pc=review_project_session(self.root,self.maps.project_id,job)
        index=read_index(self.root,self.maps.project_id,job)
        folder=self.root/'artifacts/manual-control'/job
        evidence=folder/'robot-evidence'
        # The standard source reader already checks every export file/raw byte.
        # These additional exact references bind the report and PC attribution.
        report_raw=read_bytes(evidence/'report.json',8*1024*1024)
        report=json.loads(report_raw)
        footer_raw=read_bytes(evidence/'ros-messages.raw.footer.json',8*1024*1024)
        export_raw=read_bytes(evidence/'export.json',8*1024*1024)
        result_raw=read_bytes(folder/'result.json',512*1024)
        if (pc['record_status']!='COMPLETE_RECORD' or pc['robot_boot_id']!=report.get('boot_id') or
                pc['robot_release_id']!=report.get('release_id') or pc['robot_session_id']!=report.get('robot_session_id') or
                source.window.context['source_revision']!=saved['source_revision'] or
                source.window.context['boot_id']!=saved['boot_id']):raise ValueError('SCENE_SENSOR_SOURCE_BINDING_MISMATCH')
        geometry=load_geometry_evidence()
        base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
        offset=[base[0]+mount[0],base[1]+mount[1],0.]
        if (saved.get('nominal_geometry_revision')!=geometry['revision'] or saved.get('offset')!=offset):
            raise ValueError('SCENE_SENSOR_NOMINAL_GEOMETRY_OR_OFFSET_CHANGED')
        sha=lambda raw:hashlib.sha256(raw).hexdigest()
        proof=dict(map_id=map_id,map_revision=saved['revision'],source_job_id=job,
            raw_sha256=saved['source_revision'],footer_sha256=sha(footer_raw),report_sha256=sha(report_raw),
            export_sha256=sha(export_raw),index_sha256=canonical_sha256(index),journal_sha256=pc['sha256'],
            result_sha256=sha(result_raw),boot_id=report['boot_id'],release_id=report['release_id'],
            robot_session_id=report['robot_session_id'],nominal_geometry_sha256=geometry['revision'],
            offset_sha256=canonical_sha256(offset),provenance=pc['provenance'])
        return saved,proof,base[2]+mount[2]

    @staticmethod
    def _patch(state,report):
        proposals=report.get('proposals')
        if (report.get('status')!='ALIGNMENT_CANDIDATE' or
                report.get('geometry_status')!='BOUNDED_WALL_PROPOSAL_VALIDATED' or
                not isinstance(proposals,list) or not 1<=len(proposals)<=2):
            raise ValueError('SCENE_SENSOR_VALIDATED_WALLS_REQUIRED')
        calls={call.arguments['id']:call for call in state.plan.calls};edits=[];seen=set()
        for proposal in proposals:
            identity=proposal['id'];old=calls.get(identity);delta=proposal['translation_xy_m']
            if (identity in seen or old is None or old.tool!='create_wall' or len(delta)!=2 or
                    any(type(v) not in (float,int) or not math.isfinite(v) for v in delta) or
                    math.hypot(*delta)>.20+1e-9):raise ValueError('SCENE_SENSOR_WALL_BOUND_INVALID')
            seen.add(identity);call=deepcopy(old.to_dict())
            for i in range(2):call['arguments']['position_m'][i]+=delta[i]
            edits.append(dict(action='room',target_id=identity,reason='Historical disjoint-view bounded wall candidate; not measured or physical authority',tool_call=call))
        from .dependency_patch import PATCH_VERSION
        return dict(patch_version=PATCH_VERSION,edits=edits)

    @staticmethod
    def _verify_delta(before,after,patch):
        targets={e['target_id'] for e in patch['edits']}
        if not 1<=len(targets)<=2:raise ValueError('SCENE_SENSOR_WALL_BOUND_INVALID')
        a={c.arguments['id']:c.to_dict() for c in before.plan.calls};b={c.arguments['id']:c.to_dict() for c in after.plan.calls}
        if a.keys()!=b.keys() or before.placement!=after.placement:
            raise ValueError('SCENE_SENSOR_NONWALL_STATE_CHANGED')
        for identity,old in a.items():
            if identity not in targets:
                if b[identity]!=old:raise ValueError('SCENE_SENSOR_NONWALL_STATE_CHANGED')
                continue
            new=deepcopy(b[identity]);old=deepcopy(old)
            if old['tool']!='create_wall':raise ValueError('SCENE_SENSOR_NONWALL_STATE_CHANGED')
            old_position=old['arguments'].pop('position_m');new_position=new['arguments'].pop('position_m')
            if (old!=new or old_position[2]!=new_position[2] or
                    math.dist(old_position[:2],new_position[:2])>.20+1e-9):
                raise ValueError('SCENE_SENSOR_WALL_BOUND_INVALID')
        # Structural inventory updates are expected; every nonwall row/pending
        # record remains exact, including unresolved work and placement.
        if before.inventory.keys()!=after.inventory.keys():raise ValueError('SCENE_SENSOR_NONWALL_STATE_CHANGED')
        if any(before.inventory[k]!=after.inventory[k] for k in before.inventory if k not in targets):
            raise ValueError('SCENE_SENSOR_NONWALL_STATE_CHANGED')
        objects_a={o['id']:o for o in before.site.scene.to_dict()['objects']}
        objects_b={o['id']:o for o in after.site.scene.to_dict()['objects']}
        if objects_a.keys()!=objects_b.keys() or any(objects_a[k]!=objects_b[k] for k in objects_a if k not in targets):
            raise ValueError('SCENE_SENSOR_NONWALL_GEOMETRY_CHANGED')

    def review(self,selection,policy):
        if policy not in {'align_only','correct_walls'}:raise ValueError('SCENE_SENSOR_POLICY_INVALID')
        trace=self.workflow._edit_trace('scene_sensor_review','sensor_'+uuid4().hex)
        try:
            with self.workflow._lock:
                store=self.workflow._scene_edit_store();history=store.load()
                context=self.context(store,history)
                if context!=selection['context']:raise ValueError('SCENE_SENSOR_CURRENT_STATE_CHANGED')
                state=history.effective(store.source)
            saved,evidence,height=self._inputs(selection['map_id'])
            if saved['revision']!=selection['map_revision']:raise ValueError('SCENE_SENSOR_MAP_CHANGED')
            with trace.span('scene_sensor_alignment',map_revision=saved['revision'],scene_state_sha256=context['current_state_sha256']):
                report=align_photo_map(saved,state.site.scene.to_dict()['objects'],height_m=height,policy=policy,diagnostics=True)
            trace.bind(sensor_map_id=selection['map_id'],sensor_raw_sha256=evidence['raw_sha256'],
                sensor_evidence_sha256=canonical_sha256(evidence),sensor_alignment_sha256=canonical_sha256(report))
            result=dict(status='HELD',policy=policy,reason=report.get('reason',report['status']),
                alignment_status=report['status'],geometry_status=report.get('geometry_status'),
                room_from_map=report.get('room_from_map'),proposals=deepcopy(report.get('proposals',[])),
                context=context,evidence=evidence,execution_id=trace.execution_id,physical_authority=False,
                alignment_verified=False,current_pose_available=False,preview=None)
            if self.context()!=context or self._inputs(selection['map_id'])[1]!=evidence:
                raise ValueError('SCENE_SENSOR_REVIEW_INPUT_CHANGED')
            if report['status']=='ALIGNMENT_CANDIDATE':
                result['status']='POSE_CANDIDATE'
                if policy=='correct_walls' and report.get('geometry_status')=='BOUNDED_WALL_PROPOSAL_VALIDATED':
                    patch=self._patch(state,report)
                    preview=history.preview(store.source,operation_id='sensor_'+uuid4().hex,mode='dependency',tool_call=patch)
                    from .scene_changes import SceneChange
                    after=history.append(store.source,SceneChange.from_dict(preview['operation'])).effective(store.source)
                    self._verify_delta(state,after,patch)
                    binding=checked_sensor_binding(dict(schema_version='scene-sensor-binding-1.0',policy=policy,
                        context=context,evidence=evidence,alignment_sha256=canonical_sha256(report),
                        preview_sha256=preview['preview_digest'],execution_id=trace.execution_id,physical_authority=False))
                    preview.update(apply_version='scene-edit-apply-2.0',sensor_binding=binding)
                    result.update(status='preview',preview=preview)
            trace.finish('succeeded',sensor_status=result['status']);return result
        except (OSError,ValueError,TypeError,KeyError,BrokerError) as error:
            trace.finish('failed',error=error)
            return dict(status='HELD',policy=policy,reason=str(error)[:240],execution_id=trace.execution_id,
                context=selection['context'],physical_authority=False,alignment_verified=False,
                current_pose_available=False,preview=None)

    def validate_apply(self,binding,operation,store,history):
        binding=checked_sensor_binding(binding)
        if binding is None:return
        if binding['context']!=self.context(store,history) or binding['preview_sha256']!=canonical_sha256(operation):
            raise ValueError('SCENE_SENSOR_APPLY_CONTEXT_CHANGED')
        saved,evidence,height=self._inputs(binding['evidence']['map_id'])
        if evidence!=binding['evidence']:raise ValueError('SCENE_SENSOR_APPLY_EVIDENCE_CHANGED')
        state=history.effective(store.source)
        report=align_photo_map(saved,state.site.scene.to_dict()['objects'],height_m=height,policy='correct_walls',diagnostics=True)
        if canonical_sha256(report)!=binding['alignment_sha256']:
            raise ValueError('SCENE_SENSOR_APPLY_ALIGNMENT_CHANGED')
        patch=self._patch(state,report)
        if operation.get('mode')!='dependency' or operation.get('dependency_patch')!=patch:
            raise ValueError('SCENE_SENSOR_APPLY_PATCH_CHANGED')
        from .scene_changes import SceneChange
        after=history.append(store.source,SceneChange.from_dict(operation)).effective(store.source)
        self._verify_delta(state,after,patch)
