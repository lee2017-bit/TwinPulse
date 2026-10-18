# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary schema/lineage checks, not photograph or live-model acceptance."""
from copy import deepcopy
import unittest

from twinpulse_provider import InvalidProviderResponseError
from twinpulse_provider.nebius_pipeline import ObservationArtifact, observation_json_schema
from twinpulse_provider.observation_alignment import unknown_alignment
from twinpulse_provider.observation_instances import checked_observation_instances, expand_observation_instances
from twinpulse_provider.budgeted_pipeline import repair_observation_evidence
from test_observation_support_contract import raw


def aligned(count=1):
    value=raw(count)
    value['schema_version']='1.5'
    for entity in value['entities']:entity['footprint_alignment']=unknown_alignment()
    wall=deepcopy(value['entities'][1])
    wall.update(id='wall_seen',kind='wall',category='wall',description='Separately visible wall')
    value['entities'].append(wall)
    value['entities'][0]['footprint_alignment']=dict(reference_wall_id='wall_seen',
        relation='parallel',confidence=.9,visual_basis='Visible long edge follows the wall base')
    return value


class AlignmentTests(unittest.TestCase):
    def test_metadata_role_rule_is_identical_in_wire_and_host(self):
        from twinpulse_provider.semantic_scene import _shape_issues
        schema=observation_json_schema('1.5')['properties']['entities']['items']
        for role,category,kind in [('structure','wall','wall'),('opening','opening','other'),
                ('free_space','aisle','free_space'),('robot','agv','robot_candidate')]:
            value=aligned();row=value['entities'][0]
            row.update(role=role,category=category,kind=kind)
            # Actual16 rejected metadata alignment pattern; no photo coordinates.
            self.assertTrue(_shape_issues(row,schema))
            with self.assertRaises(InvalidProviderResponseError):ObservationArtifact.from_mapping(value)
            row['footprint_alignment']=unknown_alignment('Metadata has no physical-object footprint axis')
            self.assertFalse(_shape_issues(row,schema))
            self.assertEqual(ObservationArtifact.from_mapping(value).entities[0]['role'],role)

    def test_nested_input_exports_and_repair_evidence_cannot_mutate_verified_artifact(self):
        value=aligned();source=ObservationArtifact.from_mapping(value)
        before=source.to_dict();sha=source.sha256
        value['entities'][0]['footprint_alignment']['relation']='perpendicular'
        exported=source.to_dict();exported['entities'][0]['footprint_alignment']['reference_wall_id']='invented'
        candidate=dict(inventory=[dict(id='item',source=dict(observation_ids=['piece']))])
        evidence=repair_observation_evidence(source,candidate,['item'])
        evidence['entities'][0]['footprint_alignment']['confidence']=0
        self.assertEqual(source.to_dict(),before)
        self.assertEqual(source.sha256,sha)

    def test_new_source_and_derived_versions_preserve_exact_evidence_and_sha(self):
        value=aligned();before=deepcopy(value)
        source=checked_observation_instances(value,expected_version='1.5')
        result,trace=expand_observation_instances(source)
        self.assertEqual(value,before)
        self.assertEqual(source.to_dict(),before)
        self.assertEqual(result.schema_version,'1.6')
        self.assertEqual(result.entities[0]['footprint_alignment'],value['entities'][0]['footprint_alignment'])
        self.assertEqual(trace['source_observation_sha256'],source.sha256)
        self.assertFalse(trace['physical_authority'])
        self.assertEqual(ObservationArtifact.from_mapping(result.to_dict(),allow_derived=True).sha256,result.sha256)
        with self.assertRaises(InvalidProviderResponseError):ObservationArtifact.from_mapping(result.to_dict())
        with self.assertRaises(ValueError):observation_json_schema('1.6')

    def test_legacy_shape_is_not_silently_widened_or_rewritten(self):
        old=raw();source=ObservationArtifact.from_mapping(old)
        result,trace=expand_observation_instances(source)
        self.assertEqual(source.to_dict(),old)
        self.assertEqual(result.schema_version,'1.3')
        self.assertEqual(trace['schema_version'],'observed-instance-expansion-1.4')
        self.assertNotIn('unresolved_alignments',trace)
        self.assertNotIn('footprint_alignment',observation_json_schema('1.4')['properties']['entities']['items']['properties'])
        injected=deepcopy(old);injected['entities'][0]['footprint_alignment']=unknown_alignment()
        with self.assertRaises(InvalidProviderResponseError):ObservationArtifact.from_mapping(injected)
        with self.assertRaisesRegex(InvalidProviderResponseError,'CONTRACT_VERSION_MISMATCH'):
            checked_observation_instances(old,expected_version='1.5')

    def test_invalid_or_invented_wall_and_false_precision_are_rejected(self):
        changes=[dict(reference_wall_id='missing'),dict(reference_wall_id='piece'),
            dict(reference_wall_id='visible_floor'),dict(reference_wall_id=None),
            dict(confidence=0),dict(confidence=True),dict(confidence=float('nan')),
            dict(relation='unknown'),dict(relation='horizontal'),dict(visual_basis='')]
        for change in changes:
            value=aligned();value['entities'][0]['footprint_alignment'].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(InvalidProviderResponseError,'ALIGNMENT_INVALID'):
                ObservationArtifact.from_mapping(value)
        value=aligned();value['entities'][0]['footprint_alignment']=unknown_alignment('Occluded long axis')
        self.assertEqual(ObservationArtifact.from_mapping(value).entities[0]['footprint_alignment']['confidence'],0)

    def test_group_alignment_is_deferred_not_broadcast_to_instances(self):
        source=ObservationArtifact.from_mapping(aligned(3));before=source.to_dict()
        result,trace=expand_observation_instances(source)
        self.assertEqual(len(trace['groups'][0]['instance_ids']),3)
        self.assertEqual(trace['unresolved_alignments'][0]['footprint_alignment'],source.entities[0]['footprint_alignment'])
        for row in result.entities[:3]:
            self.assertEqual(row['footprint_alignment']['relation'],'unknown')
            self.assertIsNone(row['footprint_alignment']['reference_wall_id'])
            self.assertEqual(row['footprint_alignment']['confidence'],0)
        self.assertEqual(source.to_dict(),before)

    def test_compact_repair_retains_referenced_wall_without_granting_scope(self):
        source,_=expand_observation_instances(ObservationArtifact.from_mapping(aligned()))
        candidate=dict(inventory=[dict(id='item',source=dict(observation_ids=['piece']))])
        before=deepcopy(candidate)
        evidence=repair_observation_evidence(source,candidate,['item'])
        self.assertEqual(evidence['selected_observation_ids'],['piece'])
        self.assertIn('wall_seen',[e['id'] for e in evidence['entities']])
        self.assertEqual(evidence['entities'][0]['footprint_alignment'],source.entities[0]['footprint_alignment'])
        self.assertEqual(candidate,before)
        self.assertIn('not measurements or additional edit permission',evidence['instruction'])


if __name__=='__main__':unittest.main()
