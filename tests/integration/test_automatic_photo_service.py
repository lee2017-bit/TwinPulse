# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Two actual versioned RoomRecipes, shared causal worker and derived ledger.

Synthetic raycast truth belongs to the evaluator, not the production runner.
No provider, device, Isaac stage or measured photo reconstruction is asserted.
"""
import copy
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from PIL import Image

from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_photo_store import AutomaticPhotoStore,load_automatic_room
from twinpulse_app.room_recipe import import_project_room_recipe
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.automatic_photo_alignment import align_photo_map
from twinpulse_core.observation_stream import ObservationWindow
from packages.twinpulse_core.tests.test_automatic_mapping import observations,CONTEXT
from packages.twinpulse_core.tests.test_automatic_photo_alignment import room,mapping
from tests.integration.test_automatic_demo_service import GEOMETRY


def recipe(root,identity,scale,*,import_now=True):
    outline,objects=room(scale);folder=root/'projects'/identity
    (folder/'assets').mkdir(parents=True)
    image=BytesIO();Image.new('RGB',(4,4),(60,70,int(100*scale))).save(image,format='PNG');photo=image.getvalue()
    (folder/'assets/room.png').write_bytes(photo)
    # A synthetic product fixture must not read a developer's private room
    # photo or Burger installation merely to obtain a generic plan header.
    # Geometry, raycaster inputs and fit/validation criteria remain unchanged.
    plan={'plan_version':'2.0','scene_id':identity,
          'summary':'Synthetic approximate room; no measured geometry',
          'image_observations':'Synthetic room photo fixture; structure is inferred'}
    plan['calls']=[{'call_id':'floor','tool':'create_floor','arguments':{'id':'floor','center_m':[0,0],'size_m':[3*scale,4*scale]}}]
    for obj in objects[1:-1]:
        p=copy.deepcopy(obj['transform']['position_m'])
        if obj['id']=='wall_4':p[1]+=.12 # nominal photo error; hidden raycast outline stays unchanged
        plan['calls'].append({'call_id':obj['id'],'tool':'create_wall','arguments':{'id':obj['id'],
            'position_m':p,'dimensions_m':obj['shape']['dimensions_m'],'yaw_deg':obj['transform']['rotation_rpy_deg'][2]}})
    plan['call_evidence']=[{'call_id':c['call_id'],'observation_ids':[],'basis':'inferred','note':'Synthetic approximate photo recipe, not measured'} for c in plan['calls']]
    value={'schema_version':'room-recipe-1.0','project_id':identity,'prompt':'Synthetic photo-room regression, not measured',
           'photo':{'relative_path':'assets/room.png','sha256':sha256(photo).hexdigest()},'plan':plan}
    (folder/'room_recipe.json').write_text(json.dumps(value),encoding='utf-8')
    if import_now:import_project_room_recipe(root,identity)
    return outline,objects


class RaycastSource:
    def __init__(self,identity,outline):
        self.context={**CONTEXT,'project_id':identity};self.window=ObservationWindow(self.context);self.outline=outline
        self.positions=[[.35*math.sin(i*.045),-.7+i*.006,.35+i*.004] for i in range(180)]
    def __iter__(self):yield from observations(self.positions,outline=self.outline,context=self.context)


class AutomaticPhotoServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_two_named_recipes_start_auto_apply_persist_reopen_rollback_preserve_originals(self):
        for identity,scale in (('room_one',1.),('room_two',1.2)):
            outline,truth=recipe(self.root,identity,scale)
            folder=self.root/'projects'/identity
            before={p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()}
            service=AutomaticDemoService(self.root,identity,source_factory=lambda *a:RaycastSource(identity,outline),geometry_loader=lambda:GEOMETRY)
            self.addCleanup(service.close)
            service.start('owner','a'*32,photo_policy='correct_walls');service.worker.join(15)
            job=service.snapshot('owner')['job'];self.assertEqual(job['state'],'COMPLETED',job)
            photo=job['result']['photo_alignment']
            self.assertEqual(photo['status'],'ALIGNMENT_CANDIDATE',
                {k:v for k,v in photo.items() if k in ('status','reason','geometry_status','proposals','geometry_rejections','fit_error_m','validation_before_m')})
            self.assertEqual(photo.get('geometry_status'),'AUTO_APPLIED_DERIVED_REVISION',
                {k:v for k,v in photo.items() if k in ('status','reason','geometry_status','proposals','geometry_rejections','fit_error_m','validation_before_m')})
            self.assertTrue(photo['applied_revision']);self.assertTrue(photo['goal_revalidation_required'])
            self.assertLess(math.dist(photo['room_from_map'][:2],[0,-.7]),.10)
            target=photo['effective_objects'][5]['transform']['position_m']
            self.assertLess(math.dist(target[:2],truth[5]['transform']['position_m'][:2]),.07)
            current=service.photo_store.current(load_automatic_room(self.root,identity))
            self.assertEqual(current['objects'],photo['effective_objects'])
            reopened=service.reopen('any-reader',job['map_id'])
            self.assertEqual(reopened['photo_alignment']['report_revision'],photo['report_revision'])
            self.assertIsNone(reopened['pose_candidate']);self.assertFalse(reopened['motion_authorized'])
            with self.assertRaises(BrokerError):service.rollback_photo('wrong-owner',job['job_id'],photo['applied_revision'])
            if identity=='room_two':
                service.close();service=AutomaticDemoService(self.root,identity)
                self.addCleanup(service.close)
                self.assertIsNone(service.snapshot('owner')['job'])
                self.assertIsNone(service.reopen('owner',job['map_id'])['pose_candidate'])
            restored=service.rollback_photo('owner',job['job_id'],photo['applied_revision'])['photo_alignment']
            self.assertEqual(restored['geometry_status'],'ROLLED_BACK')
            self.assertEqual(service.photo_store.current(load_automatic_room(self.root,identity))['objects'],load_automatic_room(self.root,identity)['objects'])
            with self.assertRaises(BrokerError):service.rollback_photo('owner',job['job_id'],photo['applied_revision'])
            for name,data in before.items():self.assertEqual((folder/name).read_bytes(),data)

    def test_alignment_only_no_apply_and_room_hash_change_rejects_late_result(self):
        identity='align_only';outline,_=recipe(self.root,identity,1.)
        service=AutomaticDemoService(self.root,identity,source_factory=lambda *a:RaycastSource(identity,outline),geometry_loader=lambda:GEOMETRY)
        self.addCleanup(service.close);service.start('owner','a'*32,photo_policy='align_only');service.worker.join(15)
        job=service.snapshot('owner')['job'];self.assertEqual(job['state'],'COMPLETED',job)
        self.assertIsNone(job['result']['photo_alignment']['applied_revision'])
        self.assertIsNone(service.photo_store.current(load_automatic_room(self.root,identity))['head'])
        count=[0];loader=service.room_loader
        def changed(*args):
            count[0]+=1;value=loader(*args)
            if count[0]>1:value['revision']='e'*64
            return value
        service.room_loader=changed;service.start('owner','b'*32,photo_policy='correct_walls');service.worker.join(15)
        failed=service.snapshot('owner')['job'];self.assertEqual(failed['error'],'PHOTO_ROOM_CHANGED',failed)
        self.assertEqual(failed['error_stage'],'REVERIFY_PHOTO_ROOM')
        self.assertIsNone(service.photo_store.current(loader(self.root,identity))['head'])

    def test_cancel_during_alignment_no_late_map_or_apply(self):
        identity='cancel';outline,_=recipe(self.root,identity,1.)
        service=AutomaticDemoService(self.root,identity,source_factory=lambda *a:RaycastSource(identity,outline),geometry_loader=lambda:GEOMETRY)
        self.addCleanup(service.close);entered=threading.Event();release=threading.Event()
        def gated(*args,**kwargs):entered.set();release.wait(10);return align_photo_map(*args,**kwargs)
        with patch('twinpulse_app.automatic_demo_service.align_photo_map',gated):
            job=service.start('owner','a'*32,photo_policy='correct_walls')['job'];self.assertTrue(entered.wait(10))
            service.control('owner',job['job_id'],'cancel');release.set();service.worker.join(5)
        self.assertEqual(service.snapshot('owner')['job']['state'],'CANCELLED')
        self.assertEqual(service.maps()['maps'],[])
        self.assertIsNone(service.photo_store.current(load_automatic_room(self.root,identity))['head'])

    def test_ledger_chain_tamper_cross_project_revision_conflicts_and_capacity(self):
        _,objects=room();base={'project_id':'room','objects':objects,'photo_revision':'b'*64}
        from twinpulse_core.revisions import canonical_sha256
        base['revision']=canonical_sha256(base);store=AutomaticPhotoStore(self.root,'room')
        corrected=copy.deepcopy(objects);corrected[1]['transform']['position_m'][1]+=.1
        event=store.append(base,None,corrected,action='apply',job_id='a'*32,map_revision='c'*64)
        with self.assertRaisesRegex(ValueError,'HEAD_CHANGED'):store.append(base,None,corrected,action='apply',job_id='b'*32,map_revision='c'*64)
        with self.assertRaises(ValueError):AutomaticPhotoStore(self.root,'other').current(base)
        path=store._ledger(base)/'0000.json';value=json.loads(path.read_text());value['objects'][1]['shape']['dimensions_m'][2]+=1
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'HASH_OR_CHAIN'):store.current(base)


if __name__=='__main__':unittest.main()
