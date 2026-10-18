# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual automatic App photo correction: accurate model versus fixed wall error.

Truth is only the synthetic raycaster/evaluator. No fit result or transform is
injected, no browser selection, robot, physical calibration or furniture edit.
"""
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
SOURCES=('tests/integration/test_photo_nominal_product.py',
    'tests/integration/test_automatic_photo_service.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_photo_alignment.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_demo_service.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_photo_store.py')


class PhotoNominalProductTests(unittest.TestCase):
    def test_two_recipes_exact_nominal_is_not_edited_and_error_improves_disjoint_holdout(self):
        name=os.environ.get('TWINPULSE_NOMINAL_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[];passed=[]
        for scale in (1.,1.2):
            for exact in (True,False):
                identity=f'room{int(scale*10)}_'+('exact' if exact else 'wall_error')
                with self.subTest(case=identity),TemporaryDirectory() as directory:
                    root=Path(directory);outline,truth=recipe(root,identity,scale,import_now=False)
                    path=root/'projects'/identity/'room_recipe.json'
                    if exact:
                        value=json.loads(path.read_text(encoding='utf-8'))
                        call=next(c for c in value['plan']['calls'] if c['call_id']=='wall_4')
                        call['arguments']['position_m'][1]-=.12
                        path.write_text(json.dumps(value),encoding='utf-8')
                    original=path.read_bytes();import_project_room_recipe(root,identity)
                    source=RaycastSource(identity,outline);events=list(source)
                    class RecordedSource:
                        window=source.window
                        def __iter__(self):yield from copy.deepcopy(events)
                    service=AutomaticDemoService(root,identity,source_factory=lambda *a:RecordedSource(),
                                                 geometry_loader=lambda:GEOMETRY)
                    try:
                        service.start('owner','a'*32,photo_policy='correct_walls');service.worker.join(45)
                        complete=not service.worker.is_alive()
                        if not complete:
                            service.control('owner',service.job['job_id'],'cancel');service.worker.join(10)
                        job=service.snapshot('owner')['job'];photo=(job.get('result') or {}).get('photo_alignment') or {}
                        room=load_automatic_room(root,identity);current=service.photo_store.current(room)
                        outcome={'case':identity,'complete':complete,'state':job['state'],'error':job.get('error'),
                            'geometry_status':photo.get('geometry_status'),'proposals':photo.get('proposals'),
                            'fit_sequences':photo.get('fit_sequences'),'validation_sequences':photo.get('validation_sequences'),
                            'validation_before_m':photo.get('validation_before_m'),
                            'validation_after_m':photo.get('validation_after_m'),
                            'target_validation_before_m':photo.get('target_validation_before_m'),
                            'target_validation_after_m':photo.get('target_validation_after_m'),
                            'ledger_events':len(current['events']),'physical_validation':'NOT_RUN'}
                        outcomes.append(outcome)
                        if name:
                            folder=ROOT/'artifacts'/name/identity;folder.mkdir(parents=True,exist_ok=False)
                            for filename,value in (('outcome.json',outcome),('job.json',job),('synthetic-raw.json',events),
                                    ('effective-geometry.json',current)):
                                (folder/filename).write_text(json.dumps(value,allow_nan=False),encoding='utf-8')
                            (folder/'original-recipe.json').write_bytes(original)
                        self.assertTrue(complete,outcome);self.assertEqual(job['state'],'COMPLETED',outcome)
                        self.assertEqual(path.read_bytes(),original)
                        self.assertEqual(photo.get('status'),'ALIGNMENT_CANDIDATE',outcome)
                        self.assertFalse(set(photo['fit_sequences'])&set(photo['validation_sequences']))
                        self.assertFalse(photo['alignment_verified']);self.assertFalse(photo['motion_authorized'])
                        if exact:
                            self.assertEqual(photo['geometry_status'],'UNCHANGED_NO_IDENTIFIABLE_VALIDATED_EDIT',outcome)
                            self.assertFalse(photo['proposals']);self.assertFalse(current['events'])
                            self.assertEqual(current['objects'],room['objects'])
                        else:
                            self.assertEqual(photo['geometry_status'],'AUTO_APPLIED_DERIVED_REVISION',outcome)
                            self.assertEqual(len(current['events']),1)
                            self.assertLess(photo['validation_after_m'],photo['validation_before_m'])
                            self.assertGreaterEqual(photo['target_validation_before_m']-photo['target_validation_after_m'],.025)
                            for before,after in zip(room['objects'],current['objects']):
                                self.assertEqual(before['id'],after['id']);self.assertEqual(before['shape'],after['shape'])
                                self.assertEqual(before['transform']['position_m'][2],after['transform']['position_m'][2])
                            wall=next(o for o in current['objects'] if o['id']=='wall_4')
                            expected=next(o for o in truth if o['id']=='wall_4')
                            self.assertLess(abs(wall['transform']['position_m'][1]-expected['transform']['position_m'][1]),.07)
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
