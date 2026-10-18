# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reviewed semantics are bounded estimates, not photo scale measurements."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import hashlib

from test_photo_quality_gate import inputs
import test_photo_quality_gate as quality_tests
from test_photo_parametric import object_intent
from test_photo_layout import observation
from twinpulse_core.photo_quality import inspect_photo_geometry, public_photo_quality, checked_constraints
from tests.fixtures.historical_photo_quality import reviewed_photo_constraints
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256
from twinpulse_core.revisions import canonical_sha256
from twinpulse_provider.photo_layout import compile_layout, layout_schema, PARAMETRIC_REVISION, build_layout_body
from test_nebius_pipeline import PLANNER_MODEL


def semantic_inputs():
    request,reference,_,legacy=inputs()
    constraints=replace(reviewed_photo_constraints(PHOTO_SHA256,semantic_review=True),
                        image_sha256=reference['image_sha256'],max_estimated_area_m2=None)
    value=deepcopy(legacy);value['layout_version']=PARAMETRIC_REVISION
    for identity,region in (('wood_frame','front_left'),('floor_fan','middle_left'),('office_chair','rear_left'),
                           ('entry_door','front_left'),('cables','front_right'),('power_adapter','front_right'),
                           ('basket','front_left')):
        value['objects'][identity]['region']=region
    for item in reference['items']:
        identity=item['id'];region=value['objects'][identity]['region']
        row=object_intent(identity,item['kind'],region);row.pop('id');row.pop('kind')
        row['observation_ids']=['bed_visual'] if identity=='bed' else []
        value['objects'][identity]=row
    for child,parent,part in constraints.supports:
        value['objects'][child]['placement'].update(relation='surface',parent_id=parent,part=part)
    for child,choices in constraints.attachments:
        parent,part=choices[0]
        value['objects'][child]['placement'].update(relation='drape',parent_id=parent,part=part,anchor='front')
    return request,reference,constraints,value


class PhotoSemanticReviewTests(unittest.TestCase):
    def test_bounded_search_preserves_grid_regions_inventory_and_rejects_exhaustion(self):
        from twinpulse_provider.photo_layout import _bounded_region_repack
        rows=[dict(id='a',region='front_left'),dict(id='b',region='front_right')]
        before=deepcopy(rows)
        found,report=_bounded_region_repack(rows,lambda row:(.4,.4),3.5,4.)
        self.assertEqual(set(found),{'a','b'})
        self.assertLess(found['a'][0],0);self.assertGreater(found['b'][0],0)
        self.assertTrue(all(y<0 for x,y in found.values()))
        self.assertEqual(report['status'],'FOUND');self.assertEqual(rows,before)
        again,_=_bounded_region_repack(rows,lambda row:(.4,.4),3.5,4.)
        self.assertEqual(found,again)
        for options in ({'max_nodes':0},{'timeout_s':0}):
            centres,report=_bounded_region_repack(rows,lambda row:(.4,.4),3.5,4.,**options)
            self.assertIsNone(centres);self.assertNotEqual(report['status'],'FOUND')
        centres,report=_bounded_region_repack(rows,lambda row:(5.,5.),3.5,4.)
        self.assertIsNone(centres);self.assertNotEqual(report['status'],'FOUND')

    def test_original_failed_real_packing_response_recompiles_without_source_or_model_change(self):
        from twinpulse_provider.contracts import GenerationRequest, ImageInput
        from twinpulse_provider.nebius_pipeline import parse_chat_completion, ObservationArtifact
        from tests.fixtures.historical_room_photo_inventory import photo_reference
        root=Path(__file__).resolve().parents[3]/'artifacts/pre-demo-20261008/photo-semantic-add10-r4'
        evidence_root=root/'runtime/provider-evidence'
        if not evidence_root.is_dir():self.skipTest('Original real evidence is not included in a portable test package')
        sources={p:p.read_bytes() for p in evidence_root.glob('*.json')}
        values=[]
        for raw in sources.values():
            record=json.loads(raw);response=record['response_redacted'].encode()
            self.assertEqual(hashlib.sha256(response).hexdigest(),record['response_sha256'])
            completion=parse_chat_completion(json.loads(response))
            values.append(json.loads(completion.content))
        intent=next(v for v in values if 'room' in v)
        observed=ObservationArtifact.from_mapping(next(v for v in values if 'room' not in v))
        photo=Path(__file__).resolve().parents[3]/'artifacts/agent-reliability-20261007/photo-output10000-chat-isaac-r1/1-사진-1.jpg'
        request=GenerationRequest('offline-rejection-regression','Create a digital twin of my bedroom with a bed and desk.',
            (ImageInput(photo.name,'image/jpeg',photo.read_bytes()),))
        constraints=reviewed_photo_constraints(PHOTO_SHA256,semantic_review=True)
        reference=photo_reference(PHOTO_SHA256);before=deepcopy(intent)
        with patch('twinpulse_provider.photo_layout._bounded_region_repack',return_value=(None,{'status':'TEST_DISABLED'})):
            with self.assertRaisesRegex(ValueError,'PHOTO_LAYOUT_REGION_FULL'):
                compile_layout(intent,observed,request,reference,quality_constraints=constraints)
        plan,provenance=compile_layout(intent,observed,request,reference,quality_constraints=constraints)
        self.assertEqual(provenance['compiler_revision'],'photo-layout-compiler-1.7')
        self.assertEqual(provenance['bounded_packing_search']['status'],'FOUND')
        self.assertEqual(intent,before);self.assertEqual(intent['room']['width_m'],3.5)
        self.assertEqual(intent['room']['length_m'],4.)
        report=inspect_photo_geometry(plan,PHOTO_SHA256,constraints)
        self.assertEqual(report['issues'],[]);self.assertEqual(len(report['checks']),32)
        self.assertEqual(report['full_photo_reconstruction'],'UNVERIFIED')
        repeated,_=compile_layout(intent,observed,request,reference,quality_constraints=constraints)
        self.assertEqual(canonical_sha256(plan),canonical_sha256(repeated))
        self.assertEqual({p:p.read_bytes() for p in sources},sources)

    def test_legacy_constraints_and_unknown_photo_do_not_gain_semantic_authority(self):
        old=reviewed_photo_constraints(PHOTO_SHA256)
        self.assertEqual(old.to_dict()['schema_version'],'reviewed-photo-geometry-1.0')
        self.assertNotIn('attachments',old.to_dict())
        self.assertIsNone(reviewed_photo_constraints('0'*64,semantic_review=True))
        new=reviewed_photo_constraints(PHOTO_SHA256,semantic_review=True)
        self.assertEqual(new.to_dict()['schema_version'],'reviewed-photo-geometry-1.1')
        self.assertEqual(new.to_dict()['metric_scale_validation'],'UNVERIFIED_NO_MEASUREMENTS')
        with self.assertRaisesRegex(ValueError,'SCALE_INVALID'):
            checked_constraints(replace(new,max_estimated_area_m2=float('nan')),PHOTO_SHA256)
        with self.assertRaisesRegex(ValueError,'SEMANTIC_INVALID'):
            checked_constraints(replace(new,floor_items=('bed','bed')),PHOTO_SHA256)

    def test_schema_pins_floor_and_named_attachment_choices_but_not_measured_room_size(self):
        request,reference,constraints,_=semantic_inputs()
        schema=layout_schema(request.prompt,reference,observation(),quality_constraints=constraints,revision=PARAMETRIC_REVISION)
        slots=schema['properties']['objects']['properties']
        self.assertEqual(slots['underdesk_bag']['properties']['placement']['properties']['relation']['enum'],['floor'])
        bed=slots['bedding_overhang']['properties']['placement']['anyOf']
        self.assertEqual(len(bed),1)
        self.assertEqual(bed[0]['properties']['parent_id']['enum'],['bed'])
        self.assertEqual(bed[0]['properties']['part']['enum'],['mattress'])
        self.assertNotIn('middle_left',slots['wardrobe']['properties']['region']['enum'])
        self.assertEqual(slots['entry_door']['properties']['region']['enum'],['front_left'])
        self.assertEqual(slots['cables']['properties']['region']['enum'],['front_right'])
        body=build_layout_body(request,observation(),PLANNER_MODEL,reference,quality_constraints=constraints)
        self.assertIn('unmeasured photo plausibility limit',body['messages'][0]['content'])

    def test_independent_compiler_rejects_wrong_clothing_bedding_and_floor_parent(self):
        request,reference,constraints,good=semantic_inputs()
        for identity,relation,parent,part,anchor in (
            ('hanging_clothes','drape','bed','headboard','front'),
            ('bedding_overhang','drape','bed','headboard','front'),
            ('underdesk_bag','surface','desk','top','centre')):
            with self.subTest(identity=identity):
                bad=deepcopy(good);before=canonical_sha256(bad)
                bad['objects'][identity]['placement'].update(relation=relation,parent_id=parent,part=part,anchor=anchor)
                before=canonical_sha256(bad)
                with self.assertRaisesRegex(ValueError,'PHOTO_(ATTACHMENT|FLOOR)_SEMANTIC_MISMATCH'):
                    compile_layout(bad,observation(),request,reference,quality_constraints=constraints)
                self.assertEqual(before,canonical_sha256(bad))

    def test_product_pipeline_repairs_wrong_attachment_once_with_same_schema(self):
        request,reference,constraints,good=semantic_inputs()
        bad=deepcopy(good)
        bad['objects']['bedding_overhang']['placement'].update(part='headboard')
        harness=quality_tests.PhotoQualityGateTests()
        result,error,transport,service=harness.run_pipeline([bad,good],constraints=constraints)
        self.assertIsNone(error)
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(service.diagnostic_snapshot()['repair_count'],1)
        self.assertIn('PHOTO_ATTACHMENT_SEMANTIC_MISMATCH',transport.bodies[-1]['messages'][-1]['content'])
        self.assertEqual(transport.bodies[1]['response_format'],transport.bodies[2]['response_format'])
        self.assertEqual(result.provider_provenance['photo_geometry_quality']['issues'],[])

    def test_accepted_plan_checks_real_drape_and_floor_geometry_not_model_verdict(self):
        request,reference,constraints,value=semantic_inputs()
        payload,_=compile_layout(value,observation(),request,reference,quality_constraints=constraints)
        report=inspect_photo_geometry(payload,constraints.image_sha256,constraints)
        self.assertEqual(report['issues'],[])
        self.assertEqual(report['status'],'PARTIAL')
        bad=deepcopy(payload)
        bag=next(c['arguments'] for c in bad['calls'] if c['arguments']['id']=='underdesk_bag')
        bag['position_m'][2]+=.7
        report=inspect_photo_geometry(bad,constraints.image_sha256,constraints)
        self.assertIn('PHOTO_FLOOR_SEMANTIC_MISMATCH',[i['code'] for i in report['issues']])
        bad=deepcopy(payload)
        cloth=next(c['arguments'] for c in bad['calls'] if c['arguments']['id']=='bedding_overhang')
        cloth['position_m'][0]+=.5
        report=inspect_photo_geometry(bad,constraints.image_sha256,constraints)
        self.assertIn('PHOTO_ATTACHMENT_SEMANTIC_MISMATCH',[i['code'] for i in report['issues']])
        public=public_photo_quality(report)
        self.assertEqual(public['review_revision'],'photo-semantic-review-1.0')
        self.assertIn('PHOTO_ATTACHMENT_SEMANTIC_MISMATCH',json.dumps(public))

    def test_historical_large_room_is_rejected_without_rewriting_saved_plan(self):
        from twinpulse_app.project_store import ProjectStore
        root=Path(__file__).resolve().parents[3]
        path=root/'artifacts/pre-demo-20261008/photo-add10-r4/runtime/active_project.json'
        if not path.is_file():self.skipTest('Local original candidate unavailable')
        before=path.read_bytes();saved=ProjectStore(path).load()
        report=inspect_photo_geometry(saved.site_draft.plan.to_dict(),PHOTO_SHA256,
            reviewed_photo_constraints(PHOTO_SHA256,semantic_review=True))
        self.assertEqual(report['estimated_area_m2'],120.)
        self.assertFalse(report['generation_allowed'])
        self.assertIn('PHOTO_SCALE_REVIEW_REQUIRED',[i['code'] for i in report['issues']])
        self.assertIn('PHOTO_POSITION_MISMATCH',[i['code'] for i in report['issues']])
        self.assertEqual(path.read_bytes(),before)

    def test_scale_repair_can_shrink_unmeasured_room_but_other_repairs_cannot(self):
        # An intentionally scale-only reference isolates the exception to the
        # old immutable footprint rule; furniture/layout details stay separate.
        *_,good=inputs();bad=deepcopy(good)
        bad['room'].update(width_m=10,length_m=12)
        constraints=replace(inputs()[2],max_estimated_area_m2=70.)
        harness=quality_tests.PhotoQualityGateTests()
        result,error,transport,_=harness.run_pipeline([bad,good],constraints=constraints,prompt='Create an estimated bedroom')
        self.assertIsNone(error)
        self.assertEqual(len(transport.bodies),3)
        feedback=json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertIn('PHOTO_SCALE_REVIEW_REQUIRED',json.dumps(feedback['geometry_quality']))
        self.assertEqual(result.provider_provenance['photo_geometry_quality']['room_estimate_m'],[8,8])

    def test_parametric_scale_repair_passes_both_footprint_guards(self):
        _,_,constraints,good=semantic_inputs()
        constraints=replace(constraints,max_estimated_area_m2=70.)
        bad=deepcopy(good);bad['room'].update(width_m=10,length_m=12)
        harness=quality_tests.PhotoQualityGateTests()
        result,error,transport,service=harness.run_pipeline([bad,good],constraints=constraints,
                                                          prompt='Create an estimated bedroom')
        self.assertIsNone(error)
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(service.diagnostic_snapshot()['repair_count'],1)
        self.assertEqual(result.provider_provenance['photo_geometry_quality']['room_estimate_m'],[8,8])
        # A non-scale failure does not authorize shrinking even an unmeasured
        # room, and certainly not enlarging one. Old footprint lock survives.
        wrong=deepcopy(good);wrong['objects']['bedding_overhang']['placement']['part']='headboard'
        smaller=deepcopy(good);smaller['room'].update(width_m=6,length_m=6)
        result,error,transport,_=harness.run_pipeline([wrong,smaller],constraints=constraints,
                                                     prompt='Create an estimated bedroom')
        self.assertIsNone(error)
        self.assertEqual(result.plan.calls[0].arguments['size_m'],[6,6])
        self.assertEqual(len(transport.bodies),3)


if __name__=='__main__':unittest.main()
