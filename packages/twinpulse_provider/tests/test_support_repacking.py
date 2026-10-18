# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic synthetic cases through actual compiler/core, not model recovery."""
from copy import deepcopy
import math
import unittest

from test_budgeted_generation import text_request, empty_observation
from test_warehouse_semantics import parameter
from twinpulse_provider.semantic_scene import checked_structure, scene_draft, checked_batch, compile_scene
from twinpulse_provider.support_packing import grid_indices, bounded_support_repack
from twinpulse_core import SiteToolPlan
from twinpulse_core.photo_placement import placement_contract_from_trace, validate_placement_plan
from twinpulse_core.geometry_diagnostics import GeometryValidationError


def supported_fixture(parent_kind, parent_size, child_size, count, part):
    request = text_request('Create a room with a table, cabinet and supported objects', identity='support-synthetic')
    observation = empty_observation()
    inventory = [dict(id='support', kind=parent_kind, evidence_ref='text:0')]
    inventory += [dict(id='item_'+str(n), kind='unknown', evidence_ref='text:0') for n in range(count)]
    structure = dict(summary='Synthetic estimate', room=dict(width_m=8, length_m=8, height_m=3), inventory=inventory)
    parent = parameter(parent_kind, parent_size)
    parent['model_id'] = ('common.' if parent_kind == 'storage' else 'home.')+parent_kind
    parent['finish'] = 'natural'
    if parent_kind == 'storage': parent['variant'] = 'closed'
    params = {'support': parent}
    params.update({row['id']: parameter('unknown', child_size, parent='support', part=part)
                   for row in inventory[1:]})
    draft = checked_batch(params, scene_draft(checked_structure(structure, request, observation, bound=True)), list(params))
    return request, observation, draft


class SupportRepackingTests(unittest.TestCase):
    def test_exact_grid_fit_roundoff_is_not_empty_or_extra_space(self):
        self.assertEqual((math.ceil((-.42/2+.4/2+.01)*20), math.floor((.42/2-.4/2-.01)*20)), (1, -1))
        self.assertEqual(list(grid_indices(-.42/2+.4/2+.01, .42/2-.4/2-.01)), [0])
        self.assertEqual(list(grid_indices(.00001, -.00001)), [])
        self.assertEqual(list(grid_indices(-.10000000000000002, .1)), [-2, -1, 0, 1, 2])

    def test_exact_support_fit_compiles_without_resizing_or_changed_parent(self):
        request, observation, draft = supported_fixture('storage', (.8,.445,.9), (.4,.4,.1), 1, 'body')
        before = deepcopy(draft)
        payload, trace = compile_scene(draft, observation, request)
        plan = SiteToolPlan.from_dict(payload)
        validate_placement_plan(plan, placement_contract_from_trace(trace))
        child = next(c.arguments for c in plan.calls if c.arguments['id'] == 'item_0')
        self.assertEqual(child['dimensions_m'], [.4,.4,.1])
        self.assertEqual(draft, before)

    def test_supported_siblings_repack_prior_centred_choices_without_dropping(self):
        request, observation, draft = supported_fixture('dining_table', (1.8,1.,.75), (.45,.3,.01), 4, 'top')
        before = deepcopy(draft)
        payload, trace = compile_scene(draft, observation, request)
        plan = SiteToolPlan.from_dict(payload)
        validate_placement_plan(plan, placement_contract_from_trace(trace))
        self.assertEqual({c.arguments['id'] for c in plan.calls if c.tool == 'place_room_item'},
                         {'item_0','item_1','item_2','item_3'})
        self.assertEqual(trace['bounded_support_searches'][0]['status'], 'FOUND')
        self.assertFalse(trace['bounded_support_searches'][0]['global_infeasibility_proved'])
        self.assertEqual(draft, before)
        for row in trace['model_parameters']:
            if row['id'].startswith('item_'):
                self.assertEqual(row['placement']['parent_id'], 'support')

    def test_oversize_and_invalid_parent_do_not_become_success(self):
        request, observation, draft = supported_fixture('storage', (.8,.445,.9), (.9,.6,.1), 1, 'body')
        before = deepcopy(draft)
        with self.assertRaises(GeometryValidationError) as caught: compile_scene(draft, observation, request)
        issue = caught.exception.contract_report['issues'][0]
        self.assertEqual(issue['expected']['bounded_search']['termination_code'], 'EMPTY_VALID_DOMAIN')
        self.assertEqual(draft, before)

    def test_node_time_geometry_and_branch_budgets_are_typed_not_infeasibility(self):
        parent = dict(id='support',kind='storage',catalog_version='furniture-parametric-1.0',
            center_m=[0,0],yaw_deg=0,dimensions_m=[.8,.445,.9],variant='closed',finish='natural')
        items = [dict(id='child',kind='unknown',dimensions_m=[.4,.4,.1],yaw_deg=0)]
        for options, code in (({'max_nodes':0},'NODE_BUDGET_EXHAUSTED'),
                              ({'max_geometry_checks':0},'GEOMETRY_CHECK_BUDGET_EXHAUSTED')):
            found, report = bounded_support_repack(items, parent, 'body', **options)
            self.assertIsNone(found); self.assertEqual(report['termination_code'], code)
            self.assertFalse(report['global_infeasibility_proved']); self.assertFalse(report['physical_authority'])
        ticks = iter([0., 2., 2.])
        found, report = bounded_support_repack(items, parent, 'body', timeout_s=1., clock=lambda: next(ticks))
        self.assertIsNone(found); self.assertEqual(report['termination_code'],'TIME_BUDGET_EXHAUSTED')
        for options in ({'max_nodes':True},{'timeout_s':-1},{'branch_cap':0},{'max_geometry_checks':True}):
            with self.assertRaisesRegex(ValueError,'PHOTO_SUPPORT_SEARCH_BUDGET_INVALID'):
                bounded_support_repack(items, parent, 'body', **options)

    def test_parent_rotation_is_respected_and_internal_checker_errors_propagate(self):
        from unittest.mock import patch
        parent = dict(id='support',kind='storage',catalog_version='furniture-parametric-1.0',
            center_m=[1,2],yaw_deg=90,dimensions_m=[.8,.445,.9],variant='closed',finish='natural')
        items = [dict(id='child',kind='unknown',dimensions_m=[.4,.4,.1],yaw_deg=90)]
        found, report = bounded_support_repack(items,parent,'body')
        self.assertEqual(report['status'],'FOUND')
        from twinpulse_core.photo_quality import support_geometry, support_surface
        self.assertEqual(support_geometry(found['child'],parent,'body')['status'],'PASS')
        self.assertAlmostEqual(found['child']['position_m'][0],support_surface(parent,'body').transform.position_m[0])
        self.assertEqual(found['child']['yaw_deg'],90)
        with patch('twinpulse_provider.support_packing.support_geometry',side_effect=ValueError('CHECKER_INTERNAL')):
            with self.assertRaisesRegex(ValueError,'CHECKER_INTERNAL'):bounded_support_repack(items,parent,'body')
