# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic dimension ownership, offline only; not live model/Isaac acceptance."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))

from twinpulse_provider import GenerationService, InvalidProviderResponseError
from twinpulse_provider.photo_layout import requested_size, layout_schema, compile_layout
from twinpulse_provider.semantic_scene import structure_schema, checked_structure
import test_budgeted_generation as budget_fixtures
import test_photo_layout as photo_fixtures
import test_photo_parametric as parametric_fixtures


WORKSPACE_PROMPT=('Create an approximate 6 by 8 metre workspace with a desk against the back wall, '
    'a chair and a storage cabinet. Keep the central passage open. '
    'Dimensions are user estimates, not measurements.')


class RequestedRoomSizeTests(unittest.TestCase):
    def test_korean_particles_and_local_dimension_qualifiers(self):
        for prompt in ('실측이 아닌 추정 크기 6×5m의 서재를 만들어줘.',
                '6 × 5 미터의 작업실에 책상을 넣어줘.',
                '방의 추정 크기: 6x5m', '서재는 대략 6 × 5 미터',
                '공간은 크기 6m x 5m', '거실의 치수 6 by 5m', '서재의 추정 크기는 6×5m',
                '6m x 5m 크기의 추정 방을 만들어줘.', '6×5m 규격의 작업실',
                '6×5m 정도의 방', '6 by 5m estimated room',
                '서재는 6×5m, 책상은 1.2×0.6m'):
            with self.subTest(prompt=prompt):
                self.assertEqual(requested_size(prompt),(6.,5.))
        for prompt in ('방에 1.6×2.1m의 침대를 넣어줘.',
                '책상의 크기 1.2 x 0.6m', '0.8×0.4m의 수납장을 만들어줘.'):
            with self.subTest(prompt=prompt):
                self.assertIsNone(requested_size(prompt))

    def test_korean_owner_does_not_cross_a_clause_or_longer_word(self):
        for prompt in ('서재를 만들어줘. 6×5m', '거실에 물체를 넣어줘, 6×5m',
                '서재에 1.2×0.6m의 작업대를 놓아줘.',
                '6×5m의 서재가구를 만들어줘.', '6×5m의 서재용 책상', '방향 6×5m',
                '6×5m 크기의 방가구를 만들어줘.', '6×5m 크기의 우주선',
                '4×5m의 우주선을 만들어줘.'):
            with self.subTest(prompt=prompt),self.assertRaisesRegex(ValueError,'UNQUALIFIED_DIMENSIONS'):
                requested_size(prompt)
        for prompt in ('방 4×5m의 책상', '책상 4×5m의 서재', '4×5m의 방 또는 책상',
                '책상과 방은 4×5m', '4×5m의 방과 책상', '4×5m의 방 및 책상'):
            with self.subTest(prompt=prompt),self.assertRaisesRegex(ValueError,'AMBIGUOUS_DIMENSIONS'):
                requested_size(prompt)

    def test_exact_workspace_input_binds_only_the_explicit_estimated_extent(self):
        self.assertEqual(requested_size(WORKSPACE_PROMPT),(6.,8.))
        room=layout_schema(WORKSPACE_PROMPT)['properties']['room']['properties']
        self.assertEqual(room['width_m']['const'],6.)
        self.assertEqual(room['length_m']['const'],8.)

    def test_generic_space_names_and_both_dimension_orders(self):
        for noun in ('workspace','workshop','shop','office','kitchen','warehouse','studio',
                'living room','dining room','room','space','study','home office','lounge','hallway',
                'corridor','meeting room','nursery','작업실','사무실','매장','방','서재','복도','회의실','아이방'):
            for prompt in (f'Create an approximate 3.5 by 7 metre {noun}.',
                    f'{noun} dimensions: 3.5m x 7m',f'{noun}, approximately 3.5 × 7 metres'):
                with self.subTest(prompt=prompt):
                    self.assertEqual(requested_size(prompt),(3.5,7.))

    def test_furniture_following_does_not_inherit_a_room_noun(self):
        for prompt in ('A room with a 1.6 by 2.1 m bed',
                'A bedroom. A 1.6 by 2.1 m bed',
                'An office with a 1.2 by 0.6 m desk',
                'A workspace with a 0.8 by 0.4 metre storage cabinet',
                'A room containing a 0.5 x 0.5 m office chair',
                'A bed 1 by 2 metres','desk dimensions: 1.2 by 0.6 metres'):
            with self.subTest(prompt=prompt):
                self.assertIsNone(requested_size(prompt))
                self.assertNotIn('const',layout_schema(prompt)['properties']['room']['properties']['width_m'])

    def test_explicit_room_and_object_pairs_are_independently_owned(self):
        for prompt in ('A 4 by 5 metre bedroom with a bed 1 by 2 metres',
                'A workspace 6 by 8 metres with a 1.2 by 0.6 m desk',
                'A desk 1.2 by 0.6 metres. Create an office 6 by 8 metres.',
                'A 0.8 x 0.4 m storage cabinet in a 6 x 8 m shop'):
            with self.subTest(prompt=prompt):
                self.assertEqual(requested_size(prompt),(4.,5.) if 'bedroom' in prompt else (6.,8.))

    def test_conflicting_or_multiple_possible_owners_fail_closed(self):
        for prompt in ('desk 6 by 8 metre workspace', 'room 1 by 2 metre bed',
                'desk or table 1 by 2 metres','desk and room 4 by 5 metres',
                'A 1 by 2 metre desk or table','A 4 by 5 metre room or desk',
                'room 4 by 5 and office 6 by 7','workspace 4 by 5 and shop 6 by 7'):
            with self.subTest(prompt=prompt),self.assertRaisesRegex(ValueError,'AMBIGUOUS_DIMENSIONS'):
                requested_size(prompt)

    def test_unknown_unqualified_pairs_and_stale_clause_names_are_not_inferred(self):
        for prompt in ('4 by 5 metres','A bedroom. 4 by 5 metres',
                'A workspace; 4 by 5 metres','A room with furniture, 4 by 5 metres',
                'Create a 4 by 5 metre spaceship','A showroom 4 by 5 metres',
                'A room 4 by 5 metres and 1 by 2 metres'):
            with self.subTest(prompt=prompt),self.assertRaisesRegex(ValueError,'UNQUALIFIED_DIMENSIONS'):
                requested_size(prompt)

    def test_semantic_structure_uses_the_same_binding_and_rejects_extent_changes(self):
        request=budget_fixtures.text_request(WORKSPACE_PROMPT)
        observation=budget_fixtures.empty_observation()
        schema=structure_schema(request,observation,bound=True)
        self.assertEqual(schema['properties']['room']['properties']['width_m']['const'],6.)
        value=dict(summary='Estimated space',room=dict(width_m=6,length_m=8,height_m=2.6),inventory=[])
        self.assertEqual(checked_structure(value,request,observation,bound=True),value)
        changed=deepcopy(value);changed['room']['width_m']=7
        with self.assertRaisesRegex(InvalidProviderResponseError,'EXPLICIT_ROOM_DIMENSIONS_CHANGED'):
            checked_structure(changed,request,observation,bound=True)

    def test_compiler_preserves_explicit_estimates_without_measurement_authority(self):
        value=photo_fixtures.layout();value['room'].update(width_m=6,length_m=8)
        original=deepcopy(value)
        payload,trace=compile_layout(value,photo_fixtures.observation(),
            photo_fixtures.request(WORKSPACE_PROMPT),None)
        self.assertEqual(value,original)
        self.assertEqual(payload['calls'][0]['arguments']['size_m'],[6,8])
        self.assertEqual(payload['call_evidence'][0]['basis'],'user')
        self.assertFalse(trace['physical_authority'])
        self.assertNotIn('measurement_constraints',payload)
        self.assertTrue(all(row['basis']!='measured' for row in payload['call_evidence']))
        value['room']['width_m']=7
        with self.assertRaisesRegex(ValueError,'USER_DIMENSIONS_CHANGED'):
            compile_layout(value,photo_fixtures.observation(),photo_fixtures.request(WORKSPACE_PROMPT),None)

    def test_exact_text_input_reaches_existing_budgeted_structure_batch_compiler(self):
        # Explicit scripted transport. Responses are test data, not scene
        # recipes, a production fallback, or paid provider quality evidence.
        rows=[dict(id=identity,kind=kind,evidence_ref='text:0') for identity,kind in
            (('desk','desk'),('chair','chair'),('cabinet','storage'))]
        structure=dict(summary='Unmeasured workspace',room=dict(width_m=6,length_m=8,height_m=2.6),inventory=rows)
        batch={}
        for row,region in zip(rows,('rear_left','middle_left','rear_right')):
            item=parametric_fixtures.object_intent(row['id'],row['kind'],region)
            batch[row['id']]={key:val for key,val in item.items() if key not in {'id','kind','observation_ids'}}
        transport=budget_fixtures.FixtureTransport([structure,batch])
        provider=budget_fixtures.PipelineTests.provider(self,transport)
        result=asyncio.run(GenerationService(provider,budget_fixtures.config(timeout_s=300),plan_version='2.2')
            .generate(budget_fixtures.text_request(WORKSPACE_PROMPT)))
        self.assertEqual(result.plan.calls[0].arguments['size_m'],[6,8])
        self.assertEqual([body['response_format']['json_schema']['name'] for body in transport.bodies],
            ['twinpulse_semantic_structure','twinpulse_semantic_batch'])
        self.assertEqual(result.provider_provenance['budget']['requests'],2)
        self.assertEqual(result.provider_provenance['budget']['repairs'],0)
        self.assertEqual({call.arguments.get('id') for call in result.plan.calls[4:]},{'desk','chair','cabinet'})


if __name__=='__main__':unittest.main()
