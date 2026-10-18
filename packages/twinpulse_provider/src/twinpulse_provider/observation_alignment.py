# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Source wall-relative evidence, never a calibrated world pose or edit grant."""
import math

from .errors import InvalidProviderResponseError

ALIGNMENT_INSTRUCTIONS = (
    'footprint_alignment compares the object horizontal footprint LONG axis with the horizontal '
    'direction ALONG the referenced visible wall, not its normal, object height or an image horizontal line. '
    'Preserve parallel/perpendicular/oblique evidence and its visual basis when choosing approximate '
    'dimensions and yaw. Establish wall/view correspondence first; do not convert a photo wall into '
    'world X/Y by its name or image region. Unknown correspondence stays uncertain, not measured. '
    'Do not invent a long axis for a square, round or occluded footprint. '
)


def unknown_alignment(basis='Individual long axis not established'):
    return dict(reference_wall_id=None, relation='unknown', confidence=0, visual_basis=basis)


def alignment_schema(*, unknown_only=False):
    schema=dict(type='object', additionalProperties=False,
        required=['reference_wall_id','relation','confidence','visual_basis'], properties={
            'reference_wall_id':dict(type=['string','null'],maxLength=64),
            'relation':dict(enum=['parallel','perpendicular','oblique','unknown']),
            'confidence':dict(type='number',minimum=0,maximum=1),
            'visual_basis':dict(type='string',minLength=1,maxLength=180)})
    if unknown_only:
        schema['properties'].update(reference_wall_id=dict(type='null'),relation=dict(enum=['unknown']),
            confidence=dict(type='number',enum=[0]))
    return schema


def check_alignments(entities):
    """Keep exact source values; reject broken refs without manufacturing a pose."""
    by_id={e['id']:e for e in entities}
    for entity in entities:
        value=entity.get('footprint_alignment')
        valid=isinstance(value,dict) and set(value)=={
            'reference_wall_id','relation','confidence','visual_basis'}
        if valid:
            ref=value['reference_wall_id'];relation=value['relation'];confidence=value['confidence']
            basis=value['visual_basis']
            valid=(relation in ('parallel','perpendicular','oblique','unknown')
                and type(confidence) in (int,float) and math.isfinite(confidence) and 0<=confidence<=1
                and isinstance(basis,str) and 1<=len(basis)<=180)
            if relation=='unknown':valid=valid and ref is None and confidence==0
            else:
                wall=by_id.get(ref) if isinstance(ref,str) else None
                valid=(valid and confidence>0 and ref!=entity['id'] and wall is not None
                    and wall.get('role')=='structure' and wall.get('category')=='wall'
                    and entity.get('role') in ('object','unknown'))
        if not valid:
            from .scene_contract import report, issue
            error=InvalidProviderResponseError('OBSERVER_FOOTPRINT_ALIGNMENT_INVALID')
            error.code='OBSERVER_FOOTPRINT_ALIGNMENT_INVALID'
            error.contract_report=report([issue(error.code,'$.entities.'+entity['id']+'.footprint_alignment',
                expected='Wall-relative horizontal long axis or explicit unknown; no world pose')])
            raise error


def referenced_walls(entities):
    return {e.get('footprint_alignment',{}).get('reference_wall_id') for e in entities
        if e.get('footprint_alignment',{}).get('reference_wall_id') is not None}
