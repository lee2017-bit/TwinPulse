# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual recorded App path: wrong structure and unmeasured furniture bounds."""
import copy
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_photo_store import load_automatic_room
from twinpulse_app.room_recipe import import_project_room_recipe
from tests.integration.test_automatic_photo_service import recipe,RaycastSource
from tests.integration.test_automatic_demo_service import GEOMETRY

ROOT=Path(__file__).resolve().parents[2]
SOURCES=('tests/integration/test_photo_conflict_product.py',
    'tests/integration/test_automatic_photo_service.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_photo_alignment.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_demo_service.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_photo_store.py')


class PhotoConflictProductTests(unittest.TestCase):
    def test_two_recipes_wrong_structure_rejected_and_furniture_never_measured_or_edited(self):
        name=os.environ.get('TWINPULSE_PHOTO_CONFLICT_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[];passed=[]
        for scale in (1.,1.2):
            for conflict in ('wrong_structure','displaced_furniture'):
                identity=f'room{int(scale*10)}_{conflict}'
                with self.subTest(case=identity),TemporaryDirectory() as directory:
                    root=Path(directory);outline,_=recipe(root,identity,scale,import_now=False)
                    path=root/'projects'/identity/'room_recipe.json';value=json.loads(path.read_text())
                    for call in value['plan']['calls']:
                        if call['call_id']=='wall_4':call['arguments']['position_m'][1]-=.12
                        if conflict=='wrong_structure' and call['call_id'].startswith('wall_'):
                            arguments=call['arguments']
                            arguments['position_m'][:2]=[v*1.5 for v in arguments['position_m'][:2]]
                            arguments['dimensions_m'][0]*=1.5
                    if conflict=='displaced_furniture':
                        value['plan']['plan_version']='2.1'
                        value['plan']['calls'].append({'call_id':'chair','tool':'place_furniture','arguments':
                            {'id':'chair','kind':'chair','catalog_version':'furniture-blocks-1.0',
                             'center_m':[.6,-.4],'yaw_deg':0.}})
                        value['plan']['call_evidence'].append({'call_id':'chair','observation_ids':[],
                            'basis':'inferred','note':'Photo furniture is deliberately displaced and unmeasured'})
                    path.write_text(json.dumps(value));original=path.read_bytes()
                    import_project_room_recipe(root,identity)
                    source=RaycastSource(identity,outline);events=list(source)
                    class RecordedSource:
                        window=source.window
                        def __iter__(self):yield from copy.deepcopy(events)
                    service=AutomaticDemoService(root,identity,source_factory=lambda *a:RecordedSource(),
                                                 geometry_loader=lambda:GEOMETRY)
                    try:
                        service.start('owner','a'*32,photo_policy='correct_walls');service.worker.join(45)
                        complete=not service.worker.is_alive()
                        if not complete:service.control('owner',service.job['job_id'],'cancel');service.worker.join(10)
                        job=service.snapshot('owner')['job'];photo=(job.get('result') or {}).get('photo_alignment') or {}
                        room=load_automatic_room(root,identity);current=service.photo_store.current(room)
                        outcome={'case':identity,'complete':complete,'state':job['state'],'error':job.get('error'),
                            'alignment_status':photo.get('status'),'reason':photo.get('reason'),
                            'geometry_status':photo.get('geometry_status'),'ledger_events':len(current['events']),
                            'physical_validation':'NOT_RUN'};outcomes.append(outcome)
                        if name:
                            folder=ROOT/'artifacts'/name/identity;folder.mkdir(parents=True,exist_ok=False)
                            for filename,data in (('outcome.json',outcome),('job.json',job),
                                    ('synthetic-raw.json',events),('effective-geometry.json',current)):
                                (folder/filename).write_text(json.dumps(data,allow_nan=False),encoding='utf-8')
                            (folder/'original-recipe.json').write_bytes(original)
                        self.assertTrue(complete,outcome);self.assertEqual(job['state'],'COMPLETED',outcome)
                        self.assertEqual(path.read_bytes(),original);self.assertFalse(photo['motion_authorized'])
                        self.assertFalse(photo['alignment_verified'])
                        if conflict=='wrong_structure':
                            self.assertNotEqual(photo['status'],'ALIGNMENT_CANDIDATE',outcome)
                            self.assertFalse(current['events']);self.assertEqual(current['objects'],room['objects'])
                        else:
                            self.assertEqual(photo['status'],'ALIGNMENT_CANDIDATE',outcome)
                            self.assertEqual(photo['geometry_status'],'UNCHANGED_NO_IDENTIFIABLE_VALIDATED_EDIT',outcome)
                            self.assertFalse(current['events']);self.assertFalse(photo['proposals'])
                            self.assertEqual(current['objects'],room['objects'])
                            chair=next(o for o in current['objects'] if o['id']=='chair_seat')
                            self.assertEqual(chair['transform']['position_m'][:2],[.6,-.4])
                        passed.append(identity)
                    finally:service.close()
        if name:
            folder=ROOT/'artifacts'/name
            (folder/'verification.json').write_text(json.dumps({'status':'PASS' if len(passed)==4 else 'FAILED',
                'validated_cases':passed,'cases':outcomes,'robot_connections':0,'physical_validation':'NOT_RUN',
                'browser_isaac':'NOT_RUN_FOR_THIS_MATRIX',
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*') if p.is_file()}},indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
