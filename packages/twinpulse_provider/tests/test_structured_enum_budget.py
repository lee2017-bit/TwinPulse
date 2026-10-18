# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exact reusable wire schemas, no provider calls or private-photo answers."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from twinpulse_provider.stage_transport import (compact_repeated_enum_schemas,
    compact_schema_subtrees,explicit_json_contract,normalize_json_schema,openai_observer_body)
from twinpulse_provider.errors import ProviderConfigurationError


def count_enums(node):
    if isinstance(node,dict):return len(node.get('enum',[]))+sum(count_enums(c) for c in node.values())
    if isinstance(node,list):return sum(count_enums(c) for c in node)
    return 0


def expand_refs(node,root):
    if isinstance(node,dict):
        if '$ref' in node:
            name=node['$ref'].removeprefix('#/$defs/')
            return expand_refs(root['$defs'][name],root)
        value={key:expand_refs(child,root) for key,child in node.items() if key!='$defs'}
        alternatives=value.get('anyOf',[])
        if alternatives and all(isinstance(row,dict) and len(row.get('enum',[]))==1 for row in alternatives):
            base={key:child for key,child in alternatives[0].items() if key!='enum'}
            if all({key:child for key,child in row.items() if key!='enum'}==base for row in alternatives):
                return {**base,'enum':[row['enum'][0] for row in alternatives]}
        return value
    if isinstance(node,list):return [expand_refs(child,root) for child in node]
    return node


class EnumBudgetTests(unittest.TestCase):
    def test_property_maps_and_instance_annotations_are_never_schema_refs(self):
        bindings=dict(type='object',additionalProperties=False,required=['child_a','child_b'],
            properties={i:dict(type='string',maxLength=32,description='A real support panel name, not null')
                for i in ('child_a','child_b')})
        branch=dict(type='object',properties=dict(support_bindings=bindings),required=['support_bindings'],additionalProperties=False)
        original=dict(type='object',properties=dict(first=branch,second=deepcopy(branch)),
            examples=[dict(properties=deepcopy(bindings['properties']),const='instance literal')])
        compact=compact_schema_subtrees(original)
        def assert_maps(schema):
            if not isinstance(schema,dict):return
            for name in ('properties','patternProperties'):
                if name in schema:
                    self.assertNotIn('$ref',schema[name])
                    for value in schema[name].values():assert_maps(value)
            for name in ('anyOf','allOf','oneOf'):
                for value in schema.get(name,[]):assert_maps(value)
        assert_maps(compact)
        for value in compact.get('$defs',{}).values():assert_maps(value)
        self.assertEqual(compact['examples'],original['examples'])
        self.assertEqual(expand_refs(compact,compact),original)

    def test_property_named_enum_or_const_is_not_a_schema_keyword(self):
        original=dict(type='object',properties={'enum':{'const':'literal'},'const':{'enum':[None,'ok']}},
            examples=[{'const':'do not normalize instance data','enum':['literal']}])
        normalized=normalize_json_schema(original)
        self.assertEqual(normalized['properties']['enum'],{'enum':['literal'],'type':'string'})
        self.assertEqual(normalized['examples'],original['examples'])
    def schema(self):
        fields={f'object_{i}':{'type':'string','enum':[f'model_{j}' for j in range(51)]} for i in range(20)}
        return {'type':'object','additionalProperties':False,'required':list(fields),'properties':fields}

    def test_more_than_1000_repeated_values_preserve_every_constraint(self):
        original=self.schema();before=deepcopy(original)
        self.assertEqual(count_enums(original),1020)
        compact=compact_repeated_enum_schemas(original)
        self.assertEqual(count_enums(compact),51)
        self.assertEqual(expand_refs(compact,compact),original)
        self.assertEqual(original,before)
        self.assertEqual(compact_repeated_enum_schemas(compact),compact)

    def test_unique_overflow_is_rejected_before_any_dispatch(self):
        schema=self.schema()
        for i,row in enumerate(schema['properties'].values()):row['enum']=[f'unique_{i}_{j}' for j in range(51)]
        with self.assertRaisesRegex(ProviderConfigurationError,'1020 enum values'):
            compact_repeated_enum_schemas(schema)

    def test_overlapping_nonidentical_id_lists_remain_exact(self):
        schema=self.schema()
        for i,row in enumerate(schema['properties'].values()):row['enum']=[f'id_{j}' for j in range(60) if j!=i]
        compact=compact_repeated_enum_schemas(schema)
        self.assertEqual(count_enums(compact),60)
        self.assertEqual(expand_refs(compact,compact),schema)

    def test_wire_stays_strict_and_existing_definitions_are_retained(self):
        schema=self.schema();schema['$defs']={'existing':{'type':'integer','minimum':0}}
        body={'model':'gpt-6-luna','max_tokens':20000,'temperature':0,'messages':[],
              'response_format':{'type':'json_schema','json_schema':{'name':'patch','strict':True,'schema':schema}}}
        wire=openai_observer_body(body,reasoning_effort='none')
        self.assertTrue(wire['response_format']['json_schema']['strict'])
        self.assertEqual(wire['response_format']['json_schema']['schema']['$defs']['existing'],schema['$defs']['existing'])
        self.assertEqual(wire['max_completion_tokens'],20000)
        self.assertEqual(wire['reasoning_effort'],'none')
        self.assertNotIn('temperature',wire)

    def test_numeric_and_nullable_enums_keep_equivalent_types(self):
        schema={'type':'object','properties':{'a':{'enum':[None,0,90]},'b':{'enum':[None,0,90]}},
                'required':['a','b'],'additionalProperties':False}
        normalized=normalize_json_schema(schema)
        compact=compact_repeated_enum_schemas(normalized)
        self.assertEqual(expand_refs(compact,compact),normalized)

    def test_repeated_object_prompt_is_compact_exact_and_does_not_change_wire_grammar(self):
        branch={'type':'object','additionalProperties':False,'required':['region','placement'],
            'properties':{'region':{'type':'string','enum':['rear_left','rear_right','middle_centre']},
                'placement':{'type':'object','additionalProperties':False,'required':['parent_id','anchor'],
                    'properties':{'parent_id':{'type':['string','null']},'anchor':{'enum':['centre','left','right']}}}}}
        schema={'type':'object','additionalProperties':False,'required':[f'id_{i}' for i in range(6)],
            'properties':{f'id_{i}':deepcopy(branch) for i in range(6)}}
        body={'model':'fixture','messages':[{'role':'system','content':'Host instructions'}],
            'response_format':{'type':'json_schema','json_schema':{'name':'objects','strict':True,'schema':schema}}}
        original=deepcopy(body)
        wire=explicit_json_contract(body)
        normalized=normalize_json_schema(schema)
        prompt=json.loads(wire['messages'][0]['content'].split('\nResponse JSON Schema:\n')[1])
        self.assertEqual(expand_refs(prompt,prompt),normalized)
        self.assertEqual(wire['response_format']['json_schema']['schema'],normalized)
        self.assertLess(len(json.dumps(prompt)),len(json.dumps(normalized)))
        self.assertEqual(explicit_json_contract(wire),wire)
        self.assertEqual(body,original)
        self.assertEqual(compact_schema_subtrees(prompt),prompt)


if __name__=='__main__':unittest.main()
