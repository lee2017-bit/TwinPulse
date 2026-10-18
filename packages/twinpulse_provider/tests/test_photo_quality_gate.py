# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Product geometry/repair tests. Transport is fake; no new model or robot use."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))

from twinpulse_core.photo_quality import (inspect_photo_geometry,
    support_geometry, public_photo_quality, checked_constraints)
from tests.fixtures.historical_photo_quality import reviewed_photo_constraints
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256, photo_reference
from twinpulse_core.revisions import canonical_sha256
from twinpulse_provider import (GenerationRequest, ImageInput, GenerationService,
                               InvalidProviderResponseError, ProviderConfigurationError)
from twinpulse_provider.photo_layout import compile_layout, layout_schema, REVISION, SUPPORT_COMPILER_REVISION
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider
from twinpulse_app.product_workflow_service import _public_generation_diagnostics
from test_photo_layout import observation
from test_nebius_pipeline import ScriptedTransport, completion, config, OBSERVER_MODEL, PLANNER_MODEL


def inputs():
    request=GenerationRequest('quality-fixture','Create an approximate room 8 by 8 metres.',
        (ImageInput('fixture.jpg','image/jpeg',b'quality-transport-fixture'),))
    digest=hashlib.sha256(request.images[0].content).hexdigest()
    constraints=replace(reviewed_photo_constraints(PHOTO_SHA256),image_sha256=digest)
    reference=photo_reference(PHOTO_SHA256);reference['image_sha256']=digest
    regions=['front_left','middle_right','rear_left','middle_left','front_centre','front_right',
             'rear_right','middle_centre','rear_centre']
    intent=dict(layout_version=REVISION,summary='Estimates, not measured room reconstruction.',
        room=dict(width_m=8,length_m=8,height_m=2.5),
        objects={i['id']:dict(region=regions[n%9],yaw_deg=0,observation_ids=[])
                 for n,i in enumerate(reference['items'])})
    intent['objects']['bed']['region']='middle_right'
    # The observer fixture actually sees this bed; reviewed extra objects may
    # use their explicit human review, but must not hide the observed bed.
    intent['objects']['bed']['observation_ids']=['bed_visual']
    intent['objects']['desk']['region']='rear_left'
    intent['objects']['wardrobe']['region']='rear_right'
    for identity in ('floor_bags','boxes'):intent['objects'][identity]['region']='front_left'
    return request,reference,constraints,intent


def compiled(*, supports=True):
    request,reference,constraints,intent=inputs()
    payload,trace=compile_layout(intent,observation(),request,reference,
        quality_constraints=constraints if supports else None)
    return payload,trace,constraints


def by_id(payload):
    return {c['arguments']['id']:c['arguments'] for c in payload['calls']}


class PhotoQualityGateTests(unittest.TestCase):
    def provider(self, transport, *, compact=True, repairs=1):
        return NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=repairs,
            compact_photo_layout=compact)

    def run_pipeline(self, responses, *, compact=True, repairs=1, constraints=None, prompt=None):
        request,reference,current,_=inputs()
        if prompt:request=replace(request,prompt=prompt)
        transport=ScriptedTransport(completion('observer',OBSERVER_MODEL,observation().to_dict()),
                                    *(completion(str(n),PLANNER_MODEL,v) for n,v in enumerate(responses)))
        provider=self.provider(transport,compact=compact,repairs=repairs)
        service=GenerationService(provider,config(timeout_s=10),plan_version='2.2')
        # Explicit historical review fixture, never an automatic hash lookup in
        # the product. These tests exercise generic explicit constraints only.
        from twinpulse_provider.photo_layout import build_layout_body
        from twinpulse_provider import photo_layout as module
        real_compile=module.compile_layout
        real_inspect=inspect_photo_geometry
        reviewed=constraints or current
        with patch('twinpulse_provider.photo_layout.compile_layout',side_effect=lambda value,observed,req,unused,**kw:
                real_compile(value,observed,req,reference,quality_constraints=reviewed)), \
             patch('twinpulse_provider.photo_layout.build_layout_body',side_effect=lambda req,observed,model,unused,**kw:
                build_layout_body(req,observed,model,reference,quality_constraints=reviewed)), \
             patch('twinpulse_core.photo_quality.inspect_photo_geometry',side_effect=lambda payload,digest,unused=None,**kw:
                real_inspect(payload,digest,reviewed,**kw)):
            try:
                result=asyncio.run(service.generate(request));error=None
            except (InvalidProviderResponseError, ValueError) as failure:
                result=None;error=failure
        return result,error,transport,service

    def test_unknown_photo_does_not_borrow_reviewed_constraints(self):
        payload,_,_=compiled()
        self.assertIsNone(reviewed_photo_constraints('0'*64))
        report=inspect_photo_geometry(payload,'0'*64)
        self.assertEqual(report['status'],'UNVERIFIED')
        self.assertEqual(report['checks'],[])
        self.assertEqual(report['full_photo_reconstruction'],'UNVERIFIED')

    def test_known_constraints_are_hash_bound(self):
        _,_,constraints=compiled()
        with self.assertRaisesRegex(ValueError,'EVIDENCE_MISMATCH'):
            checked_constraints(constraints,PHOTO_SHA256)

    def test_compiler_derives_three_supports_and_keeps_all_24_items(self):
        payload,trace,constraints=compiled()
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        self.assertEqual(report['checked_relation_status'],'PASS')
        self.assertEqual(report['status'],'PARTIAL')
        self.assertEqual(report['metric_scale_validation'],'UNVERIFIED_NO_MEASUREMENTS')
        self.assertEqual(report['full_photo_reconstruction'],'UNVERIFIED')
        self.assertEqual(report['physical_validation'],'NOT_RUN')
        self.assertFalse(report['large_room_scale_warning'])
        self.assertEqual(len(trace['placements']),24)
        from twinpulse_provider.photo_layout import BOUNDARY_PACKING_COMPILER_REVISION
        self.assertEqual(trace['compiler_revision'],BOUNDARY_PACKING_COMPILER_REVISION)
        self.assertEqual(trace['contract'],REVISION)
        self.assertFalse(trace['physical_authority'])
        self.assertEqual(sum('parent' in row for row in report['checks']),3)

    def test_optional_relation_compiler_does_not_change_legacy_proxies(self):
        payload,trace,constraints=compiled(supports=False)
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        from twinpulse_provider.photo_layout import BOUNDARY_PACKING_COMPILER_REVISION
        self.assertEqual(trace['compiler_revision'],BOUNDARY_PACKING_COMPILER_REVISION)
        self.assertEqual(trace['placement_relationships'],'NOT_RECONSTRUCTED')
        self.assertEqual(sum(i['code']=='PHOTO_SUPPORT_MISMATCH' for i in report['issues']),3)
        self.assertFalse(report['repairable'])

    def test_request_and_response_schema_stay_unchanged(self):
        request,reference,constraints,intent=inputs()
        original=deepcopy(intent);schema=layout_schema(request.prompt,reference,observation())
        compile_layout(intent,observation(),request,reference,quality_constraints=constraints)
        self.assertEqual(intent,original)
        self.assertEqual(layout_schema(request.prompt,reference,observation()),schema)
        self.assertEqual(set(schema['properties']['objects']['properties']['monitor']['properties']),
                         {'region','yaw_deg','observation_ids'})

    def test_supported_child_advisory_region_has_explicit_derived_provenance(self):
        request,reference,constraints,intent=inputs()
        intent['objects']['top_storage']['region']='front_left'
        payload,trace=compile_layout(intent,observation(),request,reference,quality_constraints=constraints)
        child=next(i for i in trace['placements'] if i['id']=='top_storage')
        self.assertEqual(child['requested_region'],'front_left')
        self.assertEqual(child['region'],'rear_right')
        self.assertEqual(child['parent'],'wardrobe')
        self.assertEqual(inspect_photo_geometry(payload,constraints.image_sha256,constraints)['issues'],[])

    def test_rotated_parent_and_children_support_at_all_quadrant_yaws(self):
        for yaw in (0,90,-90,180):
            with self.subTest(yaw=yaw):
                request,reference,constraints,intent=inputs()
                for identity in ('desk','wardrobe','monitor','tabletop_items','top_storage'):
                    intent['objects'][identity]['yaw_deg']=yaw
                payload,_=compile_layout(intent,observation(),request,reference,quality_constraints=constraints)
                self.assertEqual(inspect_photo_geometry(payload,constraints.image_sha256,constraints)['issues'],[])

    def test_same_height_outside_parent_is_not_support(self):
        payload,_,constraints=compiled();objects=by_id(payload)
        objects['monitor']['position_m'][0]+=2
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        row=next(c for c in report['checks'] if c['id']=='monitor')
        self.assertFalse(row['xy_contained'])
        self.assertEqual(row['bottom_to_support_top_gap_m'],0)
        self.assertEqual(row['status'],'FAIL')

    def test_xy_inside_does_not_hide_wrong_height(self):
        payload,_,constraints=compiled();objects=by_id(payload)
        objects['top_storage']['position_m'][2]-=.3
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        row=next(c for c in report['checks'] if c['id']=='top_storage')
        self.assertTrue(row['xy_contained'])
        self.assertEqual(row['status'],'FAIL')

    def test_siblings_do_not_overlap_and_checker_detects_overlap(self):
        payload,_,constraints=compiled();objects=by_id(payload)
        objects['tabletop_items']['position_m']=[*objects['monitor']['position_m'][:2],.84]
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        row=next(c for c in report['checks'] if c['id']=='tabletop_items')
        self.assertEqual(row['status'],'FAIL')
        self.assertEqual(row['overlaps_sibling'],'monitor')

    def test_wrong_front_rear_detected_even_with_correct_left_right(self):
        request,reference,constraints,intent=inputs()
        intent['objects']['desk']['region']='front_left'
        payload,_=compile_layout(intent,observation(),request,reference,quality_constraints=constraints)
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        issues=[i for i in report['issues'] if i['id']=='desk']
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['expected'],'rear')
        self.assertTrue(report['repairable'])

    def test_missing_object_is_not_existence_or_relation_pass(self):
        payload,_,constraints=compiled()
        payload['calls']=[c for c in payload['calls'] if c['arguments']['id']!='top_storage']
        payload['call_evidence']=[c for c in payload['call_evidence'] if c['call_id']!='obj_top_storage']
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        self.assertIn('PHOTO_OBJECT_MISSING',[i['code'] for i in report['issues']])
        self.assertFalse(report['generation_allowed'])

    def test_oversized_child_cannot_be_accepted_as_supported(self):
        payload,_,constraints=compiled();objects=by_id(payload)
        objects['top_storage']['dimensions_m'][0]=2
        self.assertEqual(support_geometry(objects['top_storage'],objects['wardrobe'],'body')['status'],'FAIL')

    def test_nonfinite_geometry_rejected_before_semantic_report(self):
        payload,_,constraints=compiled();by_id(payload)['top_storage']['position_m'][2]=float('nan')
        with self.assertRaises(ValueError):inspect_photo_geometry(payload,constraints.image_sha256,constraints)

    def test_model_self_acceptance_does_not_change_quality(self):
        payload,_,constraints=compiled(supports=False)
        payload['summary']='accept_estimated: all dimensions and supports verified'
        self.assertEqual(inspect_photo_geometry(payload,constraints.image_sha256,constraints)['status'],'FAIL')

    def test_constraints_cycle_rejected(self):
        _,_,constraints=compiled()
        bad=replace(constraints,supports=(('top_storage','wardrobe','body'),('wardrobe','top_storage','top')))
        with self.assertRaisesRegex(ValueError,'SUPPORT_GRAPH'):
            checked_constraints(bad,bad.image_sha256)

    def test_product_never_looks_up_photo_specific_host_reference(self):
        request,_,_,_=inputs()
        payload,_,_=compiled()
        transport=ScriptedTransport(completion('observer',OBSERVER_MODEL,observation().to_dict()),
                                    completion('planner',PLANNER_MODEL,payload))
        service=GenerationService(self.provider(transport,compact=False),config(timeout_s=10),plan_version='2.2')
        with patch('twinpulse_core.room_photo_inventory.photo_reference',side_effect=AssertionError('retired lookup')) as inventory, \
             patch('twinpulse_core.photo_quality.reviewed_photo_constraints',side_effect=AssertionError('retired lookup')) as reviewed:
            result=asyncio.run(service.generate(request))
        inventory.assert_not_called()
        reviewed.assert_not_called()
        self.assertEqual(result.provider_provenance['photo_geometry_quality']['status'],'UNVERIFIED')
        self.assertEqual(len(transport.bodies),2)

    def test_support_failure_report_is_removed_if_next_attempt_fails_before_geometry(self):
        legacy,_,_=compiled(supports=False)
        result,error,transport,service=self.run_pipeline([legacy,{}],compact=False)
        self.assertIsNone(result)
        self.assertEqual(len(transport.bodies),3)
        diagnostic=service.diagnostic_snapshot()
        self.assertNotIn('photo_quality',diagnostic)
        self.assertEqual(diagnostic['attempts'][1]['photo_quality']['status'],'FAIL')

    def test_ceiling_intersection_is_not_an_accepted_support_relation(self):
        payload,_,constraints=compiled()
        for c in payload['calls']:
            if c['tool']=='create_wall':
                c['arguments']['dimensions_m'][2]=2
                c['arguments']['position_m'][2]=1
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        self.assertIn('PHOTO_CEILING_INTERSECTION',[i['code'] for i in report['issues']])
        self.assertFalse(report['generation_allowed'])

    def test_bounded_quality_repair_through_real_generation_service(self):
        *_,good=inputs();bad=deepcopy(good)
        bad['objects']['bed']['region']='middle_left'
        bad['objects']['desk']['region']='front_right'
        result,error,transport,service=self.run_pipeline([bad,good])
        self.assertIsNone(error)
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(result.provider_provenance['reliability']['repair_count'],1)
        self.assertEqual(result.provider_provenance['photo_geometry_quality']['status'],'PARTIAL')
        feedback=json.loads(transport.bodies[2]['messages'][-1]['content'])
        self.assertEqual(len(feedback['geometry_quality']['issues']),3)
        self.assertEqual(transport.bodies[1]['response_format'],transport.bodies[2]['response_format'])
        attempts=service.diagnostic_snapshot()['attempts']
        self.assertEqual(attempts[1]['photo_quality']['status'],'FAIL')
        self.assertEqual(attempts[2]['photo_quality']['status'],'PARTIAL')

    def test_same_failure_cannot_exceed_shared_single_repair(self):
        *_,bad=inputs();bad['objects']['desk']['region']='front_right'
        result,error,transport,service=self.run_pipeline([bad,bad])
        self.assertIsNone(result)
        self.assertIsInstance(error,InvalidProviderResponseError)
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(service.diagnostic_snapshot()['repair_count'],1)
        self.assertEqual(error.diagnostics['photo_quality']['status'],'FAIL')

    def test_repair_can_change_unmeasured_room_estimate(self):
        *_,good=inputs();bad=deepcopy(good)
        bad['objects']['desk']['region']='front_left'
        good['room'].update(width_m=10,length_m=10)
        result,error,transport,_=self.run_pipeline([bad,good],prompt='Create an approximate bedroom')
        self.assertIsNone(error)
        self.assertEqual(len(transport.bodies),3)
        floor=next(c['arguments'] for c in result.plan.to_dict()['calls'] if c['tool']=='create_floor')
        self.assertEqual(floor['size_m'],[10,10])

    def test_direct_repair_can_shift_an_inferred_room_frame(self):
        legacy,_,_=compiled(supports=False);good,_,_=compiled()
        for call in good['calls']:
            args=call['arguments']
            key='center_m' if 'center_m' in args else 'position_m'
            args[key][0]+=1
        result,error,transport,_=self.run_pipeline([legacy,good],compact=False)
        self.assertIsNone(error)
        floor=next(c['arguments'] for c in result.plan.to_dict()['calls'] if c['tool']=='create_floor')
        self.assertEqual(floor['center_m'],[1,0])
        self.assertEqual(len(transport.bodies),3)

    def test_unsupported_support_dependency_does_not_dispatch_repair(self):
        legacy,_,_=compiled(supports=False);*_,good=inputs()
        with patch('twinpulse_provider.photo_layout.compile_layout',return_value=(legacy,{})):
            result,error,transport,service=self.run_pipeline([good])
        self.assertIsNone(result)
        self.assertFalse(error.diagnostics['photo_quality']['repairable'])
        self.assertEqual(len(transport.bodies),2)
        self.assertEqual(service.diagnostic_snapshot()['repair_count'],0)

    def test_compiler_dependency_failure_does_not_retry(self):
        *_,good=inputs()
        with patch('twinpulse_provider.photo_layout.compile_layout',side_effect=ValueError('PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE: monitor')):
            result,error,transport,service=self.run_pipeline([good])
        self.assertIsNone(result)
        self.assertIn('PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE',str(error))
        self.assertEqual(len(transport.bodies),2)
        self.assertEqual(service.diagnostic_snapshot()['repair_count'],0)

    def test_default_direct_site22_photo_path_also_rechecks_and_repairs_quality(self):
        legacy,_,_=compiled(supports=False);good,_,_=compiled()
        result,error,transport,_=self.run_pipeline([legacy,good],compact=False)
        self.assertIsNone(error)
        self.assertEqual(len(transport.bodies),3)
        self.assertNotIn('photo_layout_compiler',result.provider_provenance)
        self.assertEqual(result.provider_provenance['photo_geometry_quality']['checked_relation_status'],'PASS')
        initial=json.loads(transport.bodies[1]['messages'][1]['content'])
        self.assertNotIn('reviewed_geometry_constraints',initial)
        feedback=json.loads(transport.bodies[2]['messages'][-1]['content'])
        self.assertTrue(feedback['geometry_quality']['repairable'])

    def test_product_diagnostics_preserve_all_quality_errors_without_provider_text(self):
        legacy,_,constraints=compiled(supports=False)
        report=inspect_photo_geometry(legacy,constraints.image_sha256,constraints)
        report['authorization']='DO_NOT_EXPOSE'
        diagnostic=dict(request_id='q',photo_quality=report,attempts=[dict(photo_quality=report)],
                        response_body='DO_NOT_EXPOSE',headers={'Authorization':'DO_NOT_EXPOSE'})
        public=_public_generation_diagnostics(diagnostic)
        self.assertEqual(len(public['photo_quality']['issues']),3)
        self.assertEqual(len(public['attempts'][0]['photo_quality']['issues']),3)
        self.assertNotIn('DO_NOT_EXPOSE',json.dumps(public))
        self.assertEqual(public['photo_quality']['metric_scale_validation'],'UNVERIFIED_NO_MEASUREMENTS')
        self.assertEqual(public_photo_quality({'schema_version':'untrusted'}),{})

    def test_old_actual_candidates_rejected_without_modifying_originals(self):
        audit=ROOT/'artifacts/agent-reliability-20261007/photo-quality-loop-r1'
        for name in ('saved_actual_negative','controlled_region_repair','quality_feedback_correction'):
            with self.subTest(candidate=name):
                path=audit/(name+'-plan.json')
                if not path.is_file():self.skipTest('Local historical evidence unavailable')
                original=path.read_bytes()
                report=inspect_photo_geometry(json.loads(original.decode('utf-8')),PHOTO_SHA256,
                                              reviewed_photo_constraints(PHOTO_SHA256))
                self.assertEqual(report['status'],'FAIL')
                self.assertFalse(report['generation_allowed'])
                self.assertEqual(sum(i['code']=='PHOTO_SUPPORT_MISMATCH' for i in report['issues']),3)
                self.assertEqual(path.read_bytes(),original)

    def test_repeated_quality_inspection_is_deterministic_and_does_not_mutate(self):
        payload,_,constraints=compiled();before=canonical_sha256(payload)
        first=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        self.assertEqual(first,inspect_photo_geometry(payload,constraints.image_sha256,constraints))
        self.assertEqual(canonical_sha256(payload),before)


if __name__=='__main__':unittest.main()
