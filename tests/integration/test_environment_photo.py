# SPDX-License-Identifier: Apache-2.0
"""Fake completion/real App and parser. No live model or hardware acceptance."""
from contextlib import contextmanager
from copy import deepcopy
import asyncio
import base64
import hashlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import sys
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_core.environment_photo import (VERSION,CATALOG_SIZES,PHOTO_KINDS,PROPOSABLE_KINDS,checked_photo_candidates,
    overlay_kind_for,photo_context,possible_duplicates,suggest_position)
from twinpulse_core.environment_overlays import KINDS,add_overlay,footprint,overlay_objects
from twinpulse_core.environment_navigation import convex_overlap_area
from twinpulse_core.room_item_catalog import room_item_catalog_version
from twinpulse_app.environment_photo_review import EnvironmentPhotoReview
from twinpulse_app.single_photo_scope import SinglePhotoLedger
from twinpulse_app.library_asset_store import atomic_json
from twinpulse_provider.environment_photo import generate_environment_photo
from twinpulse_provider.errors import ProviderConfigurationError
from twinpulse_provider.nebius_pipeline import ChatCompletion
from tests.integration import test_environment_model_move as fixture
from tests.integration.test_environment_import import source


def output():
    return dict(schema_version=VERSION,candidates=[dict(id='Candidate_1',kind='basket',label='Basket',confidence=.8,
        bbox=[.1,.2,.4,.7],description='A visible basket; exact scene identity is unverified.',near=None)],explanation='Review duplicates and place the center explicitly.')


def candidate_output(kind,label):
    value=output();value['candidates'][0].update(kind=kind,label=label);return value


def saved_output(value,version='environment-photo-candidates-1.0'):
    """A reply as an earlier build saved it: rows without 'near'."""
    value=deepcopy(value);value['schema_version']=version
    for row in value['candidates']:row.pop('near')
    return value


def overlay(identity,kind,label,basis='photo_estimate',sha='a'*64):
    return dict(item=dict(id=identity,kind=kind,label=label),evidence=dict(basis=basis,sha256=sha))


def box(name,category,x0,y0,x1,y1,height,yaw=0.):
    """A closed box mesh (scanned furniture or a thin wall), optionally turned about its centre."""
    cx,cy=(x0+x1)/2,(y0+y1)/2;c,s=math.cos(math.radians(yaw)),math.sin(math.radians(yaw))
    corner=lambda x,y:[cx+(x-cx)*c-(y-cy)*s,cy+(x-cx)*s+(y-cy)*c]
    points=[[*corner(x,y),z] for z in (0.,height) for y in (y0,y1) for x in (x0,x1)]
    faces=[[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],[2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]]
    return dict(id='Env_'+hashlib.sha256(name.encode()).hexdigest()[:20],source_path='/Source/'+name,category=category,label=name,
        points_m=points,triangles=faces,color_rgb=[.5,.6,.7],translation_m=[0,0,0])


def room(*meshes,overlays=()):
    """A 4 x 3 m rectangular floor with the given scanned meshes (and added boxes)."""
    value=source();floor=dict(value['meshes'][0],points_m=[[0,0,0],[4,0,0],[4,3,0],[0,3,0]],triangles=[[0,1,2],[0,2,3]])
    value['meshes']=[floor,*meshes]
    if overlays:value=dict(value,schema_version='environment-static-1.1',overlays=list(overlays))
    return value


def placed(placement,kind,identity='Added_'+'1'*20):
    """The overlay the Review form would preview from a suggestion, with the exact same numbers."""
    target=overlay_kind_for(kind)
    return dict(item=dict(id=identity,kind=target,label=kind,catalog_version=room_item_catalog_version(target),position_m=placement['position_m'],
        dimensions_m=placement['dimensions_m'],yaw_deg=placement['yaw_deg'],observation_time_utc=None),uncertainty_m=placement['uncertainty_m'],
        evidence=dict(basis='photo_estimate',source_name='photo.png',sha256='b'*64,alignment_verified=False))


def body(placement):
    (x,y,_),(w,d,_)=placement['position_m'],placement['dimensions_m'];c,s=math.cos(math.radians(placement['yaw_deg'])),math.sin(math.radians(placement['yaw_deg']))
    return [[x+a*c-b*s,y+a*s+b*c] for a,b in ((-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2))]


def outline(mesh):
    """The mesh's xy outline in polygon order (sorted by angle about its centre), translation included."""
    points=list({(round(p[0]+mesh['translation_m'][0],9),round(p[1]+mesh['translation_m'][1],9)) for p in mesh['points_m']})
    cx,cy=sum(x for x,_ in points)/len(points),sum(y for _,y in points)/len(points)
    return [[x,y] for x,y in sorted(points,key=lambda p:math.atan2(p[1]-cy,p[0]-cx))]


def planar(name,category,x0,y0,x1,y1,height):
    """A vertical panel with no thickness: its floor projection is a line."""
    value=box(name,category,x0,y0,x1,y1,height);value['points_m']=[[x0,y0,0.],[x1,y1,0.],[x1,y1,height],[x0,y0,height]]
    value['triangles']=[[0,1,2],[0,2,3]];return value


def turned_room(environment,degrees):
    """The same room turned about (2, 1.5): every mesh point, translation included."""
    c,s=math.cos(math.radians(degrees)),math.sin(math.radians(degrees));value=deepcopy(environment)
    for mesh in value['meshes']:
        mesh['points_m']=[[2+(x+t[0]-2)*c-(y+t[1]-1.5)*s,1.5+(x+t[0]-2)*s+(y+t[1]-1.5)*c,z] for x,y,z in mesh['points_m'] for t in [mesh['translation_m']]]
        mesh['translation_m']=[0,0,mesh['translation_m'][2]]
    return value


class EnvironmentPhotoTests(unittest.TestCase):
    @contextmanager
    def workspace(self,*,value=None,hook=None):
        with fixture.EnvironmentModelMoveTests().workspace() as (space,app,workflow,draft,provider,calls):
            provider.observer_model_id='supplementary-fake-observer';provider.stage_output_token_caps['observer']=1000
            deferred=SimpleNamespace(start=lambda:None,is_alive=lambda:False)
            async def complete(stage,body,token,config):
                calls.append(deepcopy(body))
                if hook:hook(space,app,workflow,draft,token)
                return ChatCompletion('fake-response',provider.observer_model_id,json.dumps(value if value is not None else output()),'stop',{},'fake-attempt')
            provider._complete_stage=complete
            with patch('twinpulse_app.environment_photo_review.Thread',return_value=deferred):
                yield space,app,workflow,draft,provider,calls

    def image(self):
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(40,30),(30,40,50)).save(stream,format='PNG')
        return dict(name='fixture.png',bytes_base64=base64.b64encode(stream.getvalue()).decode())

    def start(self,space,*,consent=True,request='photo-request'):
        state=space.snapshot('owner')
        return space.action(dict(action='photo_analyze',request_id=request,expected_scene_revision=state['scene_revision'],photo=self.image(),consent=consent),'owner')

    def complete_job(self,space):
        self.start(space);space.photos._run(space.photos.job,space.photos.token)
        self.assertEqual(space.photos.job['status'],'ready',space.photos.job['error'])
        return space.photos.job

    def preview_body(self,space,job,request='candidate-preview'):
        return dict(action='photo_candidate_preview',request_id=request,expected_scene_revision=space.snapshot('owner')['scene_revision'],
            obstacle=dict(kind='basket',label='Reviewed basket',position_xy_m=[1.3,1.3],dimensions_m=[.35,.3,.4],yaw_deg=0.,uncertainty_m=.2),
            candidate_ref=dict(job_id=job['job_id'],candidate_id='Candidate_1'),duplicate_reviewed=True)

    def saved_job(self,space,value):
        """A ready job exactly as a build saved it (job.json, result.json, latest.json) for a cold reload."""
        job=self.complete_job(space);folder=space.photos.root/job['job_id'];atomic_json(folder/'result.json',value)
        job=dict(job,candidates=value['candidates'],explanation=value['explanation'],
            response_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest())
        space.photos._save_job(job);return job

    def test_candidate_contract_rejects_metric_fields_nan_inverted_or_duplicate_regions(self):
        for change in ('metric','nan','inverted','duplicate','kind','seven','id7','version','version_type'):
            value=output()
            if change=='metric':value['candidates'][0]['position_m']=[1,1,0]
            if change=='nan':value['candidates'][0]['confidence']=float('nan')
            if change=='inverted':value['candidates'][0]['bbox']=[.5,0,.1,1]
            if change=='duplicate':value['candidates']*=2
            if change=='kind':value['candidates'][0]['kind']='robot'
            if change=='seven':value['candidates']=[dict(value['candidates'][0],id='Candidate_%d'%(i%6+1)) for i in range(7)]
            if change=='id7':value['candidates'][0]['id']='Candidate_7'
            if change=='version':value['schema_version']='environment-photo-candidates-0.9'
            if change=='version_type':value['schema_version']=[VERSION]
            with self.subTest(change=change),self.assertRaises(ValueError):checked_photo_candidates(value)
        empty=output();empty['candidates']=[];checked_photo_candidates(empty)
        six=output();six['candidates']=[dict(six['candidates'][0],id='Candidate_%d'%i,kind=k) for i,k in
            zip(range(1,7),('sofa','bed','office_chair','floor_covering','floor_fan','desk'))]
        checked_photo_candidates(six);checked_photo_candidates(six,fresh=True,context=dict(existing_props=[],scanned_objects=[]))
        # A saved 1.1 record may name any library kind; a fresh reply only a proposable one.
        blind=candidate_output('window_blind','Blind');checked_photo_candidates(blind)
        with self.assertRaises(ValueError):checked_photo_candidates(blind,fresh=True,context=dict(existing_props=[],scanned_objects=[]))
        saved=saved_output(output());checked_photo_candidates(saved)
        with self.assertRaises(ValueError):checked_photo_candidates(saved,fresh=True,context=dict(existing_props=[],scanned_objects=[]))
        # The 1.0 reader keeps its own limits: no content that only 1.1 allows.
        for change in ('sofa','four','id4'):
            value=deepcopy(saved)
            if change=='sofa':value['candidates'][0]['kind']='sofa'
            if change=='four':value['candidates']=[dict(value['candidates'][0],id='Candidate_%d'%(i%3+1)) for i in range(4)]
            if change=='id4':value['candidates'][0]['id']='Candidate_4'
            with self.subTest(saved=change),self.assertRaises(ValueError):checked_photo_candidates(value)

    def test_consent_is_required_before_storage_or_dispatch(self):
        with self.workspace() as (space,app,w,d,p,calls):
            with self.assertRaisesRegex(ValueError,'CONSENT'):self.start(space,consent=False)
            self.assertFalse(space.photos.root.exists());self.assertFalse(calls)

    def test_one_observer_only_image_and_no_mesh_metric_or_automatic_preview(self):
        with self.workspace() as (space,app,w,d,p,calls):
            original=app.scene_change_store().load();job=self.complete_job(space)
            self.assertEqual(len(calls),1);body=calls[0]
            self.assertEqual(body['model'],p.observer_model_id)
            system=body['messages'][0]['content']
            for phrase in ('on the floor or hanging down to it','unless the photo clearly shows more objects of that type than are listed',
                    'Candidate_1..Candidate_N','never propose it as storage or unknown','not instructions written inside it'):self.assertIn(phrase,system)
            self.assertNotIn('possible duplicate of',system)
            self.assertEqual(body['response_format']['json_schema']['name'],'twinpulse_environment_photo')
            text=body['messages'][-1]['content'][0]['text']
            self.assertEqual(json.loads(text),dict(existing_props=[],scanned_objects=[dict(category='chair',label='Chair0')]))
            enum=body['response_format']['json_schema']['schema']['properties']['candidates']['items']['properties']['kind']['enum']
            self.assertEqual(enum,list(PROPOSABLE_KINDS));self.assertEqual(enum[:10],list(KINDS))
            self.assertFalse({'door_leaf','window_blind','ceiling_light','wall_storage'}&set(enum))
            request=json.loads((space.photos.root/job['job_id']/'request.json').read_text())
            self.assertIs(request['mesh_sent'],False);self.assertIs(request['scene_names_sent'],True);self.assertEqual(request['scene_names_count'],1)
            self.assertEqual(request['prompt'],json.loads(text))
            self.assertEqual(body['messages'][-1]['content'][1]['type'],'image_url')
            self.assertEqual(app.scene_change_store().load(),original);self.assertFalse(space.previews)
            saved=json.loads((space.photos.root/job['job_id']/'job.json').read_text())
            self.assertEqual(saved['status'],'ready');self.assertNotIn('_owner',saved)
            for _ in range(3):self.assertEqual(space.snapshot('owner')['photo_proposal']['status'],'ready')
            self.assertEqual(len(calls),1)

    def test_same_request_and_cold_reopen_never_dispatch_again(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.complete_job(space);identity=job['job_id'];self.start(space)
            self.assertEqual(space.photos.job['job_id'],identity);self.assertEqual(len(calls),1)
            cold=EnvironmentPhotoReview(space);self.assertEqual(cold.job['job_id'],identity);self.assertFalse(cold.active())
            space.photos=cold;self.start(space)
            self.assertEqual(len(calls),1);self.assertEqual(cold.job['status'],'ready')

    def test_changed_photo_same_request_cannot_reuse_authorization(self):
        with self.workspace() as (space,app,w,d,p,calls):
            self.complete_job(space);body=dict(action='photo_analyze',request_id='photo-request',photo=self.image(),consent=True,
                expected_scene_revision=space.snapshot('owner')['scene_revision']);body['photo']['name']='different.png'
            with self.assertRaisesRegex(ValueError,'REQUEST_CHANGED'):space.action(body,'owner')
            self.assertEqual(len(calls),1)

    def test_interrupted_job_is_failed_cold_without_restart_or_ready(self):
        with self.workspace() as (space,app,w,d,p,calls):
            self.start(space);cold=EnvironmentPhotoReview(space)
            self.assertEqual(cold.job['status'],'failed');self.assertIn('unknown',cold.job['error'])
            space.photos=cold;self.start(space);self.assertEqual(cold.job['status'],'failed');self.assertFalse(calls)

    def test_explicit_candidate_preview_uses_exact_photo_and_pinned_adoption(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.complete_job(space);body=self.preview_body(space,job);state=space.action(body,'owner');preview=state['preview']
            evidence=preview['operation']['tool_call']['arguments']['environment']['overlays'][0]['evidence']
            self.assertEqual(evidence,job['photo']);self.assertFalse(evidence['alignment_verified'])
            exact,_=space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner')
            self.assertEqual(exact,preview['operation']);self.assertFalse(app.scene_change_store().path.exists())
            history=app.scene_change_store().apply(preview['operation'],preview['preview_digest']);w._publish_scene_change(app.scene_change_store(),history)
            with self.assertRaisesRegex(ValueError,'ALREADY_REPRESENTED'):space.action(self.preview_body(space,job,request='duplicate'),'owner')

    def test_user_duplicate_confirmation_kind_and_current_revision_are_required(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.complete_job(space)
            for change in ('duplicate','kind','revision','id'):
                body=self.preview_body(space,job)
                if change=='duplicate':body['duplicate_reviewed']=False
                if change=='kind':body['obstacle']['kind']='bag'
                if change=='revision':body['expected_scene_revision']='0'*64
                if change=='id':body['candidate_ref']['candidate_id']='Candidate_3'
                with self.subTest(change=change),self.assertRaises(ValueError):space.action(body,'owner')
            self.assertFalse(space.previews)

    def test_response_or_adoption_tampering_blocks_apply_without_second_call(self):
        for target in ('result','adoption'):
            with self.subTest(target=target),self.workspace() as (space,app,w,d,p,calls):
                job=self.complete_job(space);preview=space.action(self.preview_body(space,job),'owner')['preview']
                folder=space.photos.root/job['job_id']
                path=folder/'result.json' if target=='result' else next((folder/'adoptions').glob('*.json'))
                value=json.loads(path.read_text());value['explanation' if target=='result' else 'model_id']='tampered';atomic_json(path,value)
                with self.assertRaises(ValueError):space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner')
                self.assertEqual(len(calls),1)

    def test_photo_cancel_and_apply_admission_share_one_fence(self):
        for admitted in (False,True):
            with self.subTest(admitted=admitted),self.workspace() as (space,app,w,d,p,calls):
                job=self.complete_job(space);preview=space.action(self.preview_body(space,job),'owner')['preview']
                cancel=dict(action='photo_cancel',request_id='cancel',job_id=job['job_id'])
                if admitted:
                    space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner',claim=True)
                    with self.assertRaisesRegex(ValueError,'ALREADY_ADMITTED'):space.action(cancel,'owner')
                    self.assertEqual(job['status'],'ready')
                else:
                    space.action(cancel,'owner')
                    with self.assertRaises(ValueError):space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner',claim=True)

    def test_invalid_output_cancel_scene_change_and_storage_failure_never_publish_ready(self):
        def cancel(space,app,w,d,token):token.cancel()
        def change(space,app,w,d,token):w._input=None
        for mode in ('invalid','cancel','scene','storage'):
            value=output()
            if mode=='invalid':value['candidates'][0]['bbox']=[1,1,0,0]
            with self.subTest(mode=mode),self.workspace(value=value,hook=cancel if mode=='cancel' else change if mode=='scene' else None) as (space,app,w,d,p,calls):
                self.start(space);job=space.photos.job
                if mode=='storage':
                    with patch('twinpulse_app.environment_photo_review.atomic_json',side_effect=OSError('diagnostics failed')):space.photos._run(job,space.photos.token)
                else:space.photos._run(job,space.photos.token)
                self.assertIn(job['status'],('failed','cancelled'));self.assertFalse(job['candidates']);self.assertFalse(space.previews)
                self.assertEqual(len(calls),0 if mode=='storage' else 1)

    def test_failed_cancel_storage_still_revokes_existing_preview_in_this_process(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.complete_job(space);preview=space.action(self.preview_body(space,job),'owner')['preview']
            with patch.object(space.photos,'_save_job',side_effect=OSError('cancel storage failed')):
                with self.assertRaises(OSError):space.action(dict(action='photo_cancel',request_id='cancel',job_id=job['job_id']),'owner')
            with self.assertRaisesRegex(ValueError,'CANCELLED'):
                space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner',claim=True)
            with self.assertRaisesRegex(ValueError,'CANCELLED'):space.action(self.preview_body(space,job,request='again'),'owner')
            self.assertFalse(app.scene_change_store().path.exists());self.assertEqual(len(calls),1)

    def test_late_diagnostic_or_publication_failure_cannot_revive_ready_cold(self):
        for failure in ('flush','publish'):
            with self.subTest(failure=failure),self.workspace() as (space,app,w,d,p,calls):
                self.start(space);job=space.photos.job
                with patch.object(space.photos,'_save_job',side_effect=OSError('job storage failed')):
                    if failure=='flush':
                        with patch.object(app.diagnostics,'flush',return_value=False):space.photos._run(job,space.photos.token)
                    else:space.photos._run(job,space.photos.token)
                self.assertEqual(job['status'],'failed');self.assertFalse(job['candidates']);self.assertEqual(len(calls),1)
                saved=json.loads((space.photos.root/job['job_id']/'job.json').read_text())
                self.assertEqual(saved['status'],'running')
                cold=EnvironmentPhotoReview(space)
                self.assertEqual(cold.job['status'],'failed');self.assertIn('unknown',cold.job['error'])
                self.assertFalse(cold.job['candidates']);self.assertEqual(len(calls),1)

    def test_single_dispatch_ledger_keeps_unknown_attempt_spent(self):
        for failure in (False,True):
            ledger=Mock(state=dict(requests=[]))
            if failure:ledger.reserve.side_effect=OSError('original failure')
            owner=SinglePhotoLedger(ledger)
            if failure:
                with self.assertRaises(OSError):owner.reserve(dict(model='fixture'))
            else:owner.reserve(dict(model='fixture'))
            with self.assertRaisesRegex(ProviderConfigurationError,'ONE_CALL'):owner.reserve(dict(model='fixture'))
            self.assertEqual(ledger.reserve.call_count,1)

    def test_kinds_are_the_model_library_and_mapping_never_widens_overlays(self):
        from twinpulse_core.model_library import library_models,FURNITURE_MODELS
        from twinpulse_provider.photo_layout import KINDS as PLANNER,SIZES
        self.assertEqual(PHOTO_KINDS,PLANNER);self.assertEqual(set(PHOTO_KINDS),{e['kind'] for e in library_models()})
        self.assertEqual(set(CATALOG_SIZES),set(PHOTO_KINDS))
        self.assertTrue(all(0<v<=3 for size in CATALOG_SIZES.values() for v in size))
        for kind in KINDS:self.assertEqual(overlay_kind_for(kind),kind)
        for kind in PHOTO_KINDS:self.assertIn(overlay_kind_for(kind),(*KINDS,None))
        self.assertEqual(PROPOSABLE_KINDS,(*KINDS,*(k for k in PHOTO_KINDS if k not in KINDS and overlay_kind_for(k))))
        for kind,(default,*_) in FURNITURE_MODELS.items():
            self.assertEqual(overlay_kind_for(kind),'unknown');self.assertEqual(CATALOG_SIZES[kind],default)
        for kind,size in SIZES.items():
            if kind not in KINDS:self.assertEqual(CATALOG_SIZES[kind],size)
        # Floor hazards with a precise kind stay addable as a conservative unknown box.
        for kind in ('floor_covering','hanging_clothes','monitor','tabletop_item','bedding_overhang','clothes_rack','pallet','rack','pallet_stack'):
            self.assertEqual(overlay_kind_for(kind),'unknown')
        for kind in ('window_blind','ceiling_light','ceiling_fixture','wall_fixture','wall_storage','surface_covering','door_leaf','robot'):
            self.assertIsNone(overlay_kind_for(kind));self.assertNotIn(kind,PROPOSABLE_KINDS)

    def test_context_is_bounded_names_without_geometry(self):
        def mesh(label,category):return dict(category=category,label=label,points_m=[[1,2,3]],color_rgb=[1,1,1],translation_m=[0,0,0])
        meshes=[mesh('Floor0','floor'),mesh('Wall0','wall'),mesh('Door0','door'),mesh('Window1','window'),mesh('Opening0','unknown')]+[
            mesh('Thing%d'%i+'x'*100,'unknown') for i in range(100)]+[mesh('Sofa0','sofa'),mesh('Refrigerator0','refrigerator')]
        environment=dict(meshes=meshes,overlays=[overlay('Added_couch','unknown','Gray fabric couch'),overlay('Added_lidar','unknown','LiDAR unknown #1','lidar_estimate')])
        context=photo_context(environment,{'Added_couch':'sofa'})
        self.assertEqual(set(context),{'existing_props','scanned_objects'})
        self.assertEqual(context['existing_props'],[dict(kind='sofa',label='Gray fabric couch'),dict(kind='unknown',label='LiDAR unknown #1')])
        rows=context['scanned_objects'];self.assertEqual(len(rows),64)
        self.assertEqual(rows[:2],[dict(category='sofa',label='Sofa0'),dict(category='refrigerator',label='Refrigerator0')])
        self.assertTrue(all(set(r)=={'category','label'} and len(r['label'])<=80 for r in rows))
        text=json.dumps(context)
        for absent in ('Floor0','Wall0','Door0','Window1','Opening0','points_m','color_rgb','translation_m'):self.assertNotIn(absent,text)

    def test_provider_refuses_unbounded_or_geometric_context_before_any_call(self):
        image=SimpleNamespace(mime_type='image/png',content=b'x');row=dict(category='chair',label='Chair0')
        for context in (dict(existing_props=[]),dict(existing_props=[],scanned_objects=[row]*65),
                dict(existing_props=[],scanned_objects=[dict(row,points_m='[1,2,3]')]),dict(existing_props=[],scanned_objects=[dict(row,label='')]),
                dict(existing_props=[],scanned_objects=[dict(row,label='x'*121)]),dict(existing_props=[],scanned_objects=[dict(row,label=[1,2])]),
                dict(existing_props=[dict(kind='box',label='Box')]*33,scanned_objects=[]),dict(existing_props=[],scanned_objects=[],position_m=[1,1])):
            request=SimpleNamespace(schema_version=VERSION,images=(image,),inference_scope=None,prompt=json.dumps(context))
            request.inference_scope=Mock(bind=Mock(side_effect=AssertionError('called before the context check')))
            with self.subTest(context=str(context)[:60]),self.assertRaisesRegex(ProviderConfigurationError,'CONTEXT_INVALID'):
                asyncio.run(generate_environment_photo(None,request,None,None))
            request.inference_scope.bind.assert_not_called()

    def test_fresh_reply_must_be_current_version_and_proposable(self):
        old=saved_output(output())
        for value in (candidate_output('window_blind','Blind'),candidate_output('door_leaf','Door'),old):
            with self.subTest(value=value['candidates'][0]['kind']+value['schema_version']),self.workspace(value=value) as (space,app,w,d,p,calls):
                self.start(space);space.photos._run(space.photos.job,space.photos.token)
                self.assertEqual(space.photos.job['status'],'failed');self.assertIn('PHOTO_CANDIDATE',space.photos.job['error'])
                self.assertFalse(space.photos.job['candidates']);self.assertEqual(len(calls),1)

    def test_furniture_candidate_previews_as_a_conservative_labelled_unknown_box(self):
        def body(space,job,**obstacle):
            value=self.preview_body(space,job,request='furniture-preview');value['obstacle'].update(obstacle);return value
        with self.workspace(value=candidate_output('sofa','Sofa')) as (space,app,w,d,p,calls):
            job=self.complete_job(space);c=space.snapshot('owner')['photo_proposal']['candidates'][0]
            self.assertEqual((c['overlay_kind'],c['addable'],c['dimensions_m'],c['duplicate_check_required'],c['possible_duplicates']),
                ('unknown',True,[1.6,.8,.85],True,[]))
            for kind in ('sofa','basket'):
                with self.subTest(kind=kind),self.assertRaises(ValueError):
                    space.action(body(space,job,kind=kind,label='Sofa',dimensions_m=[1.6,.8,.85],position_xy_m=[1.3,1.]),'owner')
            state=space.action(body(space,job,kind='unknown',label='Sofa',dimensions_m=[1.6,.8,.85],position_xy_m=[1.3,1.]),'owner')
            added=state['preview']['operation']['tool_call']['arguments']['environment']['overlays'][0]
            self.assertEqual((added['item']['kind'],added['item']['label'],added['item']['dimensions_m']),('unknown','Sofa',[1.6,.8,.85]))
            self.assertEqual(added['evidence'],job['photo']);self.assertFalse(added['evidence']['alignment_verified'])
            receipt=json.loads(next((space.photos.root/job['job_id']/'adoptions').glob('*.json')).read_text())
            self.assertEqual((receipt['position_basis'],receipt['candidate']['kind'],receipt['metric_alignment_verified']),('user_reviewed_estimate','sofa',False))
            self.assertFalse(app.scene_change_store().path.exists())
            # The floor envelope still applies: a sofa box 0.4 m from a wall leaves the scanned floor.
            with self.assertRaisesRegex(ValueError,'OUTSIDE_FLOOR'):
                space.action(body(space,job,kind='unknown',label='Sofa',dimensions_m=[1.6,.8,.85],position_xy_m=[1.3,.4],uncertainty_m=.05),'owner')

    def test_wall_or_ceiling_candidate_is_recognised_but_never_added(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.saved_job(space,candidate_output('window_blind','Blind'));space.photos=EnvironmentPhotoReview(space)
            c=space.snapshot('owner')['photo_proposal']['candidates'][0];self.assertEqual((c['overlay_kind'],c['addable']),(None,False))
            for kind in ('unknown','window_blind'):
                body=self.preview_body(space,job,request='blind-'+kind);body['obstacle'].update(kind=kind,label='Blind')
                with self.subTest(kind=kind),self.assertRaises(ValueError):space.action(body,'owner')
            body=self.preview_body(space,job,request='blind');body['obstacle'].update(kind='unknown',label='Blind')
            with self.assertRaisesRegex(ValueError,'NOT_ADDABLE'):space.action(body,'owner')
            self.assertFalse(space.previews);self.assertEqual(len(calls),1)

    def test_saved_one_point_zero_job_reloads_cold_and_still_previews(self):
        with self.workspace() as (space,app,w,d,p,calls):
            value=saved_output(output())
            job=self.saved_job(space,value);cold=EnvironmentPhotoReview(space);space.photos=cold
            self.assertIsNone(cold.load_error);self.assertEqual(cold.job['status'],'ready')
            c=space.snapshot('owner')['photo_proposal']['candidates'][0]
            self.assertEqual((c['kind'],c['overlay_kind'],c['addable'],c['dimensions_m']),('basket','basket',True,[.35,.3,.4]))
            self.assertIn('preview',space.action(self.preview_body(space,job),'owner'));self.assertEqual(len(calls),1)
        with self.workspace() as (space,app,w,d,p,calls):
            value=saved_output(candidate_output('sofa','Sofa'))
            self.saved_job(space,value);space.photos=EnvironmentPhotoReview(space)
            state=space.snapshot('owner')['photo_proposal'];self.assertEqual((state['status'],state['candidates']),('failed',[]))

    def test_possible_duplicates_name_scanned_meshes_and_still_need_the_human_check(self):
        with self.workspace(value=candidate_output('office_chair','Desk chair')) as (space,app,w,d,p,calls):
            job=self.complete_job(space)
            self.assertEqual(space.snapshot('owner')['photo_proposal']['candidates'][0]['possible_duplicates'],['Chair0'])
            body=self.preview_body(space,job);body['obstacle'].update(kind='unknown',label='Desk chair',dimensions_m=[.6,.6,.9]);body['duplicate_reviewed']=False
            with self.assertRaisesRegex(ValueError,'DUPLICATE_REVIEW'):space.action(body,'owner')
        env=dict(meshes=[dict(category='unknown',label='Bed0'),dict(category='table',label='Table1'),dict(category='storage',label='Storage0'),
                dict(category='refrigerator',label='Refrigerator0'),dict(category='unknown',label='Opening0'),dict(category='unknown',label='Television0')],
            overlays=[overlay('Added_laundry','basket','Laundry'),overlay('Added_couch','unknown','Gray fabric couch'),
                overlay('Added_lidar','unknown','LiDAR unknown #1','lidar_estimate')])
        receipts={'Added_couch':'sofa'}
        self.assertEqual(possible_duplicates('storage',env,receipts),['Storage0','Refrigerator0','LiDAR unknown #1'])
        self.assertEqual(possible_duplicates('wardrobe',env,receipts),['Storage0','Refrigerator0','LiDAR unknown #1'])
        self.assertEqual(possible_duplicates('sofa',env,receipts),['Gray fabric couch','LiDAR unknown #1'])
        self.assertEqual(possible_duplicates('sofa',env,{}),['LiDAR unknown #1'])
        self.assertEqual(possible_duplicates('bed',env,receipts),['Bed0','LiDAR unknown #1'])
        self.assertEqual(possible_duplicates('desk',env,receipts),['Table1','LiDAR unknown #1'])
        self.assertEqual(possible_duplicates('monitor',env,receipts),['Television0','LiDAR unknown #1'])
        self.assertEqual(possible_duplicates('unknown',env,receipts),['Gray fabric couch','LiDAR unknown #1'])
        self.assertEqual(possible_duplicates('basket',env,receipts),['Laundry'])
        self.assertEqual(possible_duplicates('floor_fan',env,receipts),[])
        # Strongest first: an earlier box recognised as this kind, then scanned names; anonymous LiDAR outlines fill the rest.
        home=dict(meshes=[dict(category='refrigerator',label='Refrigerator0'),*(dict(category='storage',label='Storage%d'%i) for i in range(3)),dict(category='sofa',label='Sofa0')],
            overlays=[*(overlay('Added_lidar%d'%i,'unknown','LiDAR unknown #%d'%i,'lidar_estimate') for i in range(1,6)),overlay('Added_tall','unknown','Tall white wardrobe')])
        self.assertEqual(possible_duplicates('wardrobe',home,{'Added_tall':'wardrobe'}),['Tall white wardrobe','Refrigerator0','Storage0','Storage1','Storage2',
            'LiDAR unknown #1','LiDAR unknown #2','LiDAR unknown #3'])
        self.assertEqual(possible_duplicates('sofa',home,{'Added_tall':'wardrobe'})[:2],['Sofa0','LiDAR unknown #1'])
        laundry=dict(meshes=[],overlays=[overlay('Added_old','basket','Old basket'),overlay('Added_seen','basket','Laundry hamper')])
        self.assertEqual(possible_duplicates('basket',laundry,{'Added_seen':'basket'}),['Laundry hamper','Old basket'])
        many=dict(meshes=[dict(category='chair',label='Chair%d'%i) for i in range(12)],overlays=[])
        self.assertEqual(len(possible_duplicates('chair',many,{})),8)

    def test_adopted_photo_box_keeps_its_recognised_kind_for_hints_and_the_next_analysis(self):
        with self.workspace(value=candidate_output('sofa','Sofa')) as (space,app,w,d,p,calls):
            job=self.complete_job(space);body=self.preview_body(space,job,request='couch')
            body['obstacle'].update(kind='unknown',label='Gray fabric couch',dimensions_m=[1.6,.8,.85],position_xy_m=[1.3,1.])
            preview=space.action(body,'owner')['preview'];overlay_id=preview['operation']['tool_call']['arguments']['environment']['overlays'][0]['item']['id']
            history=app.scene_change_store().apply(preview['operation'],preview['preview_digest']);w._publish_scene_change(app.scene_change_store(),history)
            self.assertEqual(space.photos.adopted_kinds(space.photos._current(job)[0]),{overlay_id:'sofa'})
            self.assertEqual(space.snapshot('owner')['photo_proposal']['candidates'][0]['possible_duplicates'],['Gray fabric couch'])
            space.photos=EnvironmentPhotoReview(space)  # cold: receipts are read back from disk
            self.assertEqual(space.snapshot('owner')['photo_proposal']['candidates'][0]['possible_duplicates'],['Gray fabric couch'])
            self.start(space,request='second-photo');space.photos._run(space.photos.job,space.photos.token)
            self.assertEqual(json.loads(calls[-1]['messages'][-1]['content'][0]['text'])['existing_props'],[dict(kind='sofa',label='Gray fabric couch')])

    def test_receipt_hints_open_only_receipts_of_photo_boxes_in_the_scene(self):
        with self.workspace(value=candidate_output('sofa','Sofa')) as (space,app,w,d,p,calls):
            job=self.complete_job(space);body=self.preview_body(space,job,request='couch')
            body['obstacle'].update(kind='unknown',label='Gray fabric couch',dimensions_m=[1.6,.8,.85],position_xy_m=[1.3,1.])
            preview=space.action(body,'owner')['preview']
            history=app.scene_change_store().apply(preview['operation'],preview['preview_digest']);w._publish_scene_change(app.scene_change_store(),history)
            receipt=next((space.photos.root/job['job_id']/'adoptions').glob('*.json'));value=json.loads(receipt.read_text())
            # 1100 earlier previews that were never applied, all sorted ahead of the applied one.
            folder=space.photos.root/('0'*32)/'adoptions';folder.mkdir(parents=True)
            for i in range(1100):(folder/('environment_edit_%032x.json'%i)).write_text(json.dumps(dict(value,overlay_id='Added_%020x'%i)))
            cold=EnvironmentPhotoReview(space);space.photos=cold
            with patch.object(cold,'_read',wraps=cold._read) as read:
                for _ in range(2):self.assertEqual(space.snapshot('owner')['photo_proposal']['candidates'][0]['possible_duplicates'],['Gray fabric couch'])
            self.assertEqual([c.args[0] for c in read.call_args_list if 'adoptions' in str(c.args[0])],[receipt])

    def test_suggestion_sits_at_the_end_of_a_long_scanned_anchor_and_turns_with_it(self):
        sofa=box('Sofa0','sofa',1.,2.,2.6,2.8,.85);environment=room(sofa)
        placement,reason=suggest_position('basket','Sofa0',environment,uncertainty_m=.2)
        self.assertIsNone(reason)
        # A 1.6 m sofa: beside its freer end (not in its legroom), 5 cm away, the basket's long edge along that end.
        self.assertEqual((placement['anchor'],placement['basis'],placement['alignment_verified'],placement['side'],placement['at_end'],placement['gap_m']),
            ('Sofa0','photo_near_anchor',False,'+x',True,.05))
        self.assertEqual((placement['position_m'],placement['yaw_deg']),([2.8,2.4,.2],90.))
        self.assertEqual(convex_overlap_area(body(placement),outline(sofa)),0.)
        # The exact add-time contract accepts the suggested numbers, still as an unaligned photo estimate.
        added=add_overlay(environment,placed(placement,'basket'))['overlays'][0]
        self.assertEqual((added['evidence']['basis'],added['evidence']['alignment_verified']),('photo_estimate',False))
        self.assertEqual(placement['envelope_xy'],[p[:2] for p in footprint(overlay_objects(added)[-1])])
        # A turned anchor: the box takes its frame, turned to lie along the end it stands at.
        turned=box('Sofa0','sofa',1.,1.,2.6,1.8,.85,yaw=30.);placement,_=suggest_position('chair','Sofa0',room(turned))
        self.assertEqual((placement['yaw_deg'],placement['at_end']),(120.,True))
        self.assertEqual(convex_overlap_area(body(placement),outline(turned)),0.);add_overlay(room(turned),placed(placement,'chair'))

    def test_suggestion_follows_the_anchor_when_the_room_is_turned(self):
        # A wardrobe-like storage, long along y: a desk at its end lies along that end, whatever the room axes are.
        environment=room(box('Storage0','storage',1.,.8,1.6,2.,1.9));first,_=suggest_position('desk','Storage0',environment,uncertainty_m=.05)
        self.assertEqual((first['position_m'],first['yaw_deg'],first['at_end']),([1.3,2.35,.37],0.,True))
        for degrees in (90.,-90.,180.):
            with self.subTest(degrees=degrees):
                c,s=math.cos(math.radians(degrees)),math.sin(math.radians(degrees));x,y=first['position_m'][0]-2,first['position_m'][1]-1.5
                second,_=suggest_position('desk','Storage0',turned_room(environment,degrees),uncertainty_m=.05)
                for got,expected in zip(second['position_m'][:2],(2+x*c-y*s,1.5+x*s+y*c)):self.assertAlmostEqual(got,expected,places=6)
                self.assertAlmostEqual((second['yaw_deg']-first['yaw_deg']-degrees)%180,0.,places=6)

    def test_long_anchor_suggestion_keeps_its_legroom_and_door_passages_free(self):
        # A sofa against the wall with a coffee table 45 cm in front: the basket goes to a sofa end, never between them.
        sofa=box('Sofa0','sofa',1.,2.1,3.,2.95,.85);table=box('Table0','table',1.5,1.2,2.5,1.65,.45)
        placement,_=suggest_position('basket','Sofa0',room(sofa,table),uncertainty_m=.2)
        self.assertEqual((placement['side'],placement['at_end']),('+x',True))
        self.assertEqual(convex_overlap_area(body(placement),[[1.,1.65],[3.,1.65],[3.,2.1],[1.,2.1]]),0.)
        # A desk beside the only door: nothing lands in the 0.8 m in front of it (suggestions only; the add contract is unchanged).
        desk=box('Table0','table',2.5,2.4,3.95,2.95,.75);door=box('Door0','door',1.5,2.97,2.4,3.03,2.)
        self.assertGreater(convex_overlap_area(body(suggest_position('basket','Table0',room(desk),uncertainty_m=.2)[0]),[[1.5,2.2],[2.4,2.2],[2.4,3.],[1.5,3.]]),0.)
        placement,reason=suggest_position('basket','Table0',room(desk,door),uncertainty_m=.2);self.assertIsNone(reason)
        self.assertEqual(convex_overlap_area(body(placement),[[1.5,2.2],[2.4,2.2],[2.4,3.],[1.5,3.]]),0.)
        add_overlay(room(desk,door),placed(placement,'basket'))
        opening=dict(box('Opening0','unknown',1.5,2.97,2.4,3.03,2.))
        placement,_=suggest_position('basket','Table0',room(desk,opening),uncertainty_m=.2)
        self.assertEqual(convex_overlap_area(body(placement),[[1.5,2.2],[2.4,2.2],[2.4,3.],[1.5,3.]]),0.)

    def test_suggestion_respects_walls_floor_edge_and_other_objects(self):
        # The free side of the sofa is a 10 cm slot before a partition wall: it must go elsewhere.
        sofa=box('Sofa0','sofa',.9,1.,1.9,2.,.85);wall=box('Wall1','wall',2.,0.,2.1,3.,2.4)
        placement,reason=suggest_position('basket','Sofa0',room(sofa,wall),uncertainty_m=.2)
        self.assertIsNone(reason);self.assertLessEqual(max(p[0] for p in body(placement)),2.)
        self.assertNotEqual(placement['side'],'+x');self.assertEqual(suggest_position('basket','Sofa0',room(sofa),uncertainty_m=.2)[0]['side'],'+x')
        # Against the floor edge the whole envelope stays on the scanned floor: +0.10 m for furniture as an unknown box and
        # for a cable bundle (entanglement), none for a basket. The suggestion carries exactly the envelope add_overlay builds.
        corner=box('Storage0','storage',0.,0.,.8,.45,.9)
        for kind,margin,expected in (('basket',.2,[.4,.65]),('office_chair',.05,[.5,.8]),('cable_bundle',.2,[.65,.6])):
            with self.subTest(kind=kind):
                placement,_=suggest_position(kind,'Storage0',room(corner),uncertainty_m=margin)
                self.assertEqual((placement['side'],placement['gap_m'],placement['position_m'][:2]),('+y',.05,expected))
                added=add_overlay(room(corner),placed(placement,kind))['overlays'][0]
                self.assertEqual(placement['envelope_xy'],[p[:2] for p in footprint(overlay_objects(added)[-1])])
                self.assertTrue(all(0<=x<=4 and 0<=y<=3 for x,y in placement['envelope_xy']))
        # Another scanned object or an added envelope beside the anchor is not free floor either.
        chair=box('Chair0','chair',1.,1.55,1.5,1.95,.9);table=box('Table0','table',1.,2.,2.6,2.8,.75)
        placement,_=suggest_position('basket','Table0',room(table,chair),uncertainty_m=.2)
        self.assertEqual(convex_overlap_area(body(placement),outline(chair)),0.)
        boxed=room(box('Box0','storage',1.8,1.3,2.2,1.7,.5),box('Ring1','storage',1.,.5,3.,1.25,.5),box('Ring2','storage',1.,1.75,3.,2.5,.5),
            box('Ring3','storage',1.,1.25,1.75,1.75,.5),box('Ring4','storage',2.25,1.25,3.,1.75,.5))
        self.assertEqual(suggest_position('basket','Box0',boxed,uncertainty_m=.2),(None,'NO_FREE_FLOOR_NEAR_ANCHOR'))
        lidar=placed(dict(position_m=[2.85,2.4,.2],dimensions_m=[.3,.3,.4],yaw_deg=0.,uncertainty_m=.1),'unknown')
        lidar['evidence']=dict(basis='lidar_estimate',source_name='route.json',sha256='c'*64,alignment_verified=False)
        sofa=box('Sofa0','sofa',1.,2.,2.6,2.8,.85);placement,_=suggest_position('basket','Sofa0',room(sofa,overlays=[lidar]),uncertainty_m=.2)
        self.assertEqual(placement['side'],'-x');self.assertEqual(convex_overlap_area(body(placement),[p[:2] for p in footprint(overlay_objects(lidar)[-1])]),0.)

    def test_low_planar_and_overhead_meshes_near_the_anchor(self):
        sofa=box('Sofa0','sofa',1.,2.,2.6,2.8,.85);alone,_=suggest_position('floor_fan','Sofa0',room(sofa),uncertainty_m=.2)
        self.assertEqual(alone['side'],'+x')
        # A 0.3 m ottoman lower than the 1.1 m fan still blocks it; a 1 cm thin panel (zero floor area) blocks like a box.
        for blocker in (box('Ottoman0','storage',2.65,2.,3.2,2.8,.3),planar('Panel0','storage',2.85,2.,2.85,2.8,.5)):
            with self.subTest(blocker=blocker['label']):
                placement,_=suggest_position('floor_fan','Sofa0',room(sofa,blocker),uncertainty_m=.2)
                self.assertNotEqual(placement['position_m'],alone['position_m'])
                self.assertEqual(convex_overlap_area(body(placement),[[x-.03,y] for x,y in outline(blocker)]+[[x+.03,y] for x,y in outline(blocker)][::-1]
                    if blocker['label']=='Panel0' else outline(blocker)),0.)
        # A wall cabinet entirely above the box does not block the floor under it.
        cabinet=box('Storage1','storage',2.65,2.,3.2,2.8,.9);cabinet['points_m']=[[x,y,z+1.6] for x,y,z in cabinet['points_m']]
        self.assertEqual(suggest_position('basket','Sofa0',room(sofa,cabinet),uncertainty_m=.2),suggest_position('basket','Sofa0',room(sofa),uncertainty_m=.2))

    def test_moved_anchor_is_placed_from_its_current_position(self):
        moved=box('Sofa0','sofa',1.,2.,2.6,2.8,.85);moved['translation_m']=[-.5,-.6,0.]
        built=box('Sofa0','sofa',.5,1.4,2.1,2.2,.85);self.assertEqual(suggest_position('basket','Sofa0',room(moved)),suggest_position('basket','Sofa0',room(built)))
        self.assertNotEqual(suggest_position('basket','Sofa0',room(moved)),suggest_position('basket','Sofa0',room(box('Sofa0','sofa',1.,2.,2.6,2.8,.85))))

    def test_suggestions_of_one_photo_do_not_stack_and_an_added_box_can_anchor(self):
        environment=room(box('Sofa0','sofa',1.,2.,2.6,2.8,.85));first,_=suggest_position('basket','Sofa0',environment,uncertainty_m=.2)
        second,_=suggest_position('basket','Sofa0',environment,uncertainty_m=.2,taken=[first['envelope_xy']])
        self.assertEqual((first['side'],second['side']),('+x','-x'));self.assertEqual(convex_overlap_area(body(second),first['envelope_xy']),0.)
        # More than the two ends: the long sides follow, corners first (beside the sofa, not before its middle).
        third,_=suggest_position('basket','Sofa0',environment,uncertainty_m=.2,taken=[first['envelope_xy'],second['envelope_xy']])
        self.assertEqual((third['side'],third['at_end'],third['position_m'][:2]),('-y',False,[2.425,1.8]))
        # The freer corner first: a box 0.5 m before the right half sends it to the left corner.
        crowded=room(box('Sofa0','sofa',1.,2.,2.6,2.8,.85),box('Box1','storage',2.2,1.3,2.5,1.5,.5))
        third,_=suggest_position('basket','Sofa0',crowded,uncertainty_m=.2,taken=[first['envelope_xy'],second['envelope_xy']])
        self.assertEqual((third['side'],third['position_m'][:2]),('-y',[1.175,1.8]))
        # An added box anchors by its own box, not its keepout: a LiDAR box with 0.3 m uncertainty still gets a 5 cm neighbour.
        for kind,margin in (('bag',.2),('unknown',.3)):
            with self.subTest(kind=kind):
                prop=placed(dict(position_m=[2.,1.,.175],dimensions_m=[.3,.25,.35],yaw_deg=0.,uncertainty_m=margin),kind);prop['item']['label']='Laundry bag'
                placement,reason=suggest_position('basket','Laundry bag',room(overlays=[prop]),uncertainty_m=.2)
                self.assertIsNone(reason);self.assertEqual(placement['gap_m'],.05)
                self.assertEqual(convex_overlap_area(body(placement),[[1.85,.875],[2.15,.875],[2.15,1.125],[1.85,1.125]]),0.)

    def test_no_suggestion_without_a_found_single_anchor_or_for_coverings(self):
        environment=room(box('Sofa0','sofa',1.,2.,2.6,2.8,.85),box('Door0','door',3.,2.9,3.9,3.,2.))
        for kind,near,reason in (('basket','Sofa9','ANCHOR_NOT_FOUND'),('basket',None,'NO_ANCHOR'),('basket','Door0','ANCHOR_NOT_FOUND'),
                ('floor_covering','Sofa0','COVERING_NOT_SUGGESTED'),('surface_covering','Sofa0','NOT_ADDABLE'),('window_blind','Sofa0','NOT_ADDABLE')):
            with self.subTest(kind=kind,near=near):self.assertEqual(suggest_position(kind,near,environment),(None,reason))
        twins=room(box('Chair0','chair',1.,1.,1.4,1.4,.9),box('Chair0','chair',2.,1.,2.4,1.4,.9))
        twins['meshes'][2]['id']='Env_'+'f'*20;twins['meshes'][2]['source_path']='/Source/Chair0b'
        self.assertEqual(suggest_position('basket','Chair0',twins),(None,'ANCHOR_AMBIGUOUS'))

    def test_near_is_versioned_and_a_fresh_reply_may_only_name_a_sent_label(self):
        context=dict(existing_props=[dict(kind='unknown',label='LiDAR unknown #1')],scanned_objects=[dict(category='sofa',label='Sofa0')])
        for near in (None,'Sofa0','LiDAR unknown #1'):
            value=output();value['candidates'][0]['near']=near;checked_photo_candidates(value,fresh=True,context=context)
        for near in ('Sofa1','',7,['Sofa0']):
            value=output();value['candidates'][0]['near']=near
            with self.subTest(near=near),self.assertRaises(ValueError):checked_photo_candidates(value,fresh=True,context=context)
        # A fresh reply is never checked without the context that was sent.
        value=output();value['candidates'][0]['near']='Sofa1'
        with self.assertRaisesRegex(ValueError,'PHOTO_CANDIDATE_CONTEXT_REQUIRED'):checked_photo_candidates(value,fresh=True)
        missing=output();missing['candidates'][0].pop('near')
        with self.assertRaises(ValueError):checked_photo_candidates(missing)
        # A saved 1.1 job stays readable with its own row shape, and cannot carry an anchor.
        saved=saved_output(candidate_output('sofa','Sofa'),'environment-photo-candidates-1.1');checked_photo_candidates(saved)
        with self.assertRaises(ValueError):checked_photo_candidates(saved,fresh=True,context=context)
        with self.assertRaises(ValueError):checked_photo_candidates(dict(saved,candidates=[dict(saved['candidates'][0],near=None)]))

    def test_saved_one_point_one_job_reloads_cold_without_a_suggestion(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.saved_job(space,saved_output(output(),'environment-photo-candidates-1.1'));space.photos=EnvironmentPhotoReview(space)
            self.assertIsNone(space.photos.load_error);c=space.snapshot('owner')['photo_proposal']['candidates'][0]
            self.assertEqual((c['near'],c['suggested'],c['suggestion_reason'],c['batch_addable'],c['addable']),(None,None,'NO_ANCHOR',False,True))
            self.assertIn('preview',space.action(self.preview_body(space,job),'owner'))

    def test_anchor_enum_lists_only_sent_names_and_an_invented_anchor_is_refused(self):
        invented=output();invented['candidates'][0]['near']='Sofa0'
        with self.workspace(value=invented) as (space,app,w,d,p,calls):
            # One earlier added box: it is sent as an existing prop and may be named too.
            preview=space.action(dict(action='add_overlay_preview',request_id='manual-box',expected_scene_revision=space.snapshot('owner')['scene_revision'],
                obstacle=dict(kind='box',label='Moving box',position_xy_m=[1.3,1.3],dimensions_m=[.3,.3,.3],yaw_deg=0.,uncertainty_m=.2),photo=None),'owner')['preview']
            history=app.scene_change_store().apply(preview['operation'],preview['preview_digest']);w._publish_scene_change(app.scene_change_store(),history)
            self.start(space);space.photos._run(space.photos.job,space.photos.token)
            self.assertEqual(space.photos.job['status'],'failed');self.assertIn('PHOTO_CANDIDATE_ANCHOR_INVALID',space.photos.job['error'])
            schema=calls[0]['response_format']['json_schema']['schema']['properties']['candidates']['items']
            self.assertEqual(schema['properties']['near']['enum'],['Chair0','Moving box',None]);self.assertIn('near',schema['required'])
            system=calls[0]['messages'][0]['content']
            for phrase in ('stands directly next to in the photo','never guess coordinates or distances','no positions'):self.assertIn(phrase,system)
            request=json.loads((space.photos.root/space.photos.job['job_id']/'request.json').read_text())
            self.assertEqual(request['near_labels_sent'],2);self.assertNotIn('points_m',json.dumps(request['prompt']))

    def test_snapshot_suggests_beside_the_anchor_and_the_reviewed_add_accepts_it(self):
        value=output();value['candidates']=[dict(value['candidates'][0],near='Chair0'),dict(value['candidates'][0],id='Candidate_2',near='Chair0'),
            dict(value['candidates'][0],id='Candidate_3',kind='office_chair',label='Desk chair',near='Chair0'),
            dict(value['candidates'][0],id='Candidate_4',kind='floor_covering',label='Rug',near='Chair0'),
            dict(value['candidates'][0],id='Candidate_5',kind='sofa',label='Sofa',near=None)]
        with self.workspace(value=value) as (space,app,w,d,p,calls):
            job=self.complete_job(space);rows={c['id']:c for c in space.snapshot('owner')['photo_proposal']['candidates']}
            first,second=rows['Candidate_1']['suggested'],rows['Candidate_2']['suggested']
            self.assertEqual((first['anchor'],first['basis'],first['uncertainty_m'],first['alignment_verified']),('Chair0','photo_near_anchor',.2,False))
            self.assertEqual(convex_overlap_area(body(second),first['envelope_xy']),0.)
            self.assertEqual(convex_overlap_area(body(first),[[.5,.5],[.9,.5],[.5,.9]]),0.)
            # The desk chair may already be the scanned Chair0: no pre-fill, manual entry with its duplicate check.
            self.assertEqual([rows[i]['suggestion_reason'] for i in sorted(rows)],[None,None,'POSSIBLE_DUPLICATE','COVERING_NOT_SUGGESTED','NO_ANCHOR'])
            self.assertEqual([rows[i]['batch_addable'] for i in sorted(rows)],[True,True,False,False,False])
            body_=self.preview_body(space,job);body_['obstacle'].update(position_xy_m=first['position_m'][:2],yaw_deg=first['yaw_deg'],uncertainty_m=first['uncertainty_m'])
            preview=space.action(body_,'owner')['preview'];added=preview['operation']['tool_call']['arguments']['environment']['overlays'][0]
            self.assertEqual((added['item']['position_m'],added['evidence'],added['evidence']['alignment_verified']),(first['position_m'],job['photo'],False))
            # The receipt says the position is the local suggestion beside Chair0, never an alignment.
            receipt=json.loads((space.photos.root/job['job_id']/'adoptions'/(preview['operation']['operation_id']+'.json')).read_text())
            self.assertEqual((receipt['position_basis'],receipt['position_anchor'],receipt['metric_alignment_verified']),('photo_near_anchor','Chair0',False))
            history=app.scene_change_store().apply(preview['operation'],preview['preview_digest']);w._publish_scene_change(app.scene_change_store(),history)
            rows={c['id']:c for c in space.snapshot('owner')['photo_proposal']['candidates']}
            # The added box is a sibling from the same photo, not a duplicate: the next candidate still qualifies, beside it.
            self.assertEqual((rows['Candidate_1']['suggestion_reason'],rows['Candidate_2']['batch_addable']),('ALREADY_ADDED',True))
            self.assertEqual(rows['Candidate_2']['possible_duplicates'],['Reviewed basket'])
            self.assertEqual(convex_overlap_area(body(rows['Candidate_2']['suggested']),[p[:2] for p in footprint(overlay_objects(added)[-1])]),0.)
            # A different box that only shares the sibling's label is outside this job: by identity, Candidate_2 may be it.
            other=space.action(dict(action='add_overlay_preview',request_id='same-label',expected_scene_revision=space.snapshot('owner')['scene_revision'],
                obstacle=dict(kind='basket',label='Reviewed basket',position_xy_m=[1.,3.],dimensions_m=[.35,.3,.4],yaw_deg=0.,uncertainty_m=.2),photo=None),'owner')['preview']
            history=app.scene_change_store().apply(other['operation'],other['preview_digest']);w._publish_scene_change(app.scene_change_store(),history)
            c=next(c for c in space.snapshot('owner')['photo_proposal']['candidates'] if c['id']=='Candidate_2')
            self.assertEqual((c['suggested'],c['suggestion_reason'],c['batch_addable']),(None,'POSSIBLE_DUPLICATE',False))

    def test_possible_duplicate_gets_no_suggestion_and_reserves_no_spot(self):
        value=candidate_output('office_chair','Desk chair');value['candidates'][0]['near']='Chair0'
        value['candidates'].append(dict(output()['candidates'][0],id='Candidate_2',near='Chair0'))
        with self.workspace(value=value) as (space,app,w,d,p,calls):
            self.complete_job(space);rows=space.snapshot('owner')['photo_proposal']['candidates']
            self.assertEqual((rows[0]['possible_duplicates'],rows[0]['suggested'],rows[0]['suggestion_reason'],rows[0]['batch_addable']),
                (['Chair0'],None,'POSSIBLE_DUPLICATE',False))
            # The basket after it gets the spot it would get alone.
            environment,_=space._current_review(app.site_draft)
            self.assertEqual(rows[1]['suggested'],suggest_position('basket','Chair0',environment,uncertainty_m=.2)[0])

    def test_snapshot_suggestion_follows_a_moved_anchor(self):
        value=output();value['candidates'][0]['near']='Chair0'
        with self.workspace(value=value) as (space,app,w,d,p,calls):
            self.complete_job(space);state=space.snapshot('owner');before=state['photo_proposal']['candidates'][0]['suggested']
            chair=next(o for o in state['objects'] if o['label']=='Chair0')
            preview=space.action(dict(action='move_preview',request_id='move-chair',object_id=chair['id'],translation_m=[.3,.2,0.],
                expected_scene_revision=state['scene_revision']),'owner')['preview']
            history=app.scene_change_store().apply(preview['operation'],preview['preview_digest']);w._publish_scene_change(app.scene_change_store(),history)
            after=space.snapshot('owner')['photo_proposal']['candidates'][0]['suggested']
            self.assertEqual((after['side'],after['gap_m']),(before['side'],before['gap_m']))
            for a,b,delta in zip(after['position_m'],before['position_m'],(.3,.2,0.)):self.assertAlmostEqual(a-b,delta,places=6)
