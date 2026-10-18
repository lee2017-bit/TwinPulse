# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary actual local calculation/import/replay tests, no model or UI."""
import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from tests.integration.test_scene_edit_transaction import workflow
from twinpulse_core import canonical_sha256
from twinpulse_core.library_assets import MeshAsset,normalize_mesh,expand_library_asset
from twinpulse_core.site_tools import SiteToolPlan
from twinpulse_core.scene_tools import SceneToolCall
from twinpulse_app.library_asset_store import LibraryAssetStore
from twinpulse_app.library_workspace import LibraryWorkspace
from twinpulse_app.library_process import call_csv_mcp
from twinpulse_app.library_tools import csv_summary
from twinpulse_app.command_broker import BrokerError
from twinpulse_provider import CancellationToken

OBJ=b'v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n'


def mesh(scale=1.):
    return normalize_mesh([[0,0,0],[scale,0,0],[0,scale,0],[0,0,scale]],[[0,2,1],[0,1,3],[0,3,2],[1,2,3]],
        logical_asset_id='test_tetrahedron',title='Actual tetrahedron',source_name='tetra.obj',source_sha256=hashlib.sha256(OBJ).hexdigest(),
        origin='Repository-authored test mesh',license='Apache-2.0')


class LibraryWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.workflow=workflow(self.root);self.library=LibraryWorkspace(self.workflow,None)
        self.workflow.library_workspace=self.library

    def tearDown(self):
        self.library.shutdown()
        for worker in self.library.threads.values():worker.join(10)
        self.workflow.shutdown();self.temp.cleanup()

    def wait(self,request):
        until=time.monotonic()+10
        while time.monotonic()<until:
            row=next(j for j in self.library.snapshot()['jobs'] if j['request_id']==request)
            if row['status'] not in {'queued','running'}:return row
            time.sleep(.02)
        self.fail('Owned local job did not finish')

    def source(self,request='import1'):
        return dict(action='import_asset',request_id=request,attachment=dict(name='tetra.obj',media_type='application/octet-stream',
            bytes_base64=base64.b64encode(OBJ).decode(),role='asset_source'),source='Repository authored tetrahedron',license='Apache-2.0',
            source_units='m',source_up_axis='Z')

    def test_mesh_hash_units_axes_and_immutable_nested_arrays(self):
        a=mesh();self.assertEqual(a.dimensions_m,(1.,1.,1.));self.assertEqual(MeshAsset.from_dict(a.to_dict()),a)
        with self.assertRaises(ValueError):MeshAsset.from_dict({**a.to_dict(),'dimensions_m':[2,2,2]})
        raw=a.to_dict();raw['points'][0][0]+=.2
        with self.assertRaises(ValueError):MeshAsset.from_dict(raw)
        a2=mesh(2);self.assertNotEqual(a.asset_ref,a2.asset_ref)
        self.assertEqual(a.logical_asset_id,a2.logical_asset_id)
        with self.assertRaises(ValueError):expand_library_asset(dict(id='part',snapshot=a.to_dict(),position_m=[0,0,0],yaw_deg=0))

    def test_actual_obj_inspect_register_duplicate_and_no_scene_change(self):
        before=self.workflow._application.site_draft.to_dict();revision=self.library.snapshot()['current_scene_revision']
        body=self.source();self.library.action(body);job=self.wait('import1');self.assertEqual(job['status'],'ready',job)
        self.assertEqual(self.library.snapshot()['assets'],[])
        self.library.action(body);self.assertEqual(len(self.library.snapshot()['jobs']),1)
        self.library.action(dict(action='register_job',job_id=job['job_id'],request_id='register'))
        assets=self.library.snapshot()['assets'];self.assertEqual(len(assets),1)
        self.assertEqual(assets[0]['source_sha256'],hashlib.sha256(OBJ).hexdigest())
        self.assertEqual(self.workflow._application.site_draft.to_dict(),before)
        self.assertEqual(self.library.snapshot()['current_scene_revision'],revision)
        self.assertFalse(self.workflow._application.scene_change_store().path.exists())
        self.assertEqual(self.workflow._broker.public_state('owner')['operations'],[])
        with self.assertRaises(BrokerError):self.library.action({**body,'license':'different same request'})

    def test_obj_requires_explicit_units_and_blocks_external_material(self):
        body=self.source();body.pop('source_units');self.library.action(body)
        self.assertEqual(self.wait('import1')['status'],'failed')
        body=self.source('import2');body['attachment']['bytes_base64']=base64.b64encode(b'mtllib ../private.mtl\n'+OBJ).decode()
        self.library.action(body);self.assertIn('EXTERNAL',self.wait('import2')['error'])
        self.assertEqual(self.library.snapshot()['assets'],[])

    def test_polygons_require_tessellation_without_silent_shape_change(self):
        from twinpulse_app.library_tools import read_obj
        with self.assertRaisesRegex(ValueError,'TRIANGULATION_REQUIRED'):
            read_obj(b'v 0 0 0\nv 2 0 0\nv 2 2 0\nv 1 1 0\nv 0 2 0\nf 1 2 3 4 5\n')

    def test_optional_probe_is_an_owned_cancellable_job(self):
        from threading import Event
        from unittest.mock import patch
        entered=Event();released=Event()
        def probe(*args,**kwargs):
            entered.set();released.wait(3)
            return dict(text='local test probe')
        with patch('twinpulse_app.library_workspace.call_csv_mcp',side_effect=probe):
            self.library.action(dict(action='check_extension',extension_id='csv_mcp'))
            self.assertTrue(entered.wait(1));self.assertTrue(self.library.active())
            with self.assertRaisesRegex(BrokerError,'ACTIVE'):
                self.library.action(dict(action='configure_extension',extension_id='csv_mcp',executable='',enabled=False))
            job=self.library.snapshot()['jobs'][-1]
            self.library.action(dict(action='cancel_job',job_id=job['job_id']))
            self.library.shutdown();released.set()
        for worker in self.library.threads.values():worker.join(3)
        self.assertEqual(self.library.snapshot()['jobs'][-1]['status'],'cancelled')
        self.assertNotIn('last_check',self.library.configuration.get('csv_mcp',{}))

    def test_imported_asset_and_existing_recipe_replay_remain_2_3_and_undo(self):
        source=self.workflow._application.site_draft;store=self.workflow._application.scene_change_store();history=store.load()
        a=mesh(.2);self.library.assets.register(a.to_dict())
        revision=history.current_scene_revision
        value=self.library.action(dict(action='preview_placement',asset_id=a.logical_asset_id,version=a.version,
            expected_scene_revision=revision,instance_id='new_asset',position_m=[-.8,-.9,.1],yaw_deg=0,request_id='place'))
        preview=value['placement_preview'];operation=preview['operation']
        state=history.append(source,__import__('twinpulse_app.scene_changes',fromlist=['SceneChange']).SceneChange.from_dict(operation)).effective(source)
        self.assertEqual(state.plan.plan_version,'2.3');self.assertEqual(state.site.scene.library_assets,(a,))
        self.assertEqual(state.site.scene.to_dict(),type(state.site.scene).from_dict(state.site.scene.to_dict()).to_dict())
        second=mesh(.15);self.library.assets.register(second.to_dict())
        self.assertEqual(state.site.scene.library_assets,(a,))
        from twinpulse_app.scene_changes import SceneChange
        changed=history.append(source,SceneChange.from_dict(operation))
        undo=changed.preview(source,operation_id='undo',mode='undo')
        restored=changed.append(source,SceneChange.from_dict(undo['operation'])).effective(source)
        self.assertEqual(restored.site.scene.library_assets,());self.assertNotIn('library_assets',restored.site.scene.to_dict())

    def test_actual_python_and_mcp_calculate_same_csv_and_close(self):
        raw=b'note,duration\na,2\nb,4\nc,6\nd,\ne,no\n';inputs=dict(column='duration')
        expected=csv_summary(raw,inputs);folder=self.root/'mcp';folder.mkdir()
        actual=call_csv_mcp(raw,inputs,folder,CancellationToken())
        self.assertEqual(actual['tables'],expected['tables']);self.assertEqual(actual['transport'],'MCP_stdio')
        self.assertEqual(actual['tables'][0]['rows'][0],["duration",5,3,1,1,12.,4.,2.,6.])
        session=json.loads((folder/'mcp-session.json').read_text());self.assertEqual(session['exit_code'],0)
        self.assertEqual([r['method'] for r in session['events']],['initialize','tools/list','tools/call'])

    def test_placement_pins_exact_numbers_and_same_request_without_mutation(self):
        asset=mesh(.2);self.library.assets.register(asset.to_dict())
        body=dict(action='preview_placement',asset_id=asset.logical_asset_id,version=asset.version,
            expected_scene_revision=self.library.snapshot()['current_scene_revision'],instance_id='pinned_asset',
            position_m=[-.8,-.9,.1],yaw_deg=0.0,request_id='pin1')
        preview=self.library.action(body)['placement_preview']
        self.assertEqual(self.library.action(body)['placement_preview'],preview)
        # Simulate JSON.parse/stringify's loss of integral float notation.
        def js_numbers(value):
            if isinstance(value,float) and value.is_integer():return int(value)
            if isinstance(value,list):return [js_numbers(v) for v in value]
            if isinstance(value,dict):return {k:js_numbers(v) for k,v in value.items()}
            return value
        self.assertNotEqual(canonical_sha256(js_numbers(preview['operation'])),preview['preview_digest'])
        operation,digest=self.library.pinned_placement_operation(preview['preview_id'],preview['preview_digest'])
        self.assertEqual(canonical_sha256(operation),digest)
        # Restart keeps the original immutable version, not a fresh preview.
        restarted=LibraryWorkspace(self.workflow,None)
        self.assertEqual(restarted.pinned_placement_operation(preview['preview_id'],digest),(operation,digest))
        with self.assertRaisesRegex(BrokerError,'CONFLICT'):
            self.library.action({**body,'position_m':[.7,-.9,.1]})
        with self.assertRaisesRegex(BrokerError,'DIGEST_MISMATCH'):
            self.library.pinned_placement_operation(preview['preview_id'],'0'*64)
        with self.assertRaisesRegex(BrokerError,'ID_INVALID'):
            self.library.pinned_placement_operation('../escape',digest)
        # Resolve doesn't run _scene_edit_store/current-mutation admission:
        # same operation recovery must reach Tx.start before current checks.
        from unittest.mock import patch
        with patch.object(self.workflow,'_scene_edit_store',side_effect=AssertionError('premature admission')):
            self.assertEqual(self.library.pinned_placement_operation(preview['preview_id'],digest),(operation,digest))
        self.assertFalse(self.workflow._broker.has_pending_operations())

    def test_placement_record_tampering_is_rejected(self):
        asset=mesh(.2);self.library.assets.register(asset.to_dict())
        preview=self.library.action(dict(action='preview_placement',asset_id=asset.logical_asset_id,version=asset.version,
            expected_scene_revision=self.library.snapshot()['current_scene_revision'],instance_id='asset',
            position_m=[-.8,-.9,.1],yaw_deg=0,request_id='tamper'))['placement_preview']
        path=self.library.root/'placement-previews'/(preview['preview_id']+'.json')
        record=json.loads(path.read_text());record['source_sha256']='0'*64
        from twinpulse_app.library_asset_store import atomic_json
        atomic_json(path,record)
        with self.assertRaisesRegex(BrokerError,'CORRUPT'):
            self.library.pinned_placement_operation(preview['preview_id'],preview['preview_digest'])
        record['sha256']=canonical_sha256({k:v for k,v in record.items() if k!='sha256'})
        atomic_json(path,record)
        with self.assertRaisesRegex(BrokerError,'SOURCE_CHANGED'):
            self.library.pinned_placement_operation(preview['preview_id'],preview['preview_digest'])

    def test_catalog_read_no_worker_and_missing_tools_do_not_gate_base(self):
        state=self.library.snapshot();self.assertEqual(state['jobs'],[]);self.assertFalse(self.library.active())
        tools={e['extension_id']:e for e in state['extensions']}
        self.assertFalse(tools['cad_converter']['available']);self.assertFalse(tools['brep']['available'])
        self.assertTrue(tools['csv_local']['available']);self.assertFalse(tools['csv_mcp']['enabled'])
        self.assertEqual(self.workflow._phase,'draft_ready')

    def test_catalog_revision_is_published_hint_without_history_or_admission_lock(self):
        from unittest.mock import patch
        expected=self.workflow._site_artifact.revision
        with patch.object(self.workflow._application,'scene_change_store',
                side_effect=AssertionError('optional catalog must not replay history')):
            self.assertEqual(self.library.snapshot()['current_scene_revision'],expected)
            # Re-entrant Library actions call snapshot while owning this lock.
            with self.library.lock:
                self.assertEqual(self.library.snapshot()['current_scene_revision'],expected)
        self.workflow._site_artifact=None
        self.assertIsNone(self.library.snapshot()['current_scene_revision'])

    def test_catalog_revision_never_authorizes_stale_placement(self):
        asset=mesh(.2);self.library.assets.register(asset.to_dict())
        # A display hint is not a way to bypass durable current-state checks.
        with self.assertRaisesRegex(BrokerError,'REVISION_CHANGED'):
            self.library.action(dict(action='preview_placement',asset_id=asset.logical_asset_id,
                version=asset.version,expected_scene_revision='0'*64,instance_id='stale_asset',
                position_m=[-.8,-.9,.1],yaw_deg=0,request_id='stale_hint'))
        self.assertFalse(self.workflow._broker.has_pending_operations())

    def test_catalog_revision_with_unreviewed_input_or_derived_state_is_unavailable(self):
        original=self.workflow._input
        self.workflow._input=replace(original,revision='0'*64)
        self.assertIsNone(self.library.snapshot()['current_scene_revision'])
        self.workflow._input=original;self.workflow._derived_revision='1'*64
        self.assertIsNone(self.library.snapshot()['current_scene_revision'])

    def test_catalog_revision_rejects_history_published_before_artifact_registration(self):
        original=self.workflow._site_artifact
        self.workflow._site_artifact=replace(original,revision='0'*64)
        self.assertIsNone(self.library.snapshot()['current_scene_revision'])
        self.workflow._site_artifact=original
        self.assertEqual(self.library.snapshot()['current_scene_revision'],original.revision)

    def test_existing_workspace_read_does_not_acquire_workflow_lock(self):
        from twinpulse_app.api import LocalApiServer
        class NoAdmission:
            def __enter__(self):raise AssertionError('cached catalog lookup must not acquire workflow lock')
            def __exit__(self,*args):pass
        server=LocalApiServer.__new__(LocalApiServer);server.product_workflow=self.workflow
        original=self.workflow._lock
        try:
            self.workflow._lock=NoAdmission()
            self.assertIs(server._library_workspace(),self.library)
            self.assertIsNotNone(self.library.snapshot()['current_scene_revision'])
        finally:self.workflow._lock=original


if __name__=='__main__':unittest.main()
