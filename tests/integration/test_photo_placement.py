# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Photo library relationships persist and follow reviewed atomic edits offline."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_provider/tests'))
from test_photo_parametric import intent, object_intent, compile
from twinpulse_core import SiteToolPlan, canonical_sha256
from twinpulse_core.photo_placement import (placement_contract_from_trace, validate_placement_plan,
    checked_placement_contract)
from twinpulse_core.photo_quality import support_geometry
from twinpulse_app.application import ApplicationService
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.scene_changes import SceneChange, SceneChangeHistory, SceneChangeStore


def source():
    value=intent(object_intent('desk','desk','rear_left',size=[1.2,.6,.85]),
        object_intent('monitor','monitor',parent='desk',part='top',relation='surface',size=[.3,.12,.25]),
        object_intent('bed','bed','middle_right',size=[1.1,2.,.9]),
        object_intent('blanket','bedding_overhang',parent='bed',part='mattress',relation='drape',anchor='left'))
    payload,trace=compile(value)
    prepared=ApplicationService.prepare_input(prompt='Estimated library fixture',images=(),
        measurement_constraints=(),generation_settings={'model_id':'offline'})
    return SiteDraftRecord.create(request_id='fixture',provider_name='fixture',model_id='fixture',image_count=0,
        input_revision=prepared.revision,plan=SiteToolPlan.from_dict(payload),
        placement_contract=placement_contract_from_trace(trace))


class PhotoPlacementTests(unittest.TestCase):
    def test_new_grounded_trace_keeps_legacy_relationship_sidecar_immutable(self):
        _,trace=compile(intent(object_intent('desk','desk'),object_intent('monitor','monitor',
            parent='desk',part='top',relation='surface')))
        old=placement_contract_from_trace(trace);before=deepcopy(trace)
        current=deepcopy(trace);current['contract']='photo-layout-1.3'
        self.assertEqual(placement_contract_from_trace(current),old)
        self.assertEqual(trace,before)
        self.assertEqual(checked_placement_contract(old),old)

    def test_stack_undo_reverts_two_edits_and_survives_reopen_without_rewriting_legacy(self):
        record=source();history=SceneChangeHistory.empty('fixture',record)
        self.assertEqual(history.schema_version,'scene-changes-1.1')
        history,_=self.edit(record,history,'desk',yaw_deg=90)
        history,_=self.edit(record,history,'bed',center_m=[1.5,0],yaw_deg=90)
        for index in range(2):
            preview=history.preview(record,operation_id='stack_undo_'+str(index),mode='undo')
            history=history.append(record,SceneChange.from_dict(preview['operation']))
            history=SceneChangeHistory.from_dict(history.to_dict(),record,'fixture')
        self.assertEqual(history.replay(record)[0].to_dict(),record.plan.to_dict())
        with self.assertRaisesRegex(ValueError,'no active scene edit'):
            history.preview(record,operation_id='empty_undo',mode='undo')
        # Explicit old history keeps its old toggle semantics and wire/hash.
        legacy=replace(SceneChangeHistory.empty('fixture',record),schema_version='scene-changes-1.0')
        legacy,_=self.edit(record,legacy,'desk',yaw_deg=90)
        edited=legacy.replay(record)[0].to_dict()
        for index in range(2):
            preview=legacy.preview(record,operation_id='legacy_undo_'+str(index),mode='undo')
            legacy=legacy.append(record,SceneChange.from_dict(preview['operation']))
        wire=deepcopy(legacy.to_dict())
        restored=SceneChangeHistory.from_dict(wire,record,'fixture')
        self.assertEqual(restored.to_dict(),wire)
        self.assertEqual(restored.replay(record)[0].to_dict(),edited)

    def test_stack_undo_then_new_edit_discards_only_new_branch(self):
        record=source();history=SceneChangeHistory.empty('fixture',record)
        history,_=self.edit(record,history,'desk',yaw_deg=90)
        first=history.replay(record)[0].to_dict()
        history,_=self.edit(record,history,'bed',center_m=[1.5,0],yaw_deg=90)
        preview=history.preview(record,operation_id='undo_bed_branch',mode='undo')
        history=history.append(record,SceneChange.from_dict(preview['operation']))
        history,_=self.edit(record,history,'bed',center_m=[1.5,0],yaw_deg=-90)
        preview=history.preview(record,operation_id='undo_new_branch',mode='undo')
        history=history.append(record,SceneChange.from_dict(preview['operation']))
        self.assertEqual(history.replay(record)[0].to_dict(),first)

    def edit(self,record,history,identity,**changes):
        plan,_=history.replay(record);call=next(c for c in plan.calls if c.arguments['id']==identity)
        tool=call.to_dict();tool['arguments']=dict(call.arguments,**changes)
        preview=history.preview(record,operation_id='change_'+str(len(history.operations)),mode='change',
            target_call_id=call.call_id,tool_call=tool)
        return history.append(record,SceneChange.from_dict(preview['operation'])),preview

    def test_replay_compiles_each_operation_once_including_undo(self):
        from twinpulse_app import scene_changes
        record=source();history=SceneChangeHistory.empty('fixture',record)
        history,_=self.edit(record,history,'desk',yaw_deg=90)
        undo=history.preview(record,operation_id='undo_cost',mode='undo')
        history=history.append(record,SceneChange.from_dict(undo['operation']))
        original=deepcopy(history.to_dict())
        with patch.object(scene_changes,'_scene_from_plan',wraps=scene_changes._scene_from_plan) as compile_scene:
            plan,site=history.replay(record)
        self.assertEqual(compile_scene.call_count,len(history.operations))
        self.assertEqual(plan.to_dict(),record.plan.to_dict())
        self.assertEqual(history.to_dict(),original)
        self.assertEqual(site.scene.revision,history.current_scene_revision)

    def test_new_source_roundtrip_preserves_explicit_relationships_and_old_shape(self):
        record=source();before=deepcopy(record.to_dict())
        self.assertEqual(record.schema_version,'2.1');self.assertEqual(len(record.placement_contract['relations']),4)
        restored=SiteDraftRecord.from_dict(before);self.assertEqual(restored.to_dict(),before)
        self.assertEqual(restored.plan_sha256,record.plan_sha256)
        legacy=SiteDraftRecord.create(request_id='legacy',provider_name='fixture',model_id='fixture',image_count=0,
            input_revision=record.input_revision,plan=record.plan)
        self.assertEqual(legacy.schema_version,'2.0');self.assertNotIn('placement_contract',legacy.to_dict())
        self.assertEqual(SiteDraftRecord.from_dict(legacy.to_dict()).to_dict(),legacy.to_dict())

    def test_parent_translation_rotation_resize_moves_children_atomically_and_undo(self):
        record=source();before=deepcopy(record.to_dict());history=SceneChangeHistory.empty('fixture',record)
        history,preview=self.edit(record,history,'desk',center_m=[-1.8,1.7],yaw_deg=90,dimensions_m=[1.4,.7,.95])
        plan,_=history.replay(record);args={c.arguments['id']:c.arguments for c in plan.calls}
        self.assertEqual(support_geometry(args['monitor'],args['desk'],'top')['status'],'PASS')
        self.assertEqual(args['monitor']['yaw_deg'],90)
        self.assertIn('monitor_visual_0',preview['affected_after']);self.assertNotIn('bed_base',preview['affected_after'])
        validate_placement_plan(plan,record.placement_contract)
        undo=history.preview(record,operation_id='undo',mode='undo')
        history=history.append(record,SceneChange.from_dict(undo['operation']))
        self.assertEqual(history.replay(record)[0].to_dict(),record.plan.to_dict())
        self.assertEqual(record.to_dict(),before)

    def test_bedding_and_floor_keepout_move_with_rotated_bed(self):
        record=source();history=SceneChangeHistory.empty('fixture',record)
        history,preview=self.edit(record,history,'bed',center_m=[1.5,0],yaw_deg=90,dimensions_m=[1.3,2.2,1.])
        plan,site=history.replay(record);validate_placement_plan(plan,record.placement_contract)
        self.assertIn('blanket_keepout',preview['affected_after'])
        keep=next(o for o in site.scene.objects if o.id=='blanket_keepout');self.assertTrue(keep.collision)
        self.assertAlmostEqual(keep.transform.position_m[0],1.5)
        self.assertEqual(next(c for c in plan.calls if c.arguments['id']=='blanket').arguments['yaw_deg'],90)

    def test_multiple_parent_edits_then_undo_replays_attached_intermediate_plan(self):
        record=source();history=SceneChangeHistory.empty('fixture',record)
        history,_=self.edit(record,history,'desk',center_m=[-1.5,1.8],yaw_deg=90)
        first=history.replay(record)[0].to_dict()
        history,_=self.edit(record,history,'bed',center_m=[1.5,0],yaw_deg=90)
        undo=history.preview(record,operation_id='undo_second',mode='undo')
        history=history.append(record,SceneChange.from_dict(undo['operation']))
        restored=SceneChangeHistory.from_dict(history.to_dict(),record,'fixture')
        self.assertEqual(restored.replay(record)[0].to_dict(),first)

    def test_source_and_history_disk_reopen_replays_parent_children_without_new_generation(self):
        record=source();history=SceneChangeHistory.empty('fixture',record)
        history,_=self.edit(record,history,'desk',center_m=[-1.5,1.8],yaw_deg=90)
        with TemporaryDirectory() as directory:
            store=SceneChangeStore(Path(directory)/'edits.json',project_id='fixture',source=record)
            operation=history.operations[0]
            store.apply(operation.to_dict(),canonical_sha256(operation.to_dict()))
            restored=SiteDraftRecord.from_dict(record.to_dict())
            loaded=SceneChangeStore(store.path,project_id='fixture',source=restored).load()
            self.assertEqual(loaded.replay(restored)[0].to_dict(),history.replay(record)[0].to_dict())
            self.assertEqual(canonical_sha256(restored.to_dict()),canonical_sha256(record.to_dict()))

    def test_public_serialization_cannot_mutate_stored_relationships(self):
        record=source();before=deepcopy(record.to_dict());public=record.to_dict()
        public['placement_contract']['relations'][1]['parent_id']='bed'
        self.assertEqual(record.to_dict(),before)

    def test_malformed_relationship_enums_return_bounded_validation_errors(self):
        record=source()
        for key in ('relation','anchor'):
            for bad in ([],{},False,None):
                value=deepcopy(record.placement_contract);value['relations'][0][key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaisesRegex(ValueError,'RELATION_INVALID'):
                    checked_placement_contract(value)

    def test_too_small_parent_resize_rejected_without_mutating_source_or_history(self):
        record=source();history=SceneChangeHistory.empty('fixture',record)
        # Legal minimum desk dimensions, but the monitor is deliberately larger.
        calls=[]
        for call in record.plan.calls:
            args=dict(call.arguments)
            if args['id']=='monitor':args['dimensions_m']=[.8,.2,.25]
            calls.append(replace(call,arguments=args))
        record=SiteDraftRecord.create(request_id='wide',provider_name='fixture',model_id='fixture',image_count=0,
            input_revision=record.input_revision,plan=replace(record.plan,calls=tuple(calls)),placement_contract=record.placement_contract)
        history=SceneChangeHistory.empty('fixture',record);before=deepcopy(record.to_dict())
        with self.assertRaisesRegex(ValueError,'SURFACE_CHANGED'):
            self.edit(record,history,'desk',dimensions_m=[.4,.35,.85])
        self.assertEqual(record.to_dict(),before);self.assertEqual(history.operations,())

    def test_detaching_child_or_erasing_relationships_is_rejected(self):
        record=source();history=SceneChangeHistory.empty('fixture',record)
        with self.assertRaisesRegex(ValueError,'SURFACE_CHANGED'):
            self.edit(record,history,'monitor',position_m=[1,0,.5])
        value=record.to_dict();value['placement_contract']=None
        with self.assertRaisesRegex(ValueError,'version mismatch'):SiteDraftRecord.from_dict(value)
        for bad in ('missing','monitor'):
            value=deepcopy(record.placement_contract);value['relations'][1]['parent_id']=bad
            with self.assertRaises(ValueError):checked_placement_contract(value)

    def test_forged_non_target_mutation_and_child_kind_edit_remain_rejected(self):
        record=source();history=SceneChangeHistory.empty('fixture',record)
        history,preview=self.edit(record,history,'desk',center_m=[-1.5,1.8])
        raw=deepcopy(preview['operation']);raw['expected_non_target_digests'].clear()
        with self.assertRaisesRegex(ValueError,'non-target'):
            SceneChangeHistory.empty('fixture',record).append(record,SceneChange.from_dict(raw))
        with self.assertRaisesRegex(ValueError,'DRAPE_KIND_UNSUPPORTED'):
            self.edit(record,history,'blanket',kind='bag')

if __name__=='__main__':unittest.main()
