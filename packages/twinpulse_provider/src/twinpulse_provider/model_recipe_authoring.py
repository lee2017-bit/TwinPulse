# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Finite authoring notation compiled to the unchanged canonical recipe.

This is not a renderer, a legacy migration or correction of invalid answers.
Original authoring bytes remain in the request/validation evidence. Registered
models and scenes contain the ordinary checked compiler-1.1 recipe/SHA.
"""
from copy import deepcopy
from twinpulse_core.model_recipe import (recipe_schema, checked_recipe, ModelRecipeError,
    RECIPE_VERSION, INTERPRETER_VERSION, KINDS, MATERIALS)

AUTHORING_VERSION='proportional-boxes-1.0'


def proportional_schema(kind=None):
    def bounds(low,high):
        return dict(type='array',minItems=2,maxItems=2,items=dict(type='number',minimum=low,maximum=high))
    parameter=dict(type='object',additionalProperties=False,
        required=['name','type','minimum','maximum','default'],properties=dict(
            name={'enum':['width','depth','height']},type={'const':'number'},
            minimum=dict(type='number',exclusiveMinimum=0,maximum=10),
            maximum=dict(type='number',exclusiveMinimum=0,maximum=10),
            default=dict(type='number',exclusiveMinimum=0,maximum=10)))
    fields=dict(id=dict(type='string',pattern='^[a-z][a-z0-9_]{0,23}$'),
        x_bounds=bounds(-.5,.5),y_bounds=bounds(-.5,.5),z_bounds=bounds(0,1),
        material={'enum':list(MATERIALS)},support_top=dict(type='boolean'))
    properties=dict(authoring_version={'const':AUTHORING_VERSION},
        title=dict(type='string',minLength=1,maxLength=100),family={'enum':['home','warehouse','common']},
        kind={'const':kind} if kind else {'enum':list(KINDS)},
        parameters=dict(type='array',minItems=3,maxItems=3,items=parameter),
        parts=dict(type='array',minItems=1,maxItems=64,items=dict(type='object',
            additionalProperties=False,required=list(fields),properties=fields)))
    return dict(type='object',additionalProperties=False,required=list(properties),properties=properties)


def authoring_schema(kind):
    legacy=recipe_schema();legacy['properties']['kind']={'const':kind}
    return {'anyOf':[proportional_schema(kind),legacy]}


def compile_authoring(value):
    """Translate only the explicit new notation, then use every original check."""
    if not isinstance(value,dict) or 'authoring_version' not in value:
        return checked_recipe(value)  # Existing recipes are never rewritten.
    from .semantic_scene import _shape_issues
    issues=_shape_issues(value,proportional_schema())
    if issues:raise ModelRecipeError('MODEL_AUTHORING_CONTRACT_INVALID',detail=str(issues))
    if {p['name'] for p in value['parameters']}!={'width','depth','height'}:
        raise ModelRecipeError('MODEL_AUTHORING_ENVELOPE_REQUIRED','$.parameters')
    parts=[]
    for index,part in enumerate(value['parts']):
        center=[];size=[]
        for axis,parameter in zip('xyz',('width','depth','height')):
            low,high=part[axis+'_bounds']
            if not low<high:
                raise ModelRecipeError('MODEL_AUTHORING_BOUNDS_INVALID',f'$.parts[{index}].{axis}_bounds',
                    'Require strictly increasing normalized bounds; no clamping or inversion is performed.')
            center.append(dict(op='mul',args=[parameter,(low+high)/2]))
            size.append(dict(op='mul',args=[parameter,high-low]))
        parts.append(dict(id=part['id'],center=center,size=size,material=part['material'],
            support_top=part['support_top'],repeat=None))
    return checked_recipe(dict(schema_version=RECIPE_VERSION,interpreter_version=INTERPRETER_VERSION,
        title=value['title'],family=value['family'],kind=value['kind'],
        parameters=deepcopy(value['parameters']),parts=parts))
