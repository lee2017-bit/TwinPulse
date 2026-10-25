# SPDX-License-Identifier: Apache-2.0
"""Supplementary contracts; not installed UI or physical acceptance."""
from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import ast
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from dataclasses import replace
from contextlib import contextmanager
import base64
from unittest.mock import Mock,patch
from types import SimpleNamespace
from threading import RLock

from twinpulse_core import InputRevision,canonical_sha256
from twinpulse_core.environment_source import checked_environment,move_environment
from twinpulse_core.environment_navigation import navigation_cells
from twinpulse_core.scene_tools import SceneToolCall
from twinpulse_core.site_tools import SiteToolPlan
from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.scene_changes import SceneChangeStore
from tests.integration.test_a2_room_recipe import NoGateway


def source():
    def mesh(name,category,points,triangles):
        return dict(id='Env_'+hashlib.sha256(name.encode()).hexdigest()[:20],source_path='/Source/'+name,
            category=category,label=name,points_m=points,triangles=triangles,color_rgb=[.5,.6,.7],translation_m=[0,0,0])
    # L-shaped floor deliberately has an absent upper-right quadrant.
    points=[[0,0,0],[4,0,0],[4,2,0],[2,2,0],[2,4,0],[0,4,0]]
    floor=mesh('Floor0','floor',points,[[0,1,2],[0,2,3],[0,3,5],[3,4,5]])
    chair=mesh('Chair0','chair',[[.5,.5,.1],[.9,.5,.1],[.5,.9,.1]],[[0,1,2]])
    return dict(schema_version='environment-static-1.0',source_name='test.usda',source_sha256=hashlib.sha256(b'test').hexdigest(),
        source_up_axis='Z',source_meters_per_unit=None,meters_per_unit=1.,units_basis='selected_for_sim',
        floor_offset_m=0.,meshes=[floor,chair])


def plan(environment):
    return SiteToolPlan('ImportedSpace','Imported source','Local geometry',
        (SceneToolCall('imported_space','import_environment',dict(id='imported_space',environment=environment)),),plan_version='2.4')


class EnvironmentImportTests(unittest.TestCase):
    @contextmanager
    def reviewed_workspace(self):
        from twinpulse_app.environment_workspace import EnvironmentWorkspace
        with TemporaryDirectory() as directory:
            store=ProjectStore.for_project(Path(directory),'test')
            app=ApplicationService(NoGateway(),project_store=store,project_id='test')
            workflow=ProductWorkflow(app,CommandBroker(project_id='test'),mode='simulation_offline',generation_settings_getter=lambda:{})
            revision=InputRevision.create(prompt='Import SHA '+source()['source_sha256'],images=(),measurement_constraints=(),
                profile_id=workflow._profile_id,generation_settings={'request_schema':'environment-static-1.0'})
            draft=app.import_environment(plan(source()),revision,'import-test',b'test')
            workflow.resume_saved_scene('test',draft.site.scene.revision,revision.digest)
            try:yield EnvironmentWorkspace(workflow),app,workflow,draft
            finally:workflow.shutdown()

    def test_display_reads_published_review_without_disk_or_history_replay(self):
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            with (patch.object(app,'scene_change_store',side_effect=AssertionError('disk on display')),
                    patch.object(type(workflow._scene_changes),'replay',side_effect=AssertionError('replay on display'))):
                state=workspace.snapshot()
            self.assertEqual(state['status'],'imported')
            self.assertEqual(state['metadata_basis'],'current_review_not_disk_validation')
            original=state['objects'][1]['position_m']
            size=state['objects'][1]['dimensions_m']
            self.assertEqual([round(v,4) for v in size],[.4,.4,0.])
            store=app.scene_change_store()
            moved=move_environment(source(),source()['meshes'][1]['id'],[.1,0,0])
            preview=store.load().preview(draft,operation_id='move-test',mode='change',target_call_id='imported_space',
                tool_call=plan(moved).calls[0].to_dict())
            history=store.apply(preview['operation'],preview['preview_digest'])
            workflow._publish_scene_change(store,history)
            state=workspace.snapshot()
            self.assertAlmostEqual(state['objects'][1]['position_m'][0]-original[0],.1)
            for a,b in zip(state['objects'][1]['dimensions_m'],size):self.assertAlmostEqual(a,b)
            self.assertEqual(state['scene_revision'],history.current_scene_revision)

    def test_generic_editor_poll_does_not_copy_imported_meshes_or_change_original(self):
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            original=draft.to_dict()
            for _ in range(3):
                summary=workflow.snapshot()['site_draft']
                self.assertEqual(summary['editable_calls'],[])
                self.assertEqual(workspace.snapshot()['status'],'imported')
            self.assertEqual(draft.to_dict(),original)
            self.assertEqual(len(draft.site.scene.environment['meshes']),2)

    def test_display_mismatch_or_unreviewed_state_cannot_enable_controls(self):
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            saved=(workflow._phase,workflow._derived_revision,workflow._input,workflow._site_artifact,workflow._scene_changes)
            for mismatch in ('phase','derived','input','artifact_source','history_project','history_input','history_revision','no_history'):
                workflow._phase,workflow._derived_revision,workflow._input,workflow._site_artifact,workflow._scene_changes=saved
                if mismatch=='phase':workflow._phase='restore_review_required'
                if mismatch=='derived':workflow._derived_revision='derived'
                if mismatch=='input':workflow._input=SimpleNamespace(revision='different')
                if mismatch=='artifact_source':workflow._site_artifact=replace(saved[3],scene=replace(saved[3].scene,source_ref='b'*64))
                if mismatch=='history_project':workflow._scene_changes=replace(saved[4],project_id='different')
                if mismatch=='history_input':workflow._scene_changes=replace(saved[4],input_revision='b'*64)
                if mismatch=='history_revision':workflow._scene_changes=replace(saved[4],current_scene_revision='b'*64)
                if mismatch=='no_history':workflow._scene_changes=None
                with self.subTest(mismatch=mismatch):
                    state=workspace.snapshot()
                    self.assertEqual(state['status'],'failed');self.assertIsNone(state['scene_revision'])
                    self.assertIsNone(state['metadata_basis'])
            workflow._phase,workflow._derived_revision,workflow._input,workflow._site_artifact,workflow._scene_changes=saved

    def test_build_rechecks_saved_project_archive_and_journal_not_display(self):
        from twinpulse_app.command_broker import BrokerError
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            workspace._validate_saved_build(draft)
            project=app._project_store.path;original=project.read_bytes()
            project.write_text('{}',encoding='utf-8')
            self.assertEqual(workspace.snapshot()['status'],'imported')  # metadata is not a disk-validation claim
            with self.assertRaises(BrokerError):workspace._validate_saved_build(draft)
            project.write_bytes(original)
            archive=app._artifact_store.root/draft.input_revision.digest/'environment-source.bin'
            archive.write_bytes(b'changed')
            with self.assertRaises(BrokerError):workspace._validate_saved_build(draft)
            archive.write_bytes(b'test')
            store=app.scene_change_store()
            moved=move_environment(source(),source()['meshes'][1]['id'],[.1,0,0])
            preview=store.load().preview(draft,operation_id='external-edit',mode='change',target_call_id='imported_space',
                tool_call=plan(moved).calls[0].to_dict())
            history=store.apply(preview['operation'],preview['preview_digest'])
            with self.assertRaises(BrokerError):workspace._validate_saved_build(draft)
            workflow._publish_scene_change(store,history)
            workspace._validate_saved_build(draft)

    def test_duplicate_inspect_releases_environment_lock_before_snapshot(self):
        with self.reviewed_workspace() as (workspace,app,workflow,draft):
            workspace.job={'request_id':'duplicate'}
            workspace.snapshot=lambda: self.assertFalse(workspace.lock._is_owned())
            workspace.action(dict(action='inspect',request_id='duplicate',units='m',
                attachment=dict(name='test.usda',bytes_base64=base64.b64encode(b'test').decode())),'owner')

    def test_packaged_inspection_does_not_create_bytecode_beside_sources(self):
        # Real fresh interpreter and real peer import, without Kit or a model
        # response fixture. Even a standalone --help must leave sources intact.
        scripts=Path(__file__).resolve().parents[2]/'scripts'
        with TemporaryDirectory() as directory:
            folder=Path(directory)
            for name in ('twinpulse_environment_worker.py','twinpulse_library_worker.py'):
                shutil.copy2(scripts/name,folder/name)
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.py')}
            env=dict(os.environ);env.pop('PYTHONDONTWRITEBYTECODE',None);env.pop('PYTHONPYCACHEPREFIX',None)
            for flags in ([],['-B']):
                completed=subprocess.run([sys.executable,*flags,str(folder/'twinpulse_environment_worker.py'),'--help'],
                    env=env,capture_output=True,text=True,timeout=15)
                self.assertEqual(completed.returncode,0,completed.stderr)
                self.assertFalse((folder/'__pycache__').exists())
                self.assertEqual(list(folder.rglob('*.pyc')),[])
                self.assertEqual({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.py')},before)

    def test_tick_object_identity_never_serializes_whole_environment_and_stays_exact(self):
        # Extract the pure method without importing Kit into unit-test Python.
        adapter=Path(__file__).resolve().parents[2]/'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py'
        tree=ast.parse(adapter.read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='IsaacSimulationAdapter')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='mission_objects_revision')
        namespace=dict(canonical_sha256=canonical_sha256,asdict=asdict)
        exec(compile(ast.Module(body=[method],type_ignores=[]),str(adapter),'exec'),namespace)
        from twinpulse_core import execute_site_tool_plan
        scene=execute_site_tool_plan(plan(source()),source='scan',source_ref='a'*64).scene
        expected=canonical_sha256(scene.to_dict()['objects'])
        owner=SimpleNamespace(runtime=SimpleNamespace(compiler=SimpleNamespace(site_scene=scene)))
        with patch.object(type(scene),'to_dict',side_effect=AssertionError('whole-scene serialization on tick')):
            self.assertEqual(namespace['mission_objects_revision'](owner),expected)
        moved=execute_site_tool_plan(plan(move_environment(source(),source()['meshes'][1]['id'],[.1,0,0])),source='scan',source_ref='a'*64).scene
        owner.runtime.compiler.site_scene=moved
        self.assertNotEqual(namespace['mission_objects_revision'](owner),expected)

    def test_build_waits_for_owned_lease_permission_and_does_not_bypass_failure(self):
        from twinpulse_app.environment_workspace import EnvironmentWorkspace
        from twinpulse_app.command_broker import BrokerError
        broker=Mock()
        broker.has_pending_operations.return_value=False
        broker.supervisor_state.return_value=dict(engine_connected=True,engine_session_id='engine',stage_epoch='stage')
        broker.acquire_lease.return_value={'control_lease_id':'test-lease'}
        broker.site_scene_capable.side_effect=[False,True]
        broker.submit.return_value={'command_id':'test-command'}
        workflow=SimpleNamespace(_lock=RLock(),_workers=[],_phase='draft_ready',_broker=broker,
            _application=SimpleNamespace(site_draft=SimpleNamespace(site=SimpleNamespace(scene=SimpleNamespace(environment=source())))),
            _site_artifact=SimpleNamespace(revision='revision',artifact_id='artifact'),acknowledge=Mock(),
            assert_site_build_allowed=Mock(),snapshot=Mock(return_value={}))
        workspace=object.__new__(EnvironmentWorkspace);workspace.workflow=workflow;workspace.snapshot=lambda **kw:kw
        workspace._validate_saved_build=Mock()
        # Slow full validation/acknowledgement must not consume a control
        # lease; this is a fake-clock sequencing regression, not SDK evidence.
        elapsed=[0.]
        def validate_before_lease(*args):
            self.assertEqual(broker.acquire_lease.call_count,0)
            elapsed[0]+=4.
        workspace._validate_saved_build.side_effect=validate_before_lease
        workflow.acknowledge.side_effect=lambda *args: self.assertEqual(workspace._validate_saved_build.call_count,1)
        workflow.assert_site_build_allowed.side_effect=lambda *args: self.assertEqual(broker.acquire_lease.call_count,1)
        with patch('twinpulse_app.environment_workspace.time.sleep'):
            workspace.action({'action':'build','request_id':'build-test'},'owner')
        broker.renew_lease.assert_called_once_with('owner','test-lease')
        broker.submit.assert_called_once()
        self.assertEqual(elapsed[0],4.)
        # Never turn an expired/changed permission into an unconditional submit.
        broker.reset_mock();broker.site_scene_capable.side_effect=None;broker.site_scene_capable.return_value=False
        workspace._validate_saved_build.reset_mock();workflow.acknowledge.reset_mock()
        with patch('twinpulse_app.environment_workspace.time.monotonic',side_effect=[0,7]):
            with self.assertRaises(BrokerError):workspace.action({'action':'build','request_id':'build-timeout'},'owner')
        broker.submit.assert_not_called()
        broker.reset_mock();workspace._validate_saved_build.reset_mock();workflow.acknowledge.reset_mock()
        workspace._validate_saved_build.side_effect=BrokerError('environment_saved_review_changed','Changed saved review',status=409)
        with self.assertRaises(BrokerError):workspace.action({'action':'build','request_id':'build-tampered'},'owner')
        broker.acquire_lease.assert_not_called();broker.submit.assert_not_called();workflow.acknowledge.assert_not_called()
        workspace._validate_saved_build.reset_mock();workspace._validate_saved_build.side_effect=validate_before_lease
        broker.supervisor_state.side_effect=[
            dict(engine_connected=True,engine_session_id='engine',stage_epoch='stage'),
            dict(engine_connected=True,engine_session_id='engine',stage_epoch='changed')]
        with self.assertRaises(BrokerError) as changed:
            workspace.action({'action':'build','request_id':'build-engine-changed'},'owner')
        self.assertEqual(changed.exception.code,'environment_engine_changed')
        broker.submit.assert_not_called()

    def test_source_units_and_topology_are_checked(self):
        value=source();checked_environment(value)
        for change in ('units','indices','nan','path','floor'):
            bad=deepcopy(value)
            if change=='units':bad['units_basis']='authored'
            if change=='indices':bad['meshes'][0]['triangles'][0][0]=100
            if change=='nan':bad['meshes'][0]['points_m'][0][0]=float('nan')
            if change=='path':bad['source_name']='../test.usda'
            if change=='floor':bad['meshes'][0]['category']='wall'
            with self.subTest(change=change),self.assertRaises(ValueError):checked_environment(bad)

    def test_real_floor_mask_does_not_fill_concave_hole_and_has_manual_boundary(self):
        geometry=navigation_cells(source()['meshes'])
        states={(round(c[0],2),round(c[1],2)):c[2] for c in geometry['cells']}
        self.assertEqual(states[(3.05,3.05)],'occupied')
        self.assertEqual(states[(1.55,3.05)],'free')
        self.assertEqual(states[(.55,.55)],'occupied')
        self.assertEqual(len(geometry['targets']),1)
        self.assertTrue(any(b[0]<-10 for b in geometry['manual_boxes']))

    def test_saved_import_edit_undo_and_cold_replay_preserve_other_geometry(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);store=ProjectStore.for_project(root,'test')
            app=ApplicationService(NoGateway(),project_store=store,project_id='test')
            broker=CommandBroker(project_id='test')
            workflow=ProductWorkflow(app,broker,mode='simulation_offline',generation_settings_getter=lambda:{})
            rev=InputRevision.create(prompt='Import SHA '+source()['source_sha256'],images=(),measurement_constraints=(),
                profile_id=workflow._profile_id,generation_settings={'request_schema':'environment-static-1.0'})
            draft=app.import_environment(plan(source()),rev,'import-test',b'test')
            from twinpulse_core.site_simulation import make_plan,geometry
            with self.assertRaisesRegex(ValueError,'IMPORTED_SPACE_USE_FLEET_SIM_CONTROLS'):
                make_plan(draft.site.scene,[1,1],[1,2],{})
            with self.assertRaisesRegex(ValueError,'IMPORTED_SPACE_USE_FLEET_SIM_CONTROLS'):
                geometry(draft.site.scene)
            self.assertEqual(SiteDraftRecord.from_dict(draft.to_dict()),draft)
            state=workflow.resume_saved_scene('test',draft.site.scene.revision,rev.digest)
            self.assertEqual(state['site_draft']['object_count'],2)
            history=app.scene_change_store().load();env=move_environment(source(),source()['meshes'][1]['id'],[.1,0,0])
            call=plan(env).calls[0].to_dict()
            from twinpulse_app.environment_workspace import EnvironmentWorkspace
            workspace=EnvironmentWorkspace(workflow)
            preview=workspace.action(dict(action='move_preview',request_id='00000000-0000-4000-8000-000000000001',
                object_id=source()['meshes'][1]['id'],translation_m=[.1,0,0],expected_scene_revision=draft.site.scene.revision),'test-owner')['preview']
            self.assertTrue(preview['operation']['operation_id'].startswith('environment_edit_'))
            identity=preview['operation']['operation_id'];digest=preview['preview_digest']
            exact,pinned_digest=workspace.pinned_environment_operation(identity,digest,'test-owner')
            self.assertEqual(canonical_sha256(exact),pinned_digest)
            # Wrong owner/digest cannot resolve another review. No rounding or
            # global canonical-hash policy change is used to accept JS numbers.
            from twinpulse_app.command_broker import BrokerError
            for owner,sha in [('other-owner',digest),('test-owner','0'*64)]:
                with self.assertRaises(BrokerError):workspace.pinned_environment_operation(identity,sha,owner)
            updated=app.scene_change_store().apply(preview['operation'],preview['preview_digest'])
            self.assertEqual(len(preview['affected_after']),1)
            self.assertEqual(preview['preserved_object_count'],1)
            undo=updated.preview(draft,operation_id='undo-test',mode='undo')
            restored=app.scene_change_store().apply(undo['operation'],undo['preview_digest'])
            _,site=restored.replay(draft)
            self.assertEqual(site.scene.environment,source())
            self.assertEqual(restored.schema_version,'scene-changes-1.1')
            with self.assertRaises(ValueError):restored.preview(draft,operation_id='undo-empty',mode='undo')
            # Two moves followed by two Undo must exhaust the active stack,
            # never reapply a movement that was already cancelled.
            current=restored
            for index in range(2):
                active_plan,active_site=current.replay(draft)
                moved=move_environment(active_site.scene.environment,source()['meshes'][1]['id'],[.1,0,0])
                edit=current.preview(draft,operation_id='move-again-'+str(index),mode='change',
                    target_call_id='imported_space',tool_call=plan(moved).calls[0].to_dict())
                current=app.scene_change_store().apply(edit['operation'],edit['preview_digest'])
            for index in range(2):
                undo=current.preview(draft,operation_id='undo-again-'+str(index),mode='undo')
                current=app.scene_change_store().apply(undo['operation'],undo['preview_digest'])
            _,site=current.replay(draft)
            self.assertEqual(site.scene.environment,source())
            with self.assertRaises(ValueError):current.preview(draft,operation_id='undo-exhausted',mode='undo')
            cold=ApplicationService(NoGateway(),project_store=ProjectStore.for_project(root,'test'),project_id='test')
            self.assertEqual(cold.scene_change_store().load().current_scene_revision,site.scene.revision)
            self.assertEqual(cold.restored_saved_input().revision,rev)
            expected=current.state_sha256(current.effective(draft))
            workflow._scene_changes=current;workflow._site_summary_cache=None
            original=type(current).replay;calls=[]
            def counted(owner,record):
                calls.append(owner)
                return original(owner,record)
            with patch.object(type(current),'replay',new=counted):
                with workflow._lock:
                    metadata=workflow._site_draft_summary(draft)
                    cached=workflow._site_draft_summary(draft)
            self.assertEqual(len(calls),1)
            self.assertEqual(metadata['scene_state_sha256'],expected)
            self.assertEqual(metadata,cached)
            workflow.shutdown()

    def test_structural_edit_and_geometry_replacement_cannot_pass_as_move(self):
        value=source()
        with self.assertRaises(ValueError):move_environment(value,value['meshes'][0]['id'],[.1,0,0])
        from twinpulse_core.environment_source import checked_environment_change
        bad=move_environment(value,value['meshes'][1]['id'],[.1,0,0]);bad['meshes'][0]['points_m'][0][0]=.1
        with self.assertRaises(ValueError):checked_environment_change(value,bad)


if __name__=='__main__':unittest.main()
