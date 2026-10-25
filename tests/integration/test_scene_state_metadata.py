# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exact metadata across first generation and history replay; no engine or HTTP."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch as mock_patch

from tests.integration.test_dependency_scene_changes import partial_source, edit, preview
from tests.integration.test_scene_changes import room_source, sofa
from tests.integration.test_a2_room_recipe import NoGateway
from tests.integration.test_derived_site_review import derived_fixture
from twinpulse_app import ApplicationService, CommandBroker, ProductWorkflow, ProjectStore
from twinpulse_app.project_store import ProjectRecord
from twinpulse_app.scene_changes import SceneChange, SceneChangeHistory, SceneChangeStore
from twinpulse_app.derived_site_review import DerivedSiteReview
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_core import InputArtifactStore
from twinpulse_provider import SiteGenerationResult
from twinpulse_provider.semantic_scene import compile_scene
from test_progressive_twin import fixture


class SceneStateMetadataTests(unittest.TestCase):
    def test_low_disk_blocks_before_generation_without_erasing_input_or_starting_worker(self):
        from types import SimpleNamespace
        product=self.product(self.root)
        product.select_input(dict(name=None,input_kind='auto',prompt='Retain this requested room',
            media_type=None,content_base64=None,sidecar_name=None,sidecar_content_base64=None))
        before=product.snapshot()
        with mock_patch('twinpulse_app.product_workflow_service.shutil.disk_usage',
                return_value=SimpleNamespace(free=128*1024*1024)):
            with self.assertRaisesRegex(Exception,'Free disk space first'):
                product.start_generation()
        self.assertEqual(product.snapshot()['phase'],before['phase'])
        self.assertEqual(product.snapshot()['input'],before['input'])
        self.assertFalse(product._workers)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.products = []

    def tearDown(self):
        for product in self.products:
            product.shutdown()
        self.temp.cleanup()

    def product(self, root, gateway=None):
        store = ProjectStore.for_project(root, 'default')
        app = ApplicationService(gateway or NoGateway(), project_store=store, project_id='default')
        product = ProductWorkflow(app, CommandBroker(), mode='explicit_fixture',
            generation_settings_getter=lambda: {'model_id': 'offline-state-metadata'})
        self.products.append(product)
        return product

    def saved_product(self, source, root):
        store = ProjectStore.for_project(root, 'default')
        InputArtifactStore(store.input_root()).save(source.input_revision, ())
        store.save(ProjectRecord('default', source.input_revision, site_draft=source))
        product = self.product(root)
        product.resume_saved_scene('default', source.site.scene.revision, source.input_revision.digest)
        return product

    @staticmethod
    def expected(source, history=None):
        history = history or SceneChangeHistory.empty('default', source)
        return history.state_sha256(history.effective(source))

    @staticmethod
    def files(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_new_generation_before_first_edit_reload_and_closed_restore_match(self):
        request, observation, draft = fixture()
        payload, trace = compile_scene(draft, observation, request, progressive=True)
        from twinpulse_core import SiteToolPlan
        plan = SiteToolPlan.from_dict(payload)

        class Gateway(NoGateway):
            async def generate(self, submitted):
                return SiteGenerationResult(submitted.request_id, 'explicit-fixture', 'offline', 0,
                    plan, provider_provenance=deepcopy(trace))

        product = self.product(self.root, Gateway())
        product.select_input(dict(name=None, input_kind='auto', prompt='Synthetic partial generation',
            media_type=None, content_base64=None, sidecar_name=None, sidecar_content_base64=None))
        product.start_generation()
        for worker in tuple(product._workers):
            worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(product.snapshot()['phase'], 'draft_ready')
        source = product._application.site_draft
        self.assertIsNone(product._scene_changes)  # The exact original failing path.
        store = product._application.scene_change_store()
        self.assertFalse(store.path.exists())
        expected = self.expected(source)
        first = product.snapshot()['site_draft']
        self.assertEqual(first['scene_state_sha256'], expected)
        self.assertEqual(first['scene_edit_count'], 0)
        self.assertEqual(first['revision'], source.site.scene.revision)
        original = store.project_store.path.read_bytes()
        product.resume_saved_scene('default', source.site.scene.revision, source.input_revision.digest)
        self.assertEqual(product.snapshot()['site_draft']['scene_state_sha256'], expected)
        product.shutdown()
        reopened = self.product(self.root)
        self.assertEqual(reopened.snapshot()['site_draft']['scene_state_sha256'], expected)
        reopened.resume_saved_scene('default', source.site.scene.revision, source.input_revision.digest)
        self.assertEqual(reopened.snapshot()['site_draft']['scene_state_sha256'], expected)
        self.assertEqual(store.project_store.path.read_bytes(), original)
        self.assertFalse(store.path.exists())
        self.assertFalse(product._broker.has_pending_operations())
        self.assertFalse(reopened._broker.has_pending_operations())

    def test_empty_supported_history_versions_have_stable_exact_metadata(self):
        partial = partial_source()
        sources = [('1.0', room_source()),
                   ('1.1', replace(partial, schema_version='2.1', progressive_twin=None)),
                   ('1.2', partial)]
        for version, source in sources:
            with self.subTest(version=version):
                product = self.saved_product(source, self.root/version)
                self.assertEqual(product._scene_changes.schema_version, 'scene-changes-'+version)
                expected = self.expected(source)
                cached = product.snapshot()['site_draft']
                self.assertEqual(cached['scene_state_sha256'], expected)
                product._scene_changes = None
                uncached = product.snapshot()['site_draft']
                self.assertEqual(uncached['scene_state_sha256'], expected)
                self.assertEqual(uncached['revision'], cached['revision'])
                self.assertEqual(uncached['plan_sha256'], cached['plan_sha256'])
                self.assertEqual(uncached['scene_edit_count'], 0)
                self.assertFalse(product._application.scene_change_store().path.exists())

    def test_legacy_edited_history_hashes_current_plan_not_original(self):
        source = room_source()
        product = self.saved_product(source, self.root)
        store = product._application.scene_change_store()
        value = store.load().preview(source, operation_id='legacy_add', mode='add', tool_call=sofa())
        history = store.apply(value['operation'], value['preview_digest'])
        product._scene_changes = history
        before = store.path.read_bytes()
        metadata = product.snapshot()['site_draft']
        self.assertEqual(metadata['scene_state_sha256'], self.expected(source, history))
        self.assertNotEqual(metadata['scene_state_sha256'], self.expected(source))
        self.assertEqual(metadata['revision'], history.current_scene_revision)
        self.assertEqual(metadata['scene_edit_count'], 1)
        self.assertEqual(store.path.read_bytes(), before)
        self.assertFalse(product._broker.has_pending_operations())

    def test_pending_only_state_changes_are_not_collapsed_to_geometry_sha(self):
        source = partial_source()
        product = self.saved_product(source, self.root)
        base = SceneChangeHistory.empty('default', source)
        results = []
        for reason in ('Retain this missing rigid item for later.', 'Need more evidence for this same retained item.'):
            change = edit('defer', 'item_0')
            change['reason'] = reason
            value = preview(base, source, 'pending', change)
            history = base.append(source, SceneChange.from_dict(value['operation']))
            product._scene_changes = history
            metadata = product.snapshot()['site_draft']
            self.assertEqual(metadata['scene_state_sha256'], self.expected(source, history))
            results.append(metadata)
        self.assertEqual(results[0]['revision'], results[1]['revision'])
        self.assertEqual(results[0]['plan_sha256'], results[1]['plan_sha256'])
        self.assertNotEqual(results[0]['scene_state_sha256'], results[1]['scene_state_sha256'])
        self.assertFalse(product._application.scene_change_store().path.exists())

    def test_snapshot_hashing_is_read_only_without_history_cache_or_sidecar(self):
        product = self.saved_product(partial_source(), self.root)
        product._scene_changes = None
        self.assertTrue(product._application.diagnostics.flush())
        before = self.files(self.root)
        with (mock_patch.object(ProjectStore, 'save', side_effect=AssertionError('metadata must not save')),
              mock_patch.object(SceneChangeStore, 'apply', side_effect=AssertionError('metadata must not edit')),
              mock_patch.object(SceneChangeStore, 'load', side_effect=AssertionError('metadata must not read/create a sidecar')),
              mock_patch.object(CommandBroker, 'submit', side_effect=AssertionError('metadata must not Build'))):
            first = product.snapshot()['site_draft']
            second = product.snapshot()['site_draft']
        self.assertEqual(first, second)
        self.assertIsNone(product._scene_changes)
        self.assertEqual(self.files(self.root), before)
        self.assertFalse(product._broker.has_pending_operations())

    def test_summary_cache_binds_full_content_and_returns_independent_metadata(self):
        source=partial_source();product=self.saved_product(source,self.root)
        product._site_summary_cache=None
        with mock_patch.object(product,'_compute_site_draft_summary',wraps=product._compute_site_draft_summary) as compute:
            first=product.snapshot()['site_draft'];second=product.snapshot()['site_draft']
            self.assertEqual(first,second);self.assertEqual(compute.call_count,1)
            first['objects'].clear();first['progressive_twin']['accepted_count']=-1
            third=product.snapshot()['site_draft']
            self.assertEqual(third,second);self.assertEqual(compute.call_count,1)
            product._acknowledged_identity=('0'*64,'1'*64)
            product.snapshot();self.assertEqual(compute.call_count,1)
            # Same geometry with changed pending reasons is a different state.
            base=product._scene_changes
            change=edit('defer','item_0');change['reason']='Retain this unplaced item for a new reason.'
            value=preview(base,source,'cache_pending',change)
            product._scene_changes=base.append(source,SceneChange.from_dict(value['operation']))
            changed=product.snapshot()['site_draft']
            self.assertEqual(compute.call_count,2)
            self.assertNotEqual(changed['scene_state_sha256'],second['scene_state_sha256'])

    def test_presentation_reuses_current_content_validated_original_revision(self):
        product=self.saved_product(room_source(),self.root)
        expected=product.snapshot()['site_draft']['original_scene_revision']
        store=product._application.presentation_store()
        with mock_patch.object(product._application,'presentation_store',return_value=store), \
             mock_patch.object(store,'load',wraps=store.load) as load:
            result=product.snapshot()
        load.assert_called_once_with(expected)
        self.assertEqual(result['presentation']['source_scene_revision'],expected)
        self.assertFalse(result['presentation']['saved'])

    def test_display_memo_detects_nested_mutation_without_rebuilding_source_dict(self):
        product=self.saved_product(room_source(),self.root)
        product.snapshot()
        original=product._application.site_draft
        original_key=product._site_summary_cache[0]
        # A frozen dataclass can contain mutable JSON containers. The memo
        # must inspect their content, not just the enclosing object's identity.
        coordinates=original.plan.calls[0].arguments['center_m'];before=coordinates[0]
        try:
            coordinates[0]=.1
            with mock_patch.object(product,'_compute_site_draft_summary',side_effect=RuntimeError('content changed')):
                with self.assertRaisesRegex(RuntimeError,'content changed'):
                    product.snapshot()
        finally:
            coordinates[0]=before
        self.assertEqual(product._site_summary_cache[0],original_key)

    def test_cache_hit_fingerprints_content_without_serializing_source_records(self):
        product=self.saved_product(room_source(),self.root)
        expected=product.snapshot()['site_draft']
        with mock_patch.object(SiteDraftRecord,'to_dict',side_effect=AssertionError('large source copy on display hit')), \
             mock_patch.object(SceneChangeHistory,'to_dict',side_effect=AssertionError('large history copy on display hit')):
            actual=product.snapshot()['site_draft']
        self.assertEqual(actual,expected)

    def test_nonprogressive_summary_reuses_one_validated_replay_without_changing_state_sha(self):
        source=room_source();product=self.saved_product(source,self.root)
        history=product._scene_changes
        expected=history.state_sha256(history.effective(source))
        product._site_summary_cache=None
        original=SceneChangeHistory.replay;calls=[]
        def replay_once(current,record):
            calls.append(current)
            return original(current,record)
        with mock_patch.object(SceneChangeHistory,'replay',new=replay_once):
            with product._lock:
                first=product._site_draft_summary(source)
                second=product._site_draft_summary(source)
        self.assertEqual(len(calls),1)
        self.assertEqual(first['scene_state_sha256'],expected)
        self.assertEqual(first,second)

    def test_nohistory_summary_validates_source_once_without_recompiling_an_empty_history(self):
        sources=[room_source(),partial_source()]
        for index,source in enumerate(sources):
            with self.subTest(index=index):
                product=self.saved_product(source,self.root/str(index))
                product._scene_changes=None;product._site_summary_cache=None
                expected=self.expected(source)
                with mock_patch.object(SceneChangeHistory,'effective',side_effect=AssertionError('no edits to replay')), \
                     mock_patch.object(SiteDraftRecord,'from_dict',wraps=SiteDraftRecord.from_dict) as validate:
                    actual=product.snapshot()['site_draft']
                self.assertEqual(validate.call_count,1)
                self.assertEqual(actual['scene_state_sha256'],expected)
                self.assertIsNone(product._scene_changes)

    def test_nohistory_import_summary_keeps_the_exact_digest_without_empty_history_compile(self):
        from tests.integration.test_environment_import import EnvironmentImportTests
        with EnvironmentImportTests().reviewed_workspace() as (_,app,product,source):
            expected=self.expected(source)
            product._scene_changes=None;product._site_summary_cache=None
            with mock_patch.object(SceneChangeHistory,'effective',side_effect=AssertionError('import must not recompile for empty history')):
                result=product.snapshot()['site_draft']
            self.assertEqual(result['scene_state_sha256'],expected)
            self.assertEqual(result['revision'],source.site.scene.revision)

    def test_nohistory_summary_still_rejects_invalid_source_before_publishing(self):
        source=partial_source();product=self.saved_product(source,self.root)
        product._scene_changes=None
        changed_scene=replace(source.site.scene,source='drawing')
        invalid=[replace(source,plan_sha256='0'*64),replace(source,site=replace(source.site,scene=changed_scene)),
                 replace(source,schema_version='bad'),replace(source,placement_contract={'bad':True}),
                 replace(source,progressive_twin={'bad':True}),replace(source,draft_refinement={'bad':True})]
        for value in invalid:
            with self.subTest(field=value):
                product._site_summary_cache=None
                with product._lock,self.assertRaises((ValueError,KeyError,TypeError)):
                    product._site_draft_summary(value)
                self.assertIsNone(product._site_summary_cache)

    def test_summary_cache_captures_engine_capability_once_for_key_and_value(self):
        product=self.saved_product(partial_source(),self.root)
        product._acknowledged_identity=(product._input.revision,product._site_artifact.revision)
        product._site_summary_cache=None
        with mock_patch.object(product._broker,'site_scene_capable',side_effect=[False,True,False]) as capability, \
                mock_patch.object(product,'_compute_site_draft_summary',wraps=product._compute_site_draft_summary) as compute:
            # Use the exact summary entry: outer workflow.snapshot has other
            # independent capability fields unrelated to this cache.
            with product._lock:
                values=[product._site_draft_summary(product._application.site_draft)['build_allowed'] for _ in range(3)]
        self.assertEqual(values,[False,True,False]);self.assertEqual(capability.call_count,3)
        self.assertEqual(compute.call_count,1)
        with mock_patch.object(product._broker,'site_scene_capable',return_value=True), \
                mock_patch.object(product,'_compute_site_draft_summary',side_effect=AssertionError('ACK must not replay geometry')):
            product._acknowledged_identity=('0'*64,'1'*64)
            self.assertFalse(product._site_draft_summary(product._application.site_draft)['build_allowed'])
            product._acknowledged_identity=(product._input.revision,product._site_artifact.revision)
            self.assertTrue(product._site_draft_summary(product._application.site_draft)['build_allowed'])

    def test_summary_cache_uses_the_same_derived_snapshot_for_key_and_result(self):
        from unittest.mock import PropertyMock
        source,archive=derived_fixture();product=self.saved_product(source,self.root)
        derived=DerivedSiteReview.create(source,archive);product._derived_revision=derived.revision
        product._site_summary_cache=None
        with mock_patch.object(ApplicationService,'derived_review',new_callable=PropertyMock,
                side_effect=[derived,None]) as selection:
            with product._lock:
                first=product._site_draft_summary(source);second=product._site_draft_summary(source)
        self.assertEqual(selection.call_count,2)
        self.assertEqual(first['revision'],derived.site.scene.revision)
        self.assertEqual(second['revision'],source.site.scene.revision)
        self.assertNotEqual(first['revision'],second['revision'])

    def test_derived_review_never_claims_common_history_state_sha(self):
        source, archive = derived_fixture()
        product = self.saved_product(source, self.root)
        derived = DerivedSiteReview.create(source, archive)
        app = product._application
        app._derived_selection = (app._epoch, derived)
        product._derived_revision = derived.revision
        before = self.files(self.root)
        metadata = product.snapshot()['site_draft']
        self.assertEqual(metadata['derived_review_revision'], derived.revision)
        self.assertEqual(metadata['revision'], derived.site.scene.revision)
        self.assertIsNone(metadata['scene_state_sha256'])
        self.assertEqual(self.files(self.root), before)
        self.assertFalse(product._broker.has_pending_operations())


if __name__ == '__main__':
    unittest.main()
