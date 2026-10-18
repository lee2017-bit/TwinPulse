# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline wire/lineage checks, not measured support or live model evidence."""
from copy import deepcopy
import unittest

from twinpulse_provider import InvalidProviderResponseError
from twinpulse_provider.nebius_pipeline import ObservationArtifact, observation_json_schema
from twinpulse_provider.observation_instances import checked_observation_instances, expand_observation_instances
from twinpulse_provider.model_recipe_planning import floor_recipe_allowed


def raw(count=1, relation='on'):
    def entity(identity, kind, role, category, quantity):
        return dict(id=identity, kind=kind, description='Explicit synthetic observation', confidence=.9,
            role=role, category=category, region='middle_centre', spatial_confidence=.9, instance_count=quantity)
    return dict(schema_version='1.4', summary='Synthetic support evidence, unmeasured',
        entities=[entity('piece','static_obstacle','object','unknown',count),
                  entity('visible_floor','floor','structure','floor',1)],
        relations=[dict(subject_id='piece',relation=relation,object_id='visible_floor')],
        dimensions=[],ambiguities=['Contact and dimensions not physically verified'])


class ObservationSupportContractTests(unittest.TestCase):
    def test_new_relation_is_version_bound_and_host_inventory_stays_host_only(self):
        for version in ('1.0','1.1','1.2'):
            schema=observation_json_schema(version)
            self.assertNotIn('on',schema['properties']['relations']['items']['properties']['relation']['enum'])
            old=raw();old['schema_version']=version
            for row in old['entities']:
                if version!='1.2':row.pop('instance_count')
                if version=='1.0':
                    for field in ('role','category','region','spatial_confidence'):row.pop(field)
            with self.assertRaises(InvalidProviderResponseError):ObservationArtifact.from_mapping(old)
        for relation in ('on','supported_by'):
            source=ObservationArtifact.from_mapping(raw(relation=relation));before=source.to_dict()
            effective,trace=expand_observation_instances(source)
            self.assertEqual(effective.schema_version,'1.3')
            self.assertEqual(effective.relations,source.relations)
            self.assertEqual(source.to_dict(),before)
            self.assertEqual(trace['source_observation_sha256'],source.sha256)
            self.assertEqual(trace['effective_object_count'],1)
            self.assertFalse(trace['physical_authority'])
            self.assertEqual(ObservationArtifact.from_mapping(effective.to_dict(),allow_derived=True).sha256,effective.sha256)
            with self.assertRaises(InvalidProviderResponseError):ObservationArtifact.from_mapping(effective.to_dict())
        with self.assertRaises(ValueError):observation_json_schema('1.3')

    def test_group_support_is_retained_unresolved_not_copied_to_instances(self):
        for count in (3,30):
            source=ObservationArtifact.from_mapping(raw(count))
            effective,trace=expand_observation_instances(source)
            self.assertEqual(effective.schema_version,'1.3')
            self.assertEqual(len(effective.entities),count+1)
            self.assertEqual(trace['effective_object_count'],count)
            self.assertFalse(effective.relations)
            self.assertEqual(trace['unresolved_relations'],list(source.relations))
            self.assertEqual(len(trace['groups'][0]['instance_ids']),count)
            for identity in trace['groups'][0]['instance_ids']:
                row=dict(kind='unknown',source=dict(basis='observed',observation_ids=[identity]))
                self.assertFalse(floor_recipe_allowed(row,effective))
        source=ObservationArtifact.from_mapping(raw(None))
        _,trace=expand_observation_instances(source)
        self.assertEqual(trace['unresolved_counts'],['piece'])
        self.assertEqual(trace['status'],'count_partially_unverified')

    def test_only_observed_floor_support_unlocks_existing_recipe_guard(self):
        row=dict(kind='unknown',source=dict(basis='observed',observation_ids=['piece']))
        before=deepcopy(row)
        self.assertTrue(floor_recipe_allowed(row,ObservationArtifact.from_mapping(raw())))
        self.assertFalse(floor_recipe_allowed(row,ObservationArtifact.from_mapping(raw(relation='near'))))
        furniture=raw();furniture['entities'][1].update(kind='static_obstacle',role='object',category='desk')
        self.assertFalse(floor_recipe_allowed(row,ObservationArtifact.from_mapping(furniture)))
        self.assertEqual(row,before)  # No automatic reparent, proxy change or recipe creation.

    def test_fresh_wire_version_pin_rejects_silent_downgrade_but_legacy_reader_survives(self):
        value=raw(relation='near');value['schema_version']='1.2'
        self.assertEqual(ObservationArtifact.from_mapping(value).schema_version,'1.2')
        with self.assertRaisesRegex(InvalidProviderResponseError,'OBSERVER_CONTRACT_VERSION_MISMATCH'):
            checked_observation_instances(value,expected_version='1.4')
        self.assertEqual(checked_observation_instances(raw(),expected_version='1.4').schema_version,'1.4')
        old=ObservationArtifact.from_mapping(value)
        effective,trace=expand_observation_instances(old)
        self.assertEqual(effective.schema_version,'1.1')  # Existing small legacy inventory unchanged.
        self.assertEqual(trace['source_observation_sha256'],old.sha256)


if __name__=='__main__':unittest.main()
