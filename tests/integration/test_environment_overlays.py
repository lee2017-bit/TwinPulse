# SPDX-License-Identifier: Apache-2.0
"""Supplementary hybrid-scene tests; not hardware or installed UI acceptance."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import sys

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_core.environment_source import checked_environment,checked_environment_change,environment_objects,move_environment
from twinpulse_core.environment_overlays import add_overlay,remove_overlay,overlay_meshes
from twinpulse_core.environment_navigation import navigation_cells
from twinpulse_core import canonical_sha256,SimulationSnapshot
from twinpulse_app.scene_changes import SceneChangeStore
from twinpulse_app.release_contract import DATA_CONTRACT,check_data_epoch,require_data_capability
from tests.integration import test_environment_import as imported
source=imported.source
plan=imported.plan


def overlay(kind='basket',xy=(1.3,1.3),identity='Added_'+'a'*20):
    size=[.35,.3,.4] if kind!='cable_bundle' else [.3,.2,.04]
    return dict(item=dict(id=identity,kind=kind,label=kind,catalog_version='room-items-1.0',
        position_m=[*xy,size[2]/2],dimensions_m=size,yaw_deg=0.,observation_time_utc=None),
        uncertainty_m=.2,evidence=dict(basis='manual_estimate',source_name=None,sha256=None,alignment_verified=False))


class EnvironmentOverlayTests(unittest.TestCase):
    reviewed_workspace=imported.EnvironmentImportTests.reviewed_workspace

    def add_body(self,revision,**extra):
        o=overlay();item=o['item']
        return dict(action='add_overlay_preview',request_id='new-obstacle',expected_scene_revision=revision,photo=None,
            obstacle=dict(kind=item['kind'],label=item['label'],position_xy_m=item['position_m'][:2],
                dimensions_m=item['dimensions_m'],yaw_deg=0.,uncertainty_m=.2),**extra)

    def test_add_move_remove_preserve_original_source_and_meshes(self):
        original=source();digest=canonical_sha256(original);mixed=add_overlay(original,overlay('floor_fan'))
        self.assertEqual(mixed['meshes'],original['meshes']);self.assertEqual(canonical_sha256(original),digest)
        self.assertEqual(mixed['source_sha256'],original['source_sha256'])
        self.assertEqual(len(environment_objects(mixed)),6)
        self.assertEqual(len(checked_environment_change(original,mixed)),4)
        moved=move_environment(mixed,overlay()['item']['id'],[.1,0,0])
        self.assertAlmostEqual(moved['overlays'][0]['item']['position_m'][0],1.4)
        self.assertEqual(remove_overlay(moved,overlay()['item']['id'])['overlays'],[])

    def test_footprint_rejects_hole_edge_and_rotated_outside_not_room_aabb(self):
        for xy in ((3,3),(.1,.1),(2,2)):
            with self.subTest(xy=xy),self.assertRaisesRegex(ValueError,'OUTSIDE_FLOOR'):
                add_overlay(source(),overlay(xy=xy))
        value=overlay();value['item']['yaw_deg']=45.;add_overlay(source(),value)

    def test_changed_source_evidence_size_and_multiple_changes_are_rejected(self):
        mixed=add_overlay(source(),overlay())
        for field in ('size','evidence','mesh','two'):
            bad=move_environment(mixed,overlay()['item']['id'],[.1,0,0])
            if field=='size':bad['overlays'][0]['item']['dimensions_m'][0]+=.1
            if field=='evidence':bad['overlays'][0]['evidence']['source_name']='not-valid'
            if field=='mesh':bad['meshes'][0]['points_m'][0][0]+=.01
            if field=='two':bad['meshes'][1]['translation_m'][0]=.1
            with self.subTest(field=field),self.assertRaises(ValueError):checked_environment_change(mixed,bad)

    def test_estimate_cannot_claim_measured_alignment_or_invalid_numeric(self):
        for field in ('aligned','nan','bool','zero','too_large','elevated','duplicate'):
            value=overlay()
            if field=='aligned':value['evidence']['alignment_verified']=True
            if field=='nan':value['uncertainty_m']=float('nan')
            if field=='bool':value['uncertainty_m']=True
            if field=='zero':value['uncertainty_m']=0
            if field=='too_large':value['item']['dimensions_m'][0]=4
            if field=='elevated':value['item']['position_m'][2]=1
            with self.subTest(field=field),self.assertRaises(ValueError):
                mixed=add_overlay(source(),value)
                if field=='duplicate':add_overlay(mixed,value)

    def test_overlapping_floor_cannot_cancel_a_hole_in_coverage(self):
        from twinpulse_core.environment_overlays import checked_overlay_floor
        value=source();floor=value['meshes'][0]
        # Whole footprint is 1 m², only its left half exists twice.
        floor['points_m']=[[0,0,0],[.5,0,0],[.5,1,0],[0,1,0]]
        floor['triangles']=[[0,1,2],[0,2,3],[0,1,2],[0,2,3]]
        item=overlay(xy=(.5,.5));item['item']['dimensions_m']=[.6,.6,.4]
        with self.assertRaisesRegex(ValueError,'FLOOR_AMBIGUOUS'):checked_overlay_floor(item,[floor])
        # Equivalent witness inside one .1 m navigation cell.
        floor['points_m']=[[0,0,0],[.05,0,0],[.05,.1,0],[0,.1,0]]
        nav=navigation_cells([floor]);cells={(round(x,2),round(y,2)):s for x,y,s,*_ in nav['cells']}
        self.assertEqual(cells[(.05,.05)],'occupied')

    def test_low_cable_and_box_uncertainty_fill_navigation_interior(self):
        for kind in ('basket','cable_bundle'):
            mixed=add_overlay(source(),overlay(kind));derived=overlay_meshes(mixed)
            geometry=navigation_cells(mixed['meshes']+derived)
            cells={(round(x,2),round(y,2)):state for x,y,state,*_ in geometry['cells']}
            self.assertEqual(cells[(1.35,1.35)],'occupied')
            self.assertEqual(cells[(1.55,1.35)],'occupied')
            self.assertEqual(cells[(3.05,3.05)],'occupied')
            self.assertEqual(cells[(1.05,3.05)],'free')
            self.assertTrue(any(m['synthetic_keepout'] for m in derived))
            self.assertTrue(any(not m['synthetic_keepout'] for m in derived))

    def test_existing_grid_planner_routes_around_added_uncertainty(self):
        from twinpulse_core.bounded_grid_plan import plan_bounded_grid
        value=source();value['meshes']=value['meshes'][:1]
        mixed=add_overlay(value,overlay(xy=(2.,1.)))
        geometry=navigation_cells(mixed['meshes']+overlay_meshes(mixed));a,b,c,d=geometry['bounds']
        route=plan_bounded_grid([.7,1.],[3.3,1.],(a,c,b,d),[],[],resolution=.1,clearance=.25,observed_cells=geometry['cells'])
        self.assertTrue(any(abs(p[1]-1.)>.4 for p in route))
        self.assertEqual(tuple(route[-1]),(3.3,1.))

    def test_workspace_add_preview_owner_and_stale_revision(self):
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            body=self.add_body(draft.site.scene.revision)
            result=workspace.action(body,'owner');preview=result['preview']
            self.assertEqual(len(preview['affected_after']),2)
            self.assertEqual(preview['preserved_object_count'],2)
            self.assertFalse(app.scene_change_store().path.exists())
            workspace.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner')
            with self.assertRaises(Exception):workspace.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'other')
            body['expected_scene_revision']='0'*64
            with self.assertRaisesRegex(ValueError,'SCENE_CHANGED'):workspace.action(body,'owner')

    def test_local_photo_original_hash_checked_again_at_commit(self):
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(10,10),(1,2,3)).save(stream,format='PNG');raw=stream.getvalue()
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            body=self.add_body(draft.site.scene.revision)
            body['photo']=dict(name='reference.png',bytes_base64=base64.b64encode(raw).decode())
            result=workspace.action(body,'owner');preview=result['preview']
            o=preview['operation']['tool_call']['arguments']['environment']['overlays'][0]
            self.assertEqual(o['evidence']['sha256'],hashlib.sha256(raw).hexdigest())
            stored=workspace.root/'overlay-photos'/o['evidence']['sha256']/'source.image'
            self.assertEqual(stored.read_bytes(),raw)
            stored.write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError,'PHOTO_CHANGED'):
                app.scene_change_store().apply(preview['operation'],preview['preview_digest'])
            self.assertFalse(app.scene_change_store().path.exists())

    def test_saved_history_cold_replay_undo_retains_barrier_and_original(self):
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            original=app._project_store.path.read_bytes();store=app.scene_change_store()
            preview=workspace.action(self.add_body(draft.site.scene.revision),'owner')['preview']
            history=store.apply(preview['operation'],preview['preview_digest'])
            _,site=history.replay(draft);identity=site.scene.environment['overlays'][0]['item']['id']
            workflow._publish_scene_change(store,history)
            self.assertTrue(workspace.snapshot()['objects'][-1]['added'])
            moved=move_environment(site.scene.environment,identity,[.1,0,0])
            edit=history.preview(draft,operation_id='move-added',mode='change',target_call_id='imported_space',tool_call=plan(moved).calls[0].to_dict())
            history=store.apply(edit['operation'],edit['preview_digest'])
            _,site=history.replay(draft)
            removed=remove_overlay(site.scene.environment,identity)
            edit=history.preview(draft,operation_id='remove-added',mode='change',target_call_id='imported_space',tool_call=plan(removed).calls[0].to_dict())
            history=store.apply(edit['operation'],edit['preview_digest'])
            self.assertFalse(history.replay(draft)[1].scene.environment['overlays'])
            undo=history.preview(draft,operation_id='undo-remove',mode='undo');history=store.apply(undo['operation'],undo['preview_digest'])
            self.assertEqual(len(history.replay(draft)[1].scene.environment['overlays']),1)
            cold=SceneChangeStore(store.path,project_id=store.project_id,source=draft,project_store=app._project_store)
            self.assertEqual(cold.load(),history)
            self.assertEqual(app._project_store.path.read_bytes(),original)
            state=app._project_store.path.parent.parent.parent
            self.assertEqual(check_data_epoch(state),1)
            marker=json.loads((state/'data-compatibility.json').read_text())
            self.assertEqual(marker['required_capabilities'],['environment-static-1.1'])

    def test_compatibility_gate_rejects_old_package_and_keeps_marker_sticky(self):
        with TemporaryDirectory() as directory:
            state=Path(directory);require_data_capability(state,'environment-static-1.1')
            self.assertEqual(check_data_epoch(state),1)
            old={k:v for k,v in DATA_CONTRACT.items() if k!='read_capabilities'}
            with self.assertRaisesRegex(ValueError,'CAPABILITY'):check_data_epoch(state,old)
            marker=(state/'data-compatibility.json').read_bytes()
            require_data_capability(state,'environment-static-1.1')
            self.assertEqual((state/'data-compatibility.json').read_bytes(),marker)

    def test_marker_failure_precedes_transaction_staging_and_dispatch(self):
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            broker=workflow._broker;broker.register_engine('engine','stage');broker.acquire_lease('owner')
            broker.record_snapshot(SimulationSnapshot(engine_session_id='engine',stage_epoch='stage',project_id='test',
                applied_revision=workflow._site_artifact.revision,run_id=None,sequence=1,runtime_state='built',safety_state=None,
                safety_reason=None,permitted_commands=('build_site_scene','get_state'),capabilities=('simulation','site_scene_build_v2')))
            preview=workspace.action(self.add_body(draft.site.scene.revision),'owner')['preview']
            transaction=workflow.scene_edit_transaction
            with patch('twinpulse_app.release_contract.atomic_json',side_effect=OSError('marker failed')):
                with self.assertRaisesRegex(OSError,'marker failed'):
                    transaction.start('owner',preview['operation'],preview['preview_digest'])
            self.assertIsNone(transaction.value);self.assertFalse(transaction.path.exists());self.assertFalse(broker.has_pending_operations())
