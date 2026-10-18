# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic count preservation through existing generation/compiler; no paid calls."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
import test_budgeted_generation as fixtures
from twinpulse_provider.observation_alignment import unknown_alignment
from twinpulse_provider import GenerationService,ImageInput,InvalidProviderResponseError
from twinpulse_provider.nebius_pipeline import ObservationArtifact,observation_json_schema
from twinpulse_provider.observation_instances import expand_observation_instances
from twinpulse_provider.semantic_scene import checked_structure
from twinpulse_provider.semantic_bindings import evidence_catalog
from twinpulse_provider.scene_contract import SceneContractError,ground_layout,GROUNDING_REVISION
from twinpulse_provider.generation_store import input_digest
from twinpulse_app.generation_scope import OrdinaryInferenceScope
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_core import canonical_sha256


def grouped(count=3,category='chair',identity='visible_group'):
    return dict(schema_version='1.2',summary='Synthetic bounded observation',
        entities=[dict(id=identity,kind='static_obstacle',description='A visible group',confidence=.9,
            role='object',category=category,region='middle_left',spatial_confidence=.9,instance_count=count)],
        relations=[],dimensions=[],ambiguities=['Individual poses are unmeasured'])


class InstanceTests(unittest.TestCase):
    def provider(self,transport,**kwargs):return fixtures.PipelineTests.provider(self,transport,**kwargs)

    def test_current_observer_prompt_does_not_reintroduce_old_count_quota(self):
        from twinpulse_provider import ImageInput
        from dataclasses import replace
        request=replace(fixtures.text_request('Estimate visible objects'),
            images=(ImageInput('room.jpg','image/jpeg',b'image'),))
        provider=self.provider(fixtures.FixtureTransport([]))
        provider.site_plan_version='2.2'
        body=provider.build_observer_body(request)
        prompt=body['messages'][0]['content']
        self.assertNotIn('at most 24 entities',prompt)
        self.assertIn('no object-count quota',prompt)
        self.assertIn('Record it separately',prompt)

    def test_repair_keeps_original_target_and_linked_evidence_without_granting_scope(self):
        from twinpulse_provider.budgeted_pipeline import repair_observation_evidence
        raw=grouped(1,category='box',identity='box_seen')
        parent=deepcopy(raw['entities'][0]);parent.update(id='table_seen',category='desk')
        other=deepcopy(parent);other.update(id='unrelated')
        raw['entities'] += [parent,other]
        raw['relations']=[dict(subject_id='box_seen',relation='near',object_id='table_seen')]
        observation=ObservationArtifact.from_mapping(raw)
        candidate=dict(inventory=[dict(id='box',source=dict(observation_ids=['box_seen']))])
        before=deepcopy(candidate)
        evidence=repair_observation_evidence(observation,candidate,['box'])
        self.assertEqual(evidence['selected_observation_ids'],['box_seen'])
        self.assertEqual([r['id'] for r in evidence['entities']],['box_seen','table_seen'])
        self.assertEqual(evidence['source_observation_sha256'],canonical_sha256(observation.to_dict()))
        self.assertEqual(candidate,before)

    def test_expanded_inventory_preserves_counts_above_old_global_cap(self):
        for total in (25,32,33,60,100):
            raw=grouped(24);other=deepcopy(raw['entities'][0]);other.update(id='other',instance_count=total-24)
            raw['entities'].append(other)
            for i in range(4):
                shell=deepcopy(other);shell.update(id='shell_'+str(i),kind='wall',role='structure',category='wall',instance_count=1)
                raw['entities'].append(shell)
            source=ObservationArtifact.from_mapping(raw);before=source.to_dict()
            effective,trace=expand_observation_instances(source)
            self.assertEqual(trace['effective_object_count'],total)
            self.assertEqual(len(effective.entities),total+4)
            self.assertEqual(source.to_dict(),before)
            expanded_ids={identity for group in trace['groups'] for identity in group['instance_ids']}
            self.assertTrue(all(e['region']=='unknown' for e in effective.entities if e['id'] in expanded_ids))
            request=fixtures.text_request('Estimate these observed chairs')
            structure=dict(summary='Estimated',room=dict(width_m=12,length_m=12,height_m=2.6),
                inventory=[dict(id='item_'+str(i),kind='chair',evidence_ref='seen:'+e['id'])
                    for i,e in enumerate(effective.entities) if e['role']=='object'])
            self.assertEqual(len(checked_structure(structure,request,effective,bound=True)['inventory']),total)

    def test_invalid_count_is_repaired_without_inventing_or_dropping_valid_objects(self):
        raw=grouped(24);raw['schema_version']='1.5'
        for row in raw['entities']:row['footprint_alignment']=unknown_alignment()
        other=deepcopy(raw['entities'][0]);other.update(id='other',instance_count=9,region='unknown',spatial_confidence=0)
        raw['entities'].append(other);raw['entities'][0]['instance_count']=0
        corrected=deepcopy(raw);corrected['entities'][0]['instance_count']=2;corrected['entities'][1]['instance_count']=1
        source=ObservationArtifact.from_mapping(corrected);effective,_=expand_observation_instances(source)
        ids=['seat_a','seat_b','seat_c']
        structure=dict(summary='Estimated chairs',room=dict(width_m=8,length_m=8,height_m=2.6),
            inventory=[dict(id=i,kind='chair',evidence_ref='seen:'+e['id']) for i,e in zip(ids,effective.entities)])
        objects={i:dict(region=r,yaw_deg=0,model_id='common.chair',dimensions_m=[.5,.5,.9],
            variant='standard',finish='natural',placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
            for i,r in zip(ids,['rear_left','rear_right','front_centre'])}
        transport=fixtures.FixtureTransport([raw,corrected,structure,objects])
        request=replace(fixtures.text_request('Estimate the chairs'),images=(ImageInput('fixture.jpg','image/jpeg',b'explicit-offline-fixture'),))
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,store_root=folder)
            result=asyncio.run(GenerationService(provider,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(cp['source_observation'],corrected)
        self.assertEqual(result.provider_provenance['budget']['requests'],4)
        self.assertEqual(result.provider_provenance['budget']['repairs'],1)
        content=transport.bodies[1]['messages'][-1]['content']
        feedback=json.loads(content[-1]['text'] if isinstance(content,list) else content)
        self.assertEqual(feedback['previous_candidate'],raw)
        self.assertIn('INSTANCE_COUNT_INVALID',str(feedback))
        self.assertEqual(len(result.plan.to_dict()['calls'])>3,True)


    def test_counts_expand_distinct_refs_and_do_not_invent_individual_poses(self):
        for category in ('chair','box','basket','unknown'):
            source=ObservationArtifact.from_mapping(grouped(3,category,'observed_'+category));before=source.to_dict()
            effective,trace=expand_observation_instances(source)
            self.assertEqual(source.to_dict(),before)
            self.assertEqual(len(effective.entities),3)
            self.assertEqual(len({row['id'] for row in effective.entities}),3)
            self.assertTrue(all(row['category']==category and row['region']=='unknown' and
                row['spatial_confidence']==0 for row in effective.entities))
            self.assertEqual(trace['source_observation_sha256'],source.sha256)
            self.assertNotEqual(effective.sha256,source.sha256)
            self.assertEqual(trace['groups'][0]['instance_count'],3)
            request=fixtures.text_request('Estimate these objects')
            refs=evidence_catalog(request,effective)
            self.assertEqual(len([r for r in refs if r['ref'].startswith('seen:')]),3)

    def test_unknown_counts_legacy_and_group_relations_stay_unverified(self):
        unknown=ObservationArtifact.from_mapping(grouped(None))
        effective,trace=expand_observation_instances(unknown)
        self.assertEqual(len(effective.entities),1)
        self.assertEqual(trace['unresolved_counts'],['visible_group'])
        old=deepcopy(effective.to_dict());legacy=ObservationArtifact.from_mapping(old)
        unchanged,trace=expand_observation_instances(legacy)
        self.assertEqual(unchanged.to_dict(),old)
        self.assertEqual(trace['status'],'legacy_count_unverified')
        raw=grouped(2);other=deepcopy(raw['entities'][0]);other.update(id='other',instance_count=1)
        raw['entities'].append(other)
        raw['relations']=[dict(subject_id='visible_group',relation='left_of',object_id='other')]
        raw['dimensions']=[dict(target_id='visible_group',dimension='width',value_m=2,confidence=.9)]
        effective,trace=expand_observation_instances(ObservationArtifact.from_mapping(raw))
        self.assertFalse(effective.relations);self.assertFalse(effective.dimensions)
        self.assertEqual(len(trace['unresolved_relations']),1)
        self.assertEqual(len(trace['unresolved_dimensions']),1)

    def test_bad_count_overflow_and_duplicate_seen_refs_are_not_silently_accepted(self):
        for count in (0,-1,True,1.5,'3'):
            with self.subTest(count=count),self.assertRaises(InvalidProviderResponseError):
                ObservationArtifact.from_mapping(grouped(count))
        raw=grouped(32);other=deepcopy(raw['entities'][0]);other.update(id='other',instance_count=1)
        raw['entities'].append(other)
        effective,trace=expand_observation_instances(ObservationArtifact.from_mapping(raw))
        self.assertEqual(trace['effective_object_count'],33)
        self.assertEqual(len(effective.entities),33)
        effective,_=expand_observation_instances(ObservationArtifact.from_mapping(grouped(2)))
        request=fixtures.text_request('Estimate this group')
        structure=dict(summary='Estimated',room=dict(width_m=6,length_m=6,height_m=2.6),
            inventory=[dict(id='a',kind='chair',evidence_ref='seen:'+effective.entities[0]['id'])])
        with self.assertRaisesRegex(SceneContractError,'OBSERVED_ITEMS_MISSING'):
            checked_structure(structure,request,effective,bound=True)
        structure['inventory']*=2;structure['inventory'][1]=dict(structure['inventory'][0],id='b')
        with self.assertRaisesRegex(SceneContractError,'OBSERVATION_DUPLICATED'):
            checked_structure(structure,request,effective,bound=True)

    def test_shell_metadata_does_not_consume_object_instance_capacity(self):
        raw=grouped(20)
        for index in range(8):
            raw['entities'].append(dict(id='shell_'+str(index),kind='wall',description='Synthetic shell metadata',
                confidence=.8,role='structure',category='wall',region='rear_centre',
                spatial_confidence=.8,instance_count=1))
        source=ObservationArtifact.from_mapping(raw);before=source.to_dict()
        effective,trace=expand_observation_instances(source)
        self.assertEqual(source.to_dict(),before)
        self.assertEqual(len(effective.entities),28)
        self.assertEqual(trace['effective_object_count'],20)
        self.assertEqual(len([e for e in effective.entities if e['role']=='structure']),8)
        self.assertEqual(effective.schema_version,'1.3')
        # Derived host inventory cannot be supplied as a new raw LLM response.
        with self.assertRaises(InvalidProviderResponseError):
            ObservationArtifact.from_mapping(effective.to_dict())
        reopened=ObservationArtifact.from_mapping(effective.to_dict(),allow_derived=True)
        self.assertEqual(reopened.sha256,effective.sha256)
        legacy=deepcopy(effective.to_dict());legacy['schema_version']='1.1'
        self.assertEqual(len(ObservationArtifact.from_mapping(legacy).entities),28)

    def test_memory_is_bounded_but_metadata_and_inventory_have_no_count_quota(self):
        effective,_=expand_observation_instances(ObservationArtifact.from_mapping(grouped(32)))
        raw=effective.to_dict();raw['schema_version']='1.3'
        row=deepcopy(raw['entities'][0]);row['id']='excess_object';raw['entities'].append(row)
        self.assertEqual(len(ObservationArtifact.from_mapping(raw,allow_derived=True).entities),33)
        raw['entities']=raw['entities'][:1]
        for index in range(25):
            raw['entities'].append(dict(id='wall_'+str(index),kind='wall',description='Shell',
                confidence=.8,role='structure',category='wall',region='rear_centre',spatial_confidence=.8))
        self.assertEqual(len(ObservationArtifact.from_mapping(raw,allow_derived=True).entities),26)
        with self.assertRaises(ValueError):observation_json_schema('1.3')
        source=grouped(1)
        for index in range(24):
            row=deepcopy(source['entities'][0]);row['id']='object_'+str(index);source['entities'].append(row)
        self.assertEqual(len(ObservationArtifact.from_mapping(source).entities),25)
        from twinpulse_provider import ProviderConfigurationError
        from twinpulse_provider.scene_capacity import checked_payload_bytes
        with self.assertRaisesRegex(ProviderConfigurationError,'MEMORY_BUDGET'):
            expand_observation_instances(ObservationArtifact.from_mapping(grouped(10**9)))
        with self.assertRaisesRegex(ProviderConfigurationError,'RESOURCE_TEST'):
            checked_payload_bytes({'entities':['x'*100]},40,'RESOURCE_TEST')
        self.assertNotIn('maxItems',observation_json_schema('1.2')['properties']['entities'])

    def test_approved_checkpoint_reopens_expanded_inventory_without_reobserving(self):
        raw=grouped(20)
        raw['schema_version']='1.5'
        for index in range(8):
            raw['entities'].append(dict(id='shell_'+str(index),kind='wall',description='Synthetic shell',
                confidence=.8,role='structure',category='wall',region='rear_centre',
                spatial_confidence=.8,instance_count=1))
        for row in raw['entities']:row['footprint_alignment']=unknown_alignment()
        source=ObservationArtifact.from_mapping(raw);obs,trace=expand_observation_instances(source)
        request=replace(fixtures.text_request('A synthetic estimated room with all observed chairs',identity='derived-parent'),
            images=(ImageInput('synthetic.jpg','image/jpeg',b'explicit-offline-fixture'),))
        structure=dict(summary='Estimated inventory',room=dict(width_m=8,length_m=8,height_m=2.6),
            inventory=[dict(id='seat_'+str(i),kind='chair',evidence_ref='seen:'+row['id'])
                for i,row in enumerate(obs.entities) if row['role']=='object'])
        checked=checked_structure(structure,request,obs,bound=True)
        grounded=ground_layout(dict(layout_version=GROUNDING_REVISION,summary=checked['summary'],
            room=checked['room'],objects=checked['inventory']),obs,request)[2]
        self.assertEqual(grounded['category_validation'],'TYPED_OBSERVATION')
        partial=fixtures.ChatCompletion('length',fixtures.PLANNER_MODEL,'','length',{})
        with TemporaryDirectory() as folder:
            root=Path(folder);provider=self.provider(fixtures.FixtureTransport([source.to_dict(),structure,partial]),store_root=root/'store')
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(provider,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
            key=provider.diagnostic_for(request.request_id)['checkpoint_id'];parent=provider.store.read('checkpoint',key)
            self.assertEqual(parent['observation'],obs.to_dict());self.assertEqual(parent['instance_grounding'],trace)
            self.assertEqual(len(parent['draft']['inventory']),20)
            rate=dict(input_per_million=1,output_per_million=1,context_tokens=40000,source='fixture-not-live')
            scope=OrdinaryInferenceScope('ordinary-generation:derived-resume',input_digest(request),'b'*64,
                GenerationPolicy().sha256,root/'new-ledger.json',{fixtures.PLANNER_MODEL:rate},'1',12,
                approved_checkpoint_sha256=canonical_sha256(parent))
            transport=fixtures.FixtureTransport([partial])
            resumed=self.provider(transport,store_root=root/'store',route_sha256='b'*64)
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(resumed,fixtures.config(timeout_s=300),plan_version='2.2').generate(
                    replace(request,request_id='derived-resumed',inference_scope=scope,continuation_checkpoint=key)))
            self.assertEqual([b['response_format']['json_schema']['name'] for b in transport.bodies],['twinpulse_semantic_batch'])
            self.assertEqual(provider.store.read('checkpoint',key),parent)
            self.assertEqual(resumed._budget.snapshot()['cumulative_requests'],4)

    def test_observer_wire_requests_count_and_product_preserves_all_instances(self):
        raw=grouped(3);raw['schema_version']='1.5'
        for row in raw['entities']:row['footprint_alignment']=unknown_alignment()
        source=ObservationArtifact.from_mapping(raw);obs,trace=expand_observation_instances(source)
        schema=observation_json_schema('1.5')['properties']['entities']['items']
        schema=schema['anyOf'][0]  # Physical-object branch; metadata has explicit unknown alignment.
        self.assertIn('instance_count',schema['required'])
        request=replace(fixtures.text_request('An estimated room with these chairs'),
            images=(ImageInput('synthetic.jpg','image/jpeg',b'explicit-offline-fixture'),))
        ids=['seat_a','seat_b','seat_c']
        structure=dict(summary='Estimated chairs',room=dict(width_m=8,length_m=8,height_m=2.6),
            inventory=[dict(id=i,kind='chair',evidence_ref='seen:'+row['id']) for i,row in zip(ids,obs.entities)])
        objects={i:dict(region=r,yaw_deg=0,model_id='common.chair',dimensions_m=[.5,.5,.9],
            variant='standard',finish='natural',placement=dict(relation='floor',parent_id=None,
                part=None,anchor='centre',elevation_m=None)) for i,r in zip(ids,['rear_left','rear_right','front_centre'])}
        transport=fixtures.FixtureTransport([source.to_dict(),structure,objects])
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,store_root=folder)
            result=asyncio.run(GenerationService(provider,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(cp['source_observation'],source.to_dict())
        self.assertEqual(cp['instance_grounding'],trace)
        self.assertEqual(len(cp['draft']['objects']),3)
        self.assertEqual(result.provider_provenance['budget']['requests'],3)
        self.assertEqual(result.provider_provenance['budget']['repairs'],0)
        content=json.loads(transport.bodies[1]['messages'][-1]['content'])
        self.assertEqual(len(content['required_inventory']),3)
        self.assertTrue(result.provider_provenance['checks_complete'])
        self.assertEqual(len([row for row in result.plan.to_dict()['calls'] if row['tool']=='place_furniture']),3)

if __name__=='__main__':unittest.main()
