# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded, request-local instance expansion; no photo/category lookup or I/O.

Original schema1.2 observations stay immutable. The existing one-object/one-ref
compiler consumes a derived schema1.1/host-only1.3 inventory, with lineage. Group
count is detection evidence, not proof of individual pose, support or size.
"""
from copy import deepcopy
from twinpulse_core import canonical_sha256
from .nebius_pipeline import ObservationArtifact, MAX_OBSERVATION_ENTITIES
from .scene_capacity import OBSERVATION_PAYLOAD_BYTES, checked_payload_bytes
from .errors import ProviderConfigurationError
from .scene_contract import role_of, report, issue, SceneContractError

INSTANCE_REVISION='observed-instance-expansion-1.3'


def checked_observation_instances(value):
    """Validate raw evidence; expansion resources are a host checkpoint boundary.

    Return raw evidence unchanged; derived instances are still separately saved.
    """
    observation=ObservationArtifact.from_mapping(value)
    return observation


def expand_observation_instances(observation):
    source=observation.to_dict()
    trace=dict(schema_version=INSTANCE_REVISION,source_observation_sha256=observation.sha256,
        effective_observation_sha256=observation.sha256,groups=[],unresolved_counts=[],
        unresolved_relations=[],unresolved_dimensions=[],metadata_counts=[],physical_authority=False,
        effective_object_count=sum(role_of(e) in {'object','unknown'} for e in observation.entities),
        status='legacy_count_unverified' if observation.schema_version!='1.2' else 'count_preserved')
    if observation.schema_version!='1.2':return observation,trace
    count=sum((e['instance_count'] or 1) for e in observation.entities
        if role_of(e) in {'object','unknown'})
    metadata_count=sum(role_of(e) not in {'object','unknown'} for e in observation.entities)
    total_count=count+metadata_count
    # Avoid iterating an enormous compressed group. This is a memory bound,
    # not a requirement that the model erase objects or change their counts.
    # Even an empty entity needs bytes; the full source is saved by the caller.
    if total_count * 2 > OBSERVATION_PAYLOAD_BYTES:
        raise ProviderConfigurationError('OBSERVATION_EXPANSION_MEMORY_BUDGET_REACHED')
    result=deepcopy(source)
    result['schema_version']='1.3' if total_count>MAX_OBSERVATION_ENTITIES else '1.1'
    result['entities']=[]
    remaining=OBSERVATION_PAYLOAD_BYTES-checked_payload_bytes(
        {**result,'entities':[]}, OBSERVATION_PAYLOAD_BYTES, 'OBSERVATION_EXPANSION_MEMORY_BUDGET_REACHED')
    def append_entity(row):
        nonlocal remaining
        remaining -= checked_payload_bytes(row, OBSERVATION_PAYLOAD_BYTES,
            'OBSERVATION_EXPANSION_MEMORY_BUDGET_REACHED')+2
        if remaining < 0:
            raise ProviderConfigurationError('OBSERVATION_EXPANSION_MEMORY_BUDGET_REACHED')
        result['entities'].append(row)
    grouped=set();used={e['id'] for e in observation.entities}
    for entity in observation.entities:
        row=deepcopy(entity);quantity=row.pop('instance_count');identity=row['id']
        if role_of(row) not in {'object','unknown'}:
            trace['metadata_counts'].append(dict(observation_id=identity,role=role_of(row),instance_count=quantity))
            append_entity(row)
            continue
        if quantity is None and role_of(row) in {'object','unknown'}:
            trace['unresolved_counts'].append(identity)
        quantity=quantity or 1
        if quantity==1:
            append_entity(row);continue
        grouped.add(identity);instance_ids=[]
        for index in range(1,quantity+1):
            digest=canonical_sha256({'group':identity,'instance':index})[:10]
            derived=identity[:47]+'_i'+str(index)+'_'+digest
            if derived in used:
                raise SceneContractError(report([issue('OBSERVER_INSTANCE_ID_COLLISION','$.entities')]))
            used.add(derived);instance_ids.append(derived)
            instance=deepcopy(row);instance['id']=derived
            # A group region/dimension is not an individual measured pose.
            instance.update(region='unknown',spatial_confidence=0,
                description=(f'Instance {index}/{quantity} of observed group {identity}: '+row['description'])[:256])
            append_entity(instance)
        trace['groups'].append(dict(observed_group_id=identity,instance_count=quantity,
            instance_ids=instance_ids,individual_pose='unverified',support='unverified'))
    for field,key in (('relations','unresolved_relations'),('dimensions','unresolved_dimensions')):
        kept=[]
        for row in source[field]:
            references=([row['subject_id'],row['object_id']] if field=='relations' else [row['target_id']])
            if grouped.intersection(references):trace[key].append(deepcopy(row))
            else:kept.append(deepcopy(row))
        result[field]=kept
    expanded=ObservationArtifact.from_mapping(result,allow_derived=True)
    trace['effective_object_count']=sum(role_of(e) in {'object','unknown'} for e in expanded.entities)
    trace['effective_observation_sha256']=expanded.sha256
    if trace['unresolved_counts']:trace['status']='count_partially_unverified'
    return expanded,trace
