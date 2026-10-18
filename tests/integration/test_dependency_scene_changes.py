# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Real history replay: partial restore, nested dependencies, stale and Undo."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app','twinpulse_robot'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_provider/tests'))
from test_progressive_twin import fixture, record
from twinpulse_provider.semantic_scene import compile_scene
from twinpulse_app.scene_changes import SceneChangeHistory, SceneChangeStore, SceneChange
from twinpulse_app.dependency_patch import PATCH_VERSION, public_progressive
from twinpulse_core import canonical_sha256


def partial_source():
    request,obs,draft=fixture()
    payload,trace=compile_scene(draft,obs,request,progressive=True)
    return record(request,payload,trace)


def relation(identity,parent,part='body'):
    return dict(id=identity,relation='surface',parent_id=parent,part=part,anchor='centre',elevation_m=None)


def item(identity,position,size=(.2,.2,.02)):
    return dict(call_id='obj_'+identity,tool='place_room_item',arguments=dict(id=identity,
        kind='tabletop_item',label='Estimated rigid prop',catalog_version='room-items-1.0',
        position_m=list(position),dimensions_m=list(size),yaw_deg=0,observation_time_utc=None))


def patch(*edits): return dict(patch_version=PATCH_VERSION,edits=list(edits))
def edit(action,target,**fields): return dict(action=action,target_id=target,reason='Explicit human feedback',**fields)
def preview(history,source,op,*edits):
    return history.preview(source,operation_id=op,mode='dependency',tool_call=patch(*edits))
def adopt(history,source,value): return history.append(source,SceneChange.from_dict(value['operation']))


class DependencySceneChangeTests(unittest.TestCase):
    def test_duplicate_targets_keep_raw_patch_and_current_history_unchanged(self):
        from twinpulse_app.dependency_patch import checked_patch
        source=partial_source();history=SceneChangeHistory.empty('room',source)
        parent=deepcopy(next(c.to_dict() for c in source.plan.calls if c.arguments['id']=='support'))
        parent['arguments']['dimensions_m']=[1.2,.8,.9]
        first=edit('change','support',tool_call=parent)
        for second in (dict(deepcopy(first),reason='Keep the existing placement.'),edit('defer','support')):
            value=patch(first,second);original=deepcopy(value);before=history.to_dict()
            with self.assertRaisesRegex(ValueError,r'DEPENDENCY_DUPLICATE_TARGET: support in edits\[0\] and edits\[1\]'):
                checked_patch(value)
            with self.assertRaisesRegex(ValueError,'DEPENDENCY_DUPLICATE_TARGET'):
                history.preview(source,operation_id='duplicate',mode='dependency',tool_call=value)
            self.assertEqual(value,original);self.assertEqual(history.to_dict(),before)

    def test_atomic_resize_preserves_placement_and_allows_same_target_next_revision(self):
        source=partial_source();history=SceneChangeHistory.empty('room',source)
        restored=preview(history,source,'restore_atomic',edit('restore','item_0',
            tool_call=item('item_0',[0,0,.91],(.5,.3,.02)),placement=relation('item_0','support')))
        history=adopt(history,source,restored);placement=deepcopy(history.effective(source).placement)
        parent=deepcopy(next(c.to_dict() for c in history.effective(source).plan.calls if c.arguments['id']=='support'))
        parent['arguments']['dimensions_m']=[1.2,.8,.9]
        first=preview(history,source,'atomic_resize',edit('change','support',tool_call=parent))
        history=adopt(history,source,first)
        self.assertEqual(history.effective(source).placement,placement)
        child_xy=history.effective(source).inventory['item_0']['tool_call']['arguments']['position_m'][:2]
        parent['arguments']['center_m']=[.15,0]
        second=preview(history,source,'same_target_new_revision',edit('change','support',tool_call=parent))
        history=adopt(history,source,second)
        self.assertEqual(history.effective(source).placement,placement)
        self.assertNotEqual(first['result_revision'],second['result_revision'])
        self.assertNotEqual(first['result_state_sha256'],second['result_state_sha256'])
        current_xy=history.effective(source).inventory['item_0']['tool_call']['arguments']['position_m'][:2]
        self.assertAlmostEqual(current_xy[0]-child_xy[0],.15)
        self.assertAlmostEqual(current_xy[1],child_xy[1])

    def test_resize_restore_repeat_defer_undo_closed_reopen_keeps_source(self):
        source=partial_source();original=source.to_dict()
        with TemporaryDirectory() as folder:
            store=SceneChangeStore(Path(folder)/'edits.json',project_id='room',source=source)
            history=store.load()
            parent=next(c.to_dict() for c in source.plan.calls if c.arguments['id']=='support')
            enlarged=deepcopy(parent);enlarged['arguments']['dimensions_m']=[1.4,.8,.9]
            value=preview(history,source,'resize_restore',edit('change','support',tool_call=enlarged),
                edit('restore','item_0',tool_call=item('item_0',[0,0,.95],(.9,.6,.1)),placement=relation('item_0','support')))
            history=store.apply(value['operation'],value['preview_digest'])
            self.assertEqual(public_progressive(source,history.effective(source))['unresolved'],[])
            self.assertEqual(history.effective(source).inventory['item_0']['original_parameters'],source.progressive_twin['inventory'][1]['parameters'])
            moved=deepcopy(enlarged);moved['arguments']['center_m']=[.2,0]
            move=preview(history,source,'move_again',edit('change','support',tool_call=moved))
            history=store.apply(move['operation'],move['preview_digest'])
            self.assertAlmostEqual(history.effective(source).inventory['item_0']['tool_call']['arguments']['position_m'][0],.2)
            deferred=preview(history,source,'defer_parent',edit('defer','support'))
            history=store.apply(deferred['operation'],deferred['preview_digest'])
            self.assertEqual({r['id'] for r in public_progressive(source,history.effective(source))['unresolved']},{'support','item_0'})
            undo=history.preview(source,operation_id='undo_defer',mode='undo')
            history=store.apply(undo['operation'],undo['preview_digest'])
            self.assertNotEqual(history.current_scene_revision,move['result_revision'])
            self.assertIsNone(history.replay(source)[1].mission)
            reopened=SceneChangeStore(store.path,project_id='room',source=source).load()
            self.assertEqual(reopened.effective(source),history.effective(source))
            undo2=history.preview(source,operation_id='undo_move',mode='undo')
            history=store.apply(undo2['operation'],undo2['preview_digest'])
            self.assertEqual(history.replay(source)[0].calls,adopt(SceneChangeHistory.empty('room',source),source,value).replay(source)[0].calls)
            self.assertEqual(source.to_dict(),original)

    def test_nested_support_contact_and_recursive_move_rejects_penetration_cycle(self):
        source=partial_source();history=SceneChangeHistory.empty('room',source)
        restored=preview(history,source,'restore_mat',edit('restore','item_0',
            tool_call=item('item_0',[0,0,.91],(.5,.3,.02)),placement=relation('item_0','support')))
        history=adopt(history,source,restored)
        added=preview(history,source,'add_upper',edit('add','upper',tool_call=item('upper',[0,0,.93],(.1,.1,.02)),placement=relation('upper','item_0','top')))
        history=adopt(history,source,added)
        parent=next(c.to_dict() for c in history.replay(source)[0].calls if c.arguments['id']=='support')
        parent['arguments']['center_m']=[.25,.15]
        moved=preview(history,source,'move_chain',edit('change','support',tool_call=parent))
        history=adopt(history,source,moved)
        inventory=history.effective(source).inventory
        for identity in ('item_0','upper'):
            self.assertEqual(inventory[identity]['tool_call']['arguments']['position_m'][:2],[.25,.15])
        bad=item('upper',[.25,.15,.91],(.1,.1,.02))
        with self.assertRaisesRegex(ValueError,'SURFACE'):
            preview(history,source,'penetration',edit('change','upper',tool_call=bad))
        with self.assertRaisesRegex(ValueError,'CYCLE'):
            preview(history,source,'cycle',edit('reparent','item_0',placement=relation('item_0','upper','top')))
        # Reparent the upper item onto a distinct checked surface at the same XY.
        value=preview(history,source,'reparent',edit('reparent','upper',
            tool_call=item('upper',[.57,.15,.93],(.1,.1,.02)),placement=relation('upper','support')))
        self.assertAlmostEqual(adopt(history,source,value).effective(source).inventory['upper']['tool_call']['arguments']['position_m'][2],.91)

    def test_stale_idempotency_non_target_inventory_and_alternative_pending_sha(self):
        source=partial_source();history=SceneChangeHistory.empty('room',source)
        first=preview(history,source,'defer_pending',edit('defer','item_0'))
        alternative=preview(history,source,'remove_pending',edit('remove','item_0'))
        self.assertEqual(first['result_revision'],alternative['result_revision'])
        self.assertNotEqual(first['result_state_sha256'],alternative['result_state_sha256'])
        a=adopt(history,source,first);b=adopt(history,source,alternative)
        undo=a.preview(source,operation_id='undo_pending',mode='undo')
        with self.assertRaisesRegex(ValueError,'Undo state is stale'):
            b.append(source,SceneChange.from_dict(undo['operation']))
        forged=deepcopy(first['operation']);forged['expected_non_target_inventory_digests'].clear()
        with self.assertRaisesRegex(ValueError,'non-target'):
            history.append(source,SceneChange.from_dict(forged))
        with TemporaryDirectory() as folder:
            store=SceneChangeStore(Path(folder)/'edits.json',project_id='room',source=source)
            current=store.apply(first['operation'],first['preview_digest'])
            self.assertEqual(store.apply(first['operation'],first['preview_digest']),current)
            with self.assertRaisesRegex(ValueError,'stale'):
                store.apply(alternative['operation'],alternative['preview_digest'])
            changed=deepcopy(first['operation']);changed['dependency_patch']['edits'][0]['reason']='Different feedback'
            with self.assertRaisesRegex(ValueError,'different edit'):
                store.apply(changed,canonical_sha256(changed))

    def test_restore_cannot_drop_support_contract_or_float_via_floor_relation(self):
        source=partial_source();history=SceneChangeHistory.empty('room',source)
        oversized=item('item_0',[0,0,.95],(.9,.6,.1))
        with self.assertRaisesRegex(ValueError,'PLACEMENT_IDENTITY'):
            preview(history,source,'null_support',edit('restore','item_0',tool_call=oversized,placement=None))
        with self.assertRaisesRegex(ValueError,'SURFACE'):
            preview(history,source,'invalid_support',edit('restore','item_0',tool_call=oversized,placement=relation('item_0','support')))
        floor=dict(id='item_0',relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None)
        with self.assertRaisesRegex(ValueError,'FLOOR_HEIGHT'):
            preview(history,source,'floating_floor',edit('restore','item_0',tool_call=oversized,placement=floor))
        self.assertEqual(history.effective(source).inventory['item_0']['status'],'deferred')


if __name__=='__main__': unittest.main()
