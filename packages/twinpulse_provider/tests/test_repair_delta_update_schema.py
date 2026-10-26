# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Replay of the 2026-10-26 factory generation that stalled (REPAIR_STALLED) with no live model calls.

Saved evidence (tests/fixtures/repair_stall_2026-10-26/): the checkpoint draft, the semantic-compile diagnosis
(rack_1 is 4.04 m in a 4.0 m room) and the two repair deltas the planner returned. Both deltas shorten rack_1,
which is exactly the requested fix, yet the host rejected them as SEMANTIC_VARIANT_INVALID at $.operations[0]:
stored objects drop a null recipe_parameters while the update schema required the key.
"""
import json,pathlib,sys,unittest

ROOT=pathlib.Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))

FIXTURES=pathlib.Path(__file__).resolve().parent/'fixtures'/'repair_stall_2026-10-26'


def load(name):return json.loads((FIXTURES/name).read_text(encoding='utf-8'))


class RepairDeltaUpdateSchemaTest(unittest.TestCase):
    def test_saved_rack_height_repairs_are_valid_patches_and_change_the_draft(self):
        from twinpulse_provider.semantic_scene import patch_schema,patch_candidate,_shape_issues,revision
        from twinpulse_provider.repair_scope import normalize_delta
        draft=load('draft.json');diagnosis=load('compile_diagnosis.json')
        self.assertNotIn('recipe_parameters',draft['objects']['rack_1'])  # the stored shape that exposed the bug
        self.assertEqual(diagnosis['issues'][0]['code'],'PHOTO_MODEL_EXCEEDS_ROOM_HEIGHT')
        for name,height in (('repair2_delta.json',3.9),('repair3_delta.json',3.96)):
            delta=load(name)
            patch=normalize_delta(draft,delta,diagnosis)
            self.assertEqual([op['op'] for op in patch['operations']],['update'])  # null entries never become removals
            self.assertEqual(_shape_issues(patch,patch_schema(draft,None,repair_diagnosis=diagnosis)),[],name)
            result=patch_candidate(draft,patch,None,repair_diagnosis=diagnosis)
            self.assertNotEqual(revision(result),revision(draft))
            self.assertEqual(result['objects']['rack_1']['dimensions_m'][2],height)
            self.assertEqual({k:v for k,v in result['objects']['rack_1'].items() if k!='dimensions_m'},
                {k:v for k,v in draft['objects']['rack_1'].items() if k!='dimensions_m'})  # only the height moved

    def test_update_slots_only_require_fields_that_can_hold_a_value(self):
        from twinpulse_provider.semantic_scene import batch_schema
        draft=load('draft.json')
        slots=batch_schema(draft['inventory'],['rack_1','bollard_1'],recipes=draft.get('model_recipes'),
            selections={i:v['model_id'] for i,v in draft['objects'].items()})['properties']
        for identity,slot in slots.items():
            selected=draft['objects'][identity]['model_id']
            if selected.startswith('local.') and selected in (draft.get('model_recipes') or {}):
                # A recipe-bound local model keeps its parameter object: that key can hold a value.
                self.assertEqual(slot['properties']['recipe_parameters']['type'],'object',identity)
                self.assertIn('recipe_parameters',slot['required'],identity)
            else:
                self.assertEqual(slot['properties'].get('recipe_parameters'),{'type':'null'},identity)
                self.assertNotIn('recipe_parameters',slot['required'],identity)
            self.assertIn('dimensions_m',slot['required'],identity)


if __name__=='__main__':unittest.main()
