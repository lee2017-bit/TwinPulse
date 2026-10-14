# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Completed historical surveys -> normal immutable maps. Never live admission."""
import hashlib
import re
from time import monotonic

from twinpulse_core import canonical_sha256
from twinpulse_core.automatic_mapping import AutomaticMapping
from .chat_inspection_visual import checked_source
from .command_broker import BrokerError
from .robot_geometry_evidence import load_geometry_evidence
from .saved_mapping_evidence import saved_observation_source
from .session_history import decode, read_bytes, read_index, review_project_session


def survey_map_id(witness):
    return canonical_sha256({k:witness[k] for k in
        ('project_id','mission_id','mission_report_revision','mission_report_sha256','raw_sha256')})[:32]


class SceneSensorImport:
    def __init__(self,review):
        self.review=review;self.root=review.root;self.maps=review.maps

    def _report_path(self,mission_id):
        if not isinstance(mission_id,str) or not re.fullmatch('[a-f0-9]{32}',mission_id):
            raise ValueError('SCENE_SENSOR_SURVEY_ID_INVALID')
        path=self.root/'artifacts/automatic-mission'/self.maps.project_id/(mission_id+'.json')
        if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('SCENE_SENSOR_SURVEY_PATH_INVALID')
        return path

    def witness(self,mission_id):
        """Re-read every terminal and raw source; no stored fit is trusted."""
        raw=read_bytes(self._report_path(mission_id),4*1024*1024);report=decode(raw)
        if (not isinstance(report,dict) or report.get('schema')!='automatic-mission-report-1.0' or
                report.get('project_id')!=self.maps.project_id or report.get('job_id')!=mission_id or
                report.get('revision')!=canonical_sha256({k:v for k,v in report.items() if k!='revision'})):
            raise ValueError('SCENE_SENSOR_SURVEY_REPORT_CHANGED')
        result=report.get('result') or {};cold=report.get('cold_start') or {}
        goal=report.get('goal')
        if (not isinstance(result,dict) or not isinstance(cold,dict) or not isinstance(goal,dict) or
                goal.get('mode')!='SURVEY_ONLY' or report.get('state')!='MISSION_ARRIVED' or
                cold.get('stage')!='SURVEY_COMPLETE' or result.get('status')!='MISSION_ARRIVED' or
                result.get('mission_id')!=mission_id or result.get('robot_job_id')!=mission_id or
                result.get('sensor_cleanup_confirmed') is not True or result.get('evidence_export')!='COMPLETE' or
                any(report.get(k) for k in ('error','cleanup_error','report_error','error_record_failed'))):
            raise ValueError('SCENE_SENSOR_SURVEY_NOT_COMPLETED_AND_CLEANED')
        room,scene=checked_source(report.get('room_source'),self.maps.project_id)
        if report.get('room_base_revision')!=room['revision']:
            raise ValueError('SCENE_SENSOR_SURVEY_COLLECTION_SOURCE_CHANGED')
        pc=review_project_session(self.root,self.maps.project_id,mission_id)
        folder=self.root/'artifacts/manual-control'/mission_id;bundle=folder/'robot-evidence'
        pc_raw=read_bytes(folder/'result.json',512*1024);pc_result=decode(pc_raw)
        evidence_raw=read_bytes(bundle/'report.json',8*1024*1024);evidence=decode(evidence_raw)
        end=pc.get('recorded_end') or {}
        native_ends=[event['data'] for event in pc.get('mission_events',[]) if event['kind']=='mission_finished']
        scopes=pc.get('mission_scopes',[])
        if (len(native_ends)!=1 or native_ends[0].get('mission_id')!=mission_id or
                native_ends[0].get('status')!='MISSION_ARRIVED' or
                len(scopes)!=1 or scopes[0]['scope'].get('project_id')!=self.maps.project_id or
                scopes[0]['scope'].get('goal',{}).get('mode')!='SURVEY_ONLY'):
            raise ValueError('SCENE_SENSOR_SURVEY_NATIVE_TERMINAL_MISMATCH')
        if (pc['record_status']!='COMPLETE_RECORD' or pc['mode']!='mission' or
                pc.get('provenance')!=report.get('provenance') or
                end.get('status')!='MISSION_ARRIVED' or end.get('cleanup_confirmed') is not True or
                pc_result.get('state')!='FINISHED' or pc_result.get('result')!='MISSION_ARRIVED' or
                pc_result.get('cleanup_confirmed') is not True or pc_result.get('sensor_cleanup_confirmed') is not True or
                evidence.get('mode')!='mission' or evidence.get('status')!='MISSION_ARRIVED' or
                evidence.get('cleanup_confirmed') is not True or evidence.get('sensor_cleanup_confirmed') is not True or
                any(pc_result.get(k) for k in ('cleanup_error','evidence_export_error','native_cleanup_errors')) or
                any(pc[key]!=evidence.get(other) for key,other in
                    (('robot_boot_id','boot_id'),('robot_release_id','release_id'),('robot_session_id','robot_session_id'))) or
                end.get('robot_session_id')!=evidence.get('robot_session_id') or end.get('reason')!=evidence.get('reason')):
            raise ValueError('SCENE_SENSOR_SURVEY_TERMINAL_BINDING_MISSING')
        source=saved_observation_source(self.root,self.maps.project_id,mission_id)
        geometry=load_geometry_evidence();base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
        offset=[base[0]+mount[0],base[1]+mount[1],0.]
        sha=lambda value:hashlib.sha256(value).hexdigest()
        proof=dict(schema_version='scene-sensor-survey-import-1.0',project_id=self.maps.project_id,
            mission_id=mission_id,mission_report_revision=report['revision'],mission_report_sha256=sha(raw),
            collection_source_sha256=canonical_sha256(report['room_source']),collection_input_revision=room['input_revision'],
            collection_scene_revision=scene.revision,collection_objects_sha256=canonical_sha256(room['objects']),
            raw_sha256=source.window.context['source_revision'],footer_sha256=sha(read_bytes(bundle/'ros-messages.raw.footer.json',8*1024*1024)),
            report_sha256=sha(evidence_raw),export_sha256=sha(read_bytes(bundle/'export.json',8*1024*1024)),
            index_sha256=canonical_sha256(read_index(self.root,self.maps.project_id,mission_id)),journal_sha256=pc['sha256'],
            result_sha256=sha(pc_raw),boot_id=evidence['boot_id'],release_id=evidence['release_id'],
            robot_session_id=evidence['robot_session_id'],nominal_geometry_sha256=geometry['revision'],offset=offset,
            provenance=pc['provenance'],physical_authority=False)
        return proof,source,geometry

    def catalog(self):
        folder=self._report_path('0'*32).parent
        if not folder.exists():return dict(surveys=[],physical_authority=False)
        paths=sorted(folder.glob('*.json'))
        if len(paths)>256:raise ValueError('SCENE_SENSOR_SURVEY_CATALOG_BUDGET')
        rows=[]
        for path in paths[-20:]:
            try:
                report=decode(read_bytes(self._report_path(path.stem),4*1024*1024))
                if not isinstance(report,dict) or not isinstance(report.get('goal'),dict) or report['goal'].get('mode')!='SURVEY_ONLY':continue
                row=dict(mission_id=path.stem,report_revision=report.get('revision'),source_job_id=path.stem,
                    provenance=report.get('provenance','UNAVAILABLE'))
                self.witness(path.stem)
                row.update(status='READY',reason='Completed historical survey; geometry and physical authority unchanged')
            except (OSError,ValueError,TypeError,KeyError,BrokerError) as error:
                row=dict(mission_id=path.stem,report_revision=None,source_job_id=path.stem,provenance='UNAVAILABLE')
                row.update(status='HELD',reason=str(error)[:160])
            rows.append(row)
        return dict(surveys=rows,physical_authority=False)

    def validate_map(self,saved):
        witness=saved.get('survey_import')
        if witness is None:return
        if not isinstance(witness,dict):raise ValueError('SCENE_SENSOR_SURVEY_IMPORT_WITNESS_INVALID')
        current,_,_=self.witness(witness.get('mission_id'))
        context=witness.get('import_context')
        from .scene_sensor_review import checked_context
        checked_context(context)
        if (witness!={**current,'import_context':context} or
                context['project_id']!=current['project_id'] or context['input_revision']!=current['collection_input_revision'] or
                saved.get('source_job_id')!=current['mission_id'] or saved.get('source_revision')!=current['raw_sha256']):
            raise ValueError('SCENE_SENSOR_SURVEY_IMPORT_WITNESS_CHANGED')
        # Reuse is bounded to the same saved ORIGINAL/input, not the import-time
        # effective revision: ordinary edits and fresh-revision Undo remain valid.
        workflow=self.review.workflow
        with workflow._lock:
            original=workflow._application.site_draft;selected=workflow._input
            if (original is None or selected is None or selected.revision!=context['input_revision'] or
                    canonical_sha256(original.to_dict())!=context['source_sha256']):
                raise ValueError('SCENE_SENSOR_SURVEY_IMPORT_ORIGINAL_CHANGED')

    def run(self,body,owner):
        context=self.review.context()
        if (body['expected_scene_revision']!=context['current_scene_revision'] or
                body['expected_state_sha256']!=context['current_state_sha256']):
            raise BrokerError('scene_sensor_stale','Current Twin changed before survey import.',status=409)
        workflow=self.review.workflow;tx=workflow.scene_edit_transaction
        # Shared physical start mutex is held through registration, never a live worker mutation.
        with tx.admission(owner):
            with workflow._lock:
                store=workflow._scene_edit_store();history=store.load();state=history.effective(store.source)
                if self.review.context(store,history)!=context:raise BrokerError('scene_sensor_stale','Current Twin changed.',status=409)
            trace=workflow._edit_trace('scene_sensor_import','sensor_import_'+body['mission_id'])
            try:
                witness,source,geometry=self.witness(body['mission_id'])
                if witness['mission_report_revision']!=body['expected_report_revision']:
                    raise BrokerError('scene_sensor_stale','Saved survey report changed.',status=409)
                if (witness['collection_input_revision']!=context['input_revision'] or
                        witness['collection_objects_sha256']!=canonical_sha256(state.site.scene.to_dict()['objects'])):
                    raise ValueError('SCENE_SENSOR_SURVEY_CURRENT_SOURCE_MISMATCH')
                map_id=survey_map_id(witness)
                try:
                    saved=self.maps.load(map_id);self.validate_map(saved)
                    if {k:v for k,v in saved['survey_import'].items() if k!='import_context'}!=witness:
                        raise ValueError('SCENE_SENSOR_SURVEY_DUPLICATE_CONFLICT')
                    duplicate=True
                except FileNotFoundError:
                    processor=AutomaticMapping(source.window.context,witness['offset']);started=monotonic()
                    for index,event in enumerate(source):
                        if index>=65536 or monotonic()-started>30:raise ValueError('SCENE_SENSOR_SURVEY_REPLAY_BUDGET')
                        processor.consume(event)
                    processor.finish();saved=processor.saved_map()
                    saved.update(source_job_id=body['mission_id'],nominal_geometry_revision=geometry['revision'],
                        source_status=source.original_status,source_reason=source.original_reason,processing_summary=processor.snapshot(),
                        survey_import={**witness,'import_context':context})
                    saved.pop('revision');saved['revision']=canonical_sha256(saved)
                    if self.witness(body['mission_id'])[0]!=witness:raise ValueError('SCENE_SENSOR_SURVEY_INPUT_CHANGED')
                    with workflow._lock:
                        if self.review.context()!=context:raise BrokerError('scene_sensor_stale','Current Twin changed during import.',status=409)
                        self.maps.save(map_id,saved)
                    duplicate=False
                self.validate_map(saved)
                trace.finish('succeeded',sensor_status='imported')
                return dict(status='imported',policy='import_only',context=context,map_id=map_id,map_revision=saved['revision'],
                    duplicate=duplicate,mapping_status=saved.get('processing_summary',{}).get('state'),reference_eligible=saved['reference_eligible'],
                    evidence=dict(map_id=map_id,map_revision=saved['revision'],source_job_id=body['mission_id'],
                    provenance=witness['provenance']),survey_import_sha256=canonical_sha256(saved['survey_import']),
                    execution_id=trace.execution_id,physical_authority=False,alignment_verified=False,current_pose_available=False,preview=None)
            except (OSError,ValueError,TypeError,KeyError,BrokerError) as error:
                trace.finish('failed',error=error)
                if isinstance(error,BrokerError) and error.code=='scene_sensor_stale':raise
                return dict(status='HELD',policy='import_only',reason=str(error)[:240],context=context,
                    execution_id=trace.execution_id,physical_authority=False,alignment_verified=False,current_pose_available=False,preview=None)
