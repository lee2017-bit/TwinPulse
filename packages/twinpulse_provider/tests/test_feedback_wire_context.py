# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Request-bound feedback identities, offline; no model or engine acceptance."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app','twinpulse_robot'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_core import canonical_sha256
from twinpulse_provider.scene_edit_provider import feedback_proposal_json_schema
from twinpulse_provider.stage_transport import explicit_json_contract
from twinpulse_app.scene_changes import SceneChangeHistory
from twinpulse_app.scene_edit_proposals import feedback_edit_context
from tests.integration.test_dependency_scene_changes import partial_source,edit,preview,adopt,item,relation


def wire(context):
    return explicit_json_contract(dict(response_format=dict(type='json_schema',json_schema=dict(
        name='twinpulse_scene_feedback',strict=True,schema=feedback_proposal_json_schema(context))),
        messages=[dict(role='system',content='Bounded proposal only.')]))['response_format']['json_schema']['schema']


def edits(schema):
    return schema['properties']['patch']['anyOf'][0]['properties']['edits']['items']['anyOf']


class FeedbackWireContextTests(unittest.TestCase):
    def mesh_context(self):
        from twinpulse_core.library_assets import normalize_mesh
        snapshot=normalize_mesh([[0,0,0],[.2,0,0],[0,.2,0],[0,0,.2]],
            [[0,2,1],[0,1,3],[0,3,2],[1,2,3]],logical_asset_id='asset_test',
            title='Test immutable tetrahedron',source_name='shape.obj',source_sha256='a'*64,
            origin='Explicit offline regression',license='Test only').to_dict()
        context=deepcopy(self.context)
        context['current_plan']['plan_version']='2.3'
        old=next(c for c in context['current_plan']['calls'] if c['arguments']['id']=='support')
        old.update(tool='place_library_asset',arguments=dict(id='support',snapshot=snapshot,position_m=[0,0,.1],yaw_deg=0))
        row=next(r for r in context['inventory'] if r['id']=='support')
        row.update(kind='place_library_asset',tool_call=deepcopy(old),original_parameters=deepcopy(old['arguments']))
        context['context_sha256']=canonical_sha256({k:v for k,v in context.items() if k!='context_sha256'})
        return context,old

    def test_mesh_wire_pins_version_and_normalization_is_idempotent(self):
        from twinpulse_provider.scene_edit_provider import normalized_feedback_patch
        from twinpulse_provider.errors import InvalidProviderResponseError
        from twinpulse_provider.semantic_scene import _shape_issues
        context,old=self.mesh_context();before=deepcopy(context)
        schema=wire(context)
        change=next(e for e in edits(schema) if e['properties']['action']['enum']==['change'])
        args=change['properties']['tool_call']['properties']['arguments']['properties']
        self.assertNotIn('snapshot',args)
        self.assertEqual(args['asset_version']['enum'],[old['arguments']['snapshot']['version']])
        compact=deepcopy(old);compact['arguments'].pop('snapshot')
        compact['arguments'].update(asset_version=old['arguments']['snapshot']['version'],position_m=[.3,0,.1])
        patch=dict(patch_version='scene-dependency-patch-1.0',edits=[edit('change','support',tool_call=compact)])
        final=normalized_feedback_patch(context,patch)
        self.assertEqual(final['edits'][0]['tool_call']['arguments']['snapshot'],old['arguments']['snapshot'])
        self.assertEqual(normalized_feedback_patch(context,final),final)
        self.assertEqual(context,before)
        bad=deepcopy(patch);bad['edits'][0]['tool_call']['arguments']['asset_version']='b'*64
        with self.assertRaisesRegex(InvalidProviderResponseError,'ASSET_PIN_CHANGED'):
            normalized_feedback_patch(context,bad)
        injected=deepcopy(compact);injected['arguments']['snapshot']=deepcopy(old['arguments']['snapshot'])
        self.assertTrue(_shape_issues(injected,change['properties']['tool_call']))
        forged=deepcopy(patch);forged['edits'][0]['action']='add'
        with self.assertRaisesRegex(InvalidProviderResponseError,'EXPLICIT_LIBRARY_PLACEMENT'):
            normalized_feedback_patch(context,forged)

    def test_mesh_summary_omits_every_geometry_copy_but_keeps_full_host_context(self):
        import json
        from twinpulse_provider.scene_edit_provider import feedback_generation_request
        context,old=self.mesh_context();request=feedback_generation_request(context,'mesh-context-test')
        self.assertNotIn('"points":',request.prompt);self.assertNotIn('"triangles":',request.prompt)
        self.assertIn(old['arguments']['snapshot']['version'],request.prompt)
        self.assertEqual(json.loads(request.prompt)['context_sha256'],context['context_sha256'])
        self.assertEqual(request.feedback_context,context)
        context['current_plan']['calls'][0]['arguments']['id']='caller_later_change'
        self.assertNotEqual(request.feedback_context,context)

    def test_host_summary_mismatch_blocks_before_scope_or_transport(self):
        import asyncio
        from dataclasses import replace
        from twinpulse_provider import CancellationToken,ProviderConfigurationError
        from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
        from twinpulse_provider.generation_policy import GenerationPolicy
        from twinpulse_provider.scene_edit_provider import feedback_generation_request
        from test_budgeted_generation import FixtureTransport,config,OBSERVER_MODEL
        class Scope:
            calls=0
            def bind(self,*args):self.calls+=1;return None
        context,_=self.mesh_context();scope=Scope();transport=FixtureTransport([])
        request=replace(feedback_generation_request(context,'mismatch-test'),inference_scope=scope)
        provider=BudgetedPipeline(transport,policy=GenerationPolicy(),observer_model_id=OBSERVER_MODEL,
            planner_model_id='nvidia/nemotron-3-super-120b-a12b',site_plan_version='2.2',
            stage_output_token_caps={'observer':40000,'planner':40000})
        with self.assertRaisesRegex(ProviderConfigurationError,'HOST_CONTEXT_SUMMARY_MISMATCH'):
            asyncio.run(provider.generate_feedback(replace(request,prompt=request.prompt+' '),
                CancellationToken(),config(timeout_s=300)))
        self.assertEqual(scope.calls,0);self.assertEqual(transport.bodies,[])

    def test_mesh_provider_wire_then_host_replay_is_bounded_and_geometry_free(self):
        import asyncio,json
        from dataclasses import replace
        from twinpulse_provider import CancellationToken,InvalidProviderResponseError
        from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
        from twinpulse_provider.generation_policy import GenerationPolicy
        from twinpulse_provider.scene_edit_provider import feedback_generation_request,normalized_feedback_patch
        from test_budgeted_generation import FixtureTransport,config,OBSERVER_MODEL
        class Scope:
            def bind(self,*args):return None
        context,old=self.mesh_context();wire_call=deepcopy(old)
        wire_call['arguments'].pop('snapshot');wire_call['arguments'].update(
            asset_version=old['arguments']['snapshot']['version'],position_m=[.3,0,.1])
        payload=dict(schema_version='scene-edit-proposal-1.1',context_sha256=context['context_sha256'],
            mode='dependency',explanation='Move the pinned instance only.',
            patch=dict(patch_version='scene-dependency-patch-1.0',edits=[edit('change','support',tool_call=wire_call)]))
        def run(value):
            transport=FixtureTransport([value]);request=replace(feedback_generation_request(context,'wire-test'),inference_scope=Scope())
            provider=BudgetedPipeline(transport,policy=GenerationPolicy(),observer_model_id=OBSERVER_MODEL,
                planner_model_id='nvidia/nemotron-3-super-120b-a12b',site_plan_version='2.2',
                stage_output_token_caps={'observer':40000,'planner':40000})
            response=asyncio.run(provider.generate_feedback(request,CancellationToken(),config(timeout_s=300)))
            return response,transport
        response,transport=run(payload)
        self.assertEqual(len(transport.bodies),1)
        wire_text=json.dumps(transport.bodies[0]);self.assertNotIn('"points"',wire_text);self.assertNotIn('"triangles"',wire_text)
        self.assertEqual(normalized_feedback_patch(context,response.payload['patch']),response.payload['patch'])
        self.assertEqual(response.payload['patch']['edits'][0]['tool_call']['arguments']['snapshot'],old['arguments']['snapshot'])
        forged=deepcopy(payload);forged['patch']['edits'][0]['tool_call']['arguments']['snapshot']=old['arguments']['snapshot']
        with self.assertRaises(InvalidProviderResponseError):run(forged)

    def test_new_add_rechecks_legacy_reuse_without_changing_pinned_replay(self):
        from test_model_recipe_planning import plinth_recipe
        from twinpulse_core.model_recipe import recipe_model_id,recipe_digest,compiled_parts
        from twinpulse_provider.scene_edit_provider import normalized_feedback_patch
        from twinpulse_provider.errors import InvalidProviderResponseError
        recipe=plinth_recipe();recipe['interpreter_version']='model-recipe-compiler-1.0'
        def addition(value):
            return dict(patch_version='scene-dependency-patch-1.0',edits=[edit('add','new_plinth',
                tool_call=dict(call_id='obj_new_plinth',tool='place_model_recipe',arguments=dict(
                    id='new_plinth',kind='storage',model_id=recipe_model_id(value),recipe_sha256=recipe_digest(value),
                    interpreter_version=value['interpreter_version'],recipe=value,
                    parameters={p['name']:p['default'] for p in value['parameters']},center_m=[0,0],yaw_deg=0)),
                placement=dict(id='new_plinth',relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))])
        valid=addition(recipe)
        self.assertEqual(normalized_feedback_patch(self.context,valid),valid)
        broken=deepcopy(recipe)
        broken['parts'][0].update(center=[0,0,.05],size=['width','depth',.1])
        broken['parts'].append(dict(id='floating_top',center=[0,0,dict(op='sub',args=['height',.01])],
            size=['width','depth',.02],material='wood',support_top=False,repeat=None))
        parameters={p['name']:p['default'] for p in broken['parameters']}
        self.assertEqual(len(compiled_parts(broken,parameters)),2) # immutable 1.0 replay is still supported
        with self.assertRaisesRegex(InvalidProviderResponseError,'FEEDBACK_RECIPE_REUSE_INVALID'):
            normalized_feedback_patch(self.context,addition(broken))

    def test_split_current_placement_normalizes_without_last_write_wins(self):
        from twinpulse_provider.scene_edit_provider import normalized_feedback_patch
        from twinpulse_provider.errors import InvalidProviderResponseError
        from twinpulse_app.dependency_patch import checked_patch
        source=partial_source();history=SceneChangeHistory.empty('room',source)
        context=feedback_edit_context('room',source,history,'Move the support .3m right')
        call=deepcopy(next(c for c in context['current_plan']['calls'] if c['arguments']['id']=='support'))
        call['arguments']['center_m'][0]+=.3
        floor=next(r for r in context['placement_contract']['relations'] if r['id']=='support')
        original=dict(patch_version='scene-dependency-patch-1.0',edits=[
            edit('change','support',tool_call=call),edit('reparent','support',placement=floor)])
        before=deepcopy(original)
        normalized=checked_patch(normalized_feedback_patch(context,original))
        self.assertEqual(normalized['edits'],[original['edits'][0]])
        self.assertEqual(original,before)
        bad=deepcopy(original);bad['edits'][1]['tool_call']=deepcopy(call)
        bad['edits'][1]['tool_call']['arguments']['center_m'][0]+=.2
        with self.assertRaises(InvalidProviderResponseError):normalized_feedback_patch(context,bad)
        repeated=deepcopy(original);repeated['edits'][1]=deepcopy(repeated['edits'][0])
        self.assertEqual(normalized_feedback_patch(context,repeated)['edits'],[repeated['edits'][0]])
        bad=deepcopy(repeated);bad['edits'][1]['tool_call']['arguments']['center_m'][0]+=.1
        with self.assertRaises(InvalidProviderResponseError):normalized_feedback_patch(context,bad)
    def setUp(self):
        self.source=partial_source();self.history=SceneChangeHistory.empty('room',self.source)
        self.context=feedback_edit_context('room',self.source,self.history,'Move only the existing support a little.')

    def test_exact_sha_and_object_not_call_identity(self):
        schema=wire(self.context)
        self.assertEqual(schema['properties']['context_sha256']['enum'],[self.context['context_sha256']])
        change=next(e for e in edits(schema) if e['properties']['action']['enum']==['change'])
        fields=change['properties'];self.assertEqual(fields['target_id']['enum'],['support'])
        call=fields['tool_call'];self.assertEqual(call['properties']['call_id']['enum'],['obj_support'])
        self.assertNotEqual(fields['target_id']['enum'],call['properties']['call_id']['enum'])
        branches=call['properties']['arguments'].get('anyOf',[call['properties']['arguments']])
        for branch in branches:
            self.assertEqual(branch['properties']['id']['enum'],['support'])
            self.assertEqual(branch['properties']['kind']['enum'],['storage'])

    def test_recipe_snapshot_pin_is_wire_compatible_and_legacy_compiler_unchanged(self):
        from test_model_recipe_planning import plinth_recipe
        from twinpulse_core.model_recipe import recipe_model_id,recipe_digest
        recipe=plinth_recipe();recipe['interpreter_version']='model-recipe-compiler-1.0'
        context=deepcopy(self.context)
        old=next(c for c in context['current_plan']['calls'] if c['arguments']['id']=='support')
        old.update(tool='place_model_recipe',arguments=dict(id='support',kind='storage',
            model_id=recipe_model_id(recipe),recipe_sha256=recipe_digest(recipe),
            interpreter_version=recipe['interpreter_version'],recipe=recipe,
            parameters={p['name']:p['default'] for p in recipe['parameters']},center_m=[0,0],yaw_deg=0))
        context['context_sha256']=canonical_sha256({k:v for k,v in context.items() if k!='context_sha256'})
        schema=wire(context)
        change=next(e for e in edits(schema) if e['properties']['action']['enum']==['change'])
        args=change['properties']['tool_call']['properties']['arguments']['properties']
        self.assertNotIn('recipe',args)
        self.assertEqual(args['interpreter_version']['enum'],['model-recipe-compiler-1.0'])
        from twinpulse_provider.scene_edit_provider import normalized_feedback_patch
        from twinpulse_provider.errors import InvalidProviderResponseError
        compact=deepcopy(old);compact['arguments'].pop('recipe');compact['arguments']['center_m']=[.3,0]
        patch=dict(patch_version='scene-dependency-patch-1.0',edits=[edit('change','support',tool_call=compact)])
        final=normalized_feedback_patch(context,patch)
        self.assertEqual(final['edits'][0]['tool_call']['arguments']['recipe'],recipe)
        self.assertNotIn('recipe',patch['edits'][0]['tool_call']['arguments'])
        retained=deepcopy(context);retained['current_plan']['calls']=[c for c in retained['current_plan']['calls']
            if c['arguments']['id']!='support']
        row=next(r for r in retained['inventory'] if r['id']=='support')
        row.update(status='deferred',tool_call=deepcopy(old))
        restore=dict(patch_version='scene-dependency-patch-1.0',edits=[edit('restore','support',
            tool_call=compact,placement=dict(id='support',relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))])
        self.assertEqual(normalized_feedback_patch(retained,restore)['edits'][0]['tool_call']['arguments']['recipe'],recipe)
        legacy=deepcopy(patch);legacy['edits'][0]['tool_call']['arguments']['recipe']=deepcopy(recipe)
        legacy['edits'][0]['tool_call']['arguments']['recipe']['parameters'][0]['maximum']=2
        self.assertEqual(normalized_feedback_patch(context,legacy),final)
        legacy['edits'][0]['tool_call']['arguments']['recipe']['title']='Changed definition'
        with self.assertRaises(InvalidProviderResponseError):normalized_feedback_patch(context,legacy)

    def test_materialized_pending_structural_and_new_add_are_separate(self):
        groups={action:[] for action in ('change','restore','room','reparent','defer','remove','add')}
        for entry in edits(wire(self.context)):
            fields=entry['properties'];groups[fields['action']['enum'][0]].append(fields['target_id'])
        self.assertEqual([r['enum'] for r in groups['change']],[['support']])
        self.assertEqual([r['enum'] for r in groups['restore']],[['item_0']])
        self.assertEqual(groups['reparent'],[])
        structural={c.arguments['id'] for c in self.source.plan.calls if c.tool in {'create_floor','create_wall'}}
        self.assertEqual({r['enum'][0] for r in groups['room']},structural)
        self.assertEqual({r['enum'][0] for r in groups['defer']},{'support','item_0'})
        self.assertEqual(len(groups['add']),1);self.assertNotIn('enum',groups['add'][0])

    def test_restore_then_reparent_and_pending_only_sha_are_fresh(self):
        restored=adopt(self.history,self.source,preview(self.history,self.source,'restore',edit('restore','item_0',
            tool_call=item('item_0',[0,0,.91],(.5,.3,.02)),placement=relation('item_0','support'))))
        context=feedback_edit_context('room',self.source,restored,'Reparent the restored item.')
        candidates=edits(wire(context))
        self.assertFalse(any(e['properties']['action']['enum']==['restore'] for e in candidates))
        self.assertEqual({e['properties']['target_id']['enum'][0] for e in candidates
            if e['properties']['action']['enum']==['reparent']},{'item_0'})
        deferred=adopt(self.history,self.source,preview(self.history,self.source,'pending',edit('defer','item_0')))
        after=feedback_edit_context('room',self.source,deferred,self.context['request_text'])
        alternative=edit('defer','item_0');alternative['reason']='A distinct retained pending explanation'
        other=adopt(self.history,self.source,preview(self.history,self.source,'other-pending',alternative))
        other_context=feedback_edit_context('room',self.source,other,self.context['request_text'])
        self.assertEqual(after['current_scene_revision'],other_context['current_scene_revision'])
        self.assertNotEqual(after['current_state_sha256'],other_context['current_state_sha256'])
        self.assertNotEqual(wire(after)['properties']['context_sha256'],wire(other_context)['properties']['context_sha256'])

    def test_invalid_context_fails_before_constructing_schema_and_generic_compatibility(self):
        invalid=deepcopy(self.context);invalid['request_text']='A different request'
        with self.assertRaisesRegex(ValueError,'feedback context invalid'):wire(invalid)
        extra={**self.context,'authority':True}
        extra['context_sha256']=canonical_sha256({k:v for k,v in extra.items() if k!='context_sha256'})
        with self.assertRaisesRegex(ValueError,'feedback context invalid'):wire(extra)
        static=feedback_proposal_json_schema()
        self.assertEqual(static['properties']['context_sha256'],{'type':'string'})
        self.assertIn({'type':'null'},static['properties']['patch']['anyOf'])

    def test_atomic_edit_rule_is_wire_visible_without_limiting_later_revisions(self):
        description=wire(self.context)['properties']['patch']['anyOf'][0]['properties']['edits']['description']
        self.assertIn('each target_id appears exactly once',description)
        self.assertIn('unchanged placement',description)
        self.assertIn('one reparent edit',description)
        self.assertIn('later reviewed revision',description)
        self.assertIn('preserved implicitly',self.context['boundary'])
        call=deepcopy(next(c for c in self.context['current_plan']['calls'] if c['arguments']['id']=='support'))
        call['arguments']['center_m']=[.1,0]
        history=adopt(self.history,self.source,preview(self.history,self.source,'first',edit('change','support',tool_call=call)))
        current=feedback_edit_context('room',self.source,history,'Resize the same support in a new revision.')
        self.assertEqual({e['properties']['target_id']['enum'][0] for e in edits(wire(current))
            if e['properties']['action']['enum']==['change']},{'support'})
        self.assertNotEqual(current['context_sha256'],self.context['context_sha256'])


if __name__=='__main__':unittest.main()
