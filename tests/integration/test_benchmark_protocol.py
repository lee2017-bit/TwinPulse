# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline protocol test data only; no paid/model/Isaac acceptance claim."""
from collections import Counter,defaultdict
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from io import BytesIO
from dataclasses import replace
from unittest.mock import patch
from PIL import Image
from scripts.benchmark_protocol import (checked_case,checked_manifest,checked_packet,journey_packet,
    canonical_sha,file_sha,text_sha,schedule,prepare,effective_settings_sha,source_freeze,frozen_stage_output_caps)


class BenchmarkProtocolTests(unittest.TestCase):
    def test_frozen_output_caps_preserve_old_cohorts_and_bind_new_settings(self):
        config=dict(config_id='example')
        self.assertEqual(frozen_stage_output_caps(config),dict(observer=20000,planner=20000))
        config['stage_output_token_caps']=dict(observer=40000,planner=20000)
        caps=frozen_stage_output_caps(config)
        self.assertEqual(caps,config['stage_output_token_caps'])
        caps['planner']=123;self.assertEqual(config['stage_output_token_caps']['planner'],20000)
        for invalid in (dict(observer=40001,planner=20000),dict(observer=True,planner=20000),
                        dict(observer=20000),dict(observer=20000,planner='40000')):
            with self.assertRaisesRegex(ValueError,'OUTPUT_CAPS_INVALID'):
                frozen_stage_output_caps(dict(stage_output_token_caps=invalid))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name,color in (('first.png',(20,30,40)),('second.png',(70,80,90))):
            stream=BytesIO();Image.new('RGB',(2,2),color).save(stream,format='PNG')
            (self.root/name).write_bytes(stream.getvalue())
        (self.root/'answers.json').write_text('{"label":"ANSWER_ONLY_DO_NOT_SEND"}',encoding='utf-8')
        (self.root/'source.py').write_text('# fixed code fixture',encoding='utf-8')
        self.cases=[self.case('photo-one','photo','first.png'),self.case('photo-two','photo','second.png'),
                    self.case('text-one','text'),self.case('text-two','text')]
        self.roles=dict(observer=dict(provider='nebius',model='vision-model'),
            planner=dict(provider='nebius',model='plan-model'),repair=dict(provider='nebius',model='plan-model'),
            critic=dict(provider='nebius',model='vision-model'))
        self.value=dict(schema_version='comparative-benchmark-1.0',dataset_id='offline-fixtures',version='1',
            seed=46,repeats=2,cases=self.cases,
            configs=[dict(config_id=name,roles=deepcopy(self.roles),settings_sha256='a'*64) for name in ('a','b','c')],
            freeze={'source.py':file_sha(self.root/'source.py')})

    def case(self,identity,modality,photo=None):
        prompt='An approximate space '+identity;goal='Go to desk'
        return dict(schema_version='benchmark-case-1.0',case_id=identity,room_group=identity,
            split='development',modality=modality,prompt=prompt,prompt_sha256=text_sha(prompt),
            photo=dict(path=photo,sha256=file_sha(self.root/photo),mime_type='image/png') if photo else None,
            goal=dict(text=goal,sha256=text_sha(goal),expected='arrival',start_policy='checked_sim_preview'),
            source=dict(reference='synthetic protocol fixture',license='test only',
                external_transmission_allowed=False,public_release_allowed=False),
            annotations=dict(path='answers.json',sha256=file_sha(self.root/'answers.json')))

    def checked(self):return checked_manifest(self.value,self.root)

    def test_two_photos_two_texts_have_isolated_input_packets(self):
        before=deepcopy(self.value);checked=self.checked()
        packets=[checked_packet(journey_packet(case)) for case in checked['cases']]
        self.assertNotEqual(packets[0]['photo']['sha256'],packets[1]['photo']['sha256'])
        self.assertTrue(all(packet['photo'] is None for packet in packets[2:]))
        for packet in packets:
            encoded=json.dumps(packet)
            self.assertNotIn('annotations',encoded);self.assertNotIn('answers.json',encoded)
            self.assertNotIn('ANSWER_ONLY_DO_NOT_SEND',encoded)
        self.assertEqual(self.value,before)

    def test_seeded_schedule_is_repeatable_paired_and_position_balanced(self):
        manifest=self.checked();jobs=schedule(manifest)
        self.assertEqual(jobs,schedule(manifest));self.assertEqual(len(jobs),24)
        paired=defaultdict(list);positions=defaultdict(Counter)
        for job in jobs:
            paired[job['case_id'],job['repeat']].append(job['config_id'])
            positions[job['config_id']][job['position']]+=1
        self.assertTrue(all(sorted(rows)==['a','b','c'] for rows in paired.values()))
        self.assertTrue(all(max(c.values())-min(c.values())<=1 for c in positions.values()))
        manifest['seed']+=1;self.assertNotEqual(jobs,schedule(manifest))

    def test_room_and_duplicate_image_leakage_rejected(self):
        self.value['cases'][1]['room_group']='photo-one';self.value['cases'][1]['split']='holdout'
        with self.assertRaisesRegex(ValueError,'ROOM_SPLIT_LEAKAGE'):self.checked()
        self.value['cases'][1]=self.case('photo-two','photo','first.png')
        with self.assertRaisesRegex(ValueError,'DUPLICATE_IMAGE_GROUP'):self.checked()

    def test_actual_packet_requires_permission_and_diagnostic_lane_not_faked(self):
        packet=journey_packet(checked_case(self.cases[0],self.root))
        with self.assertRaisesRegex(ValueError,'TRANSMISSION_NOT_APPROVED'):checked_packet(packet,actual=True)
        packet['external_transmission_allowed']=True
        self.assertEqual(checked_packet(packet,actual=True),packet)
        packet['split']='diagnostic';packet['goal']['expected']='rejection'
        self.assertEqual(checked_packet(packet,actual=True),packet)
        packet['split']='holdout'
        with self.assertRaisesRegex(ValueError,'NEGATIVE_CASE_REQUIRES_DIAGNOSTIC'):checked_packet(packet,actual=True)

    def test_frozen_catalog_manifest_expands_configs_and_preserves_all_models(self):
        from twinpulse_provider.model_contracts import catalog_sha
        value=dict(schema_version='stage-model-catalog-1.0',verified_at='2026-10-10T00:00:00+00:00',
            valid_until='2026-10-16T00:00:00+00:00',source_sha256='a'*64,models=[
                dict(model_id='model-'+str(i),visible=True,modalities=['text','image'],context_tokens=32000,
                     input_per_million='0.1',output_per_million='0.2') for i in range(25)])
        path=self.root/'models.json';path.write_text(json.dumps(value),encoding='utf-8')
        self.value.update(schema_version='comparative-benchmark-1.1',model_catalog=dict(path='models.json',sha256=file_sha(path)))
        self.value['configs']=[dict(config_id='model-'+str(i),roles=deepcopy(self.roles),settings_sha256='a'*64) for i in range(25)]
        manifest=self.root/'manifest.json';manifest.write_text(json.dumps(self.value),encoding='utf-8')
        result=prepare(manifest)
        self.assertEqual(len(result['configs']),25);self.assertEqual(len(result['jobs']),200)
        self.assertEqual(result['model_catalog'],value);self.assertIn(str(path.resolve()),result['freeze'])
        route={'observer':{},'planner':{},'generation_policy':{}}
        before=effective_settings_sha(route,self.roles);route['model_catalog_sha256']=catalog_sha(value)
        self.assertNotEqual(before,effective_settings_sha(route,self.roles))
        path.write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'SHA_CHANGED'):prepare(manifest)

    def test_prompt_photo_goal_and_freeze_hash_changes_rejected(self):
        for field in ('prompt_sha256',):
            value=deepcopy(self.cases[0]);value[field]='b'*64
            with self.assertRaisesRegex(ValueError,'SHA_CHANGED'):checked_case(value,self.root)
        value=deepcopy(self.cases[0]);value['goal']['sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'GOAL_SHA_CHANGED'):checked_case(value,self.root)
        (self.root/'first.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'INPUT_SHA_CHANGED'):self.checked()

    def test_prepare_is_not_an_approval_or_an_inference(self):
        path=self.root/'manifest.json';path.write_text(json.dumps(self.value),encoding='utf-8')
        value=prepare(path)
        self.assertEqual(value['HTTP'],0);self.assertFalse(value['actual_run_authorized'])
        self.assertEqual(value['manifest_sha256'],file_sha(path))
        self.assertNotIn('answers.json',json.dumps(value))

    def test_source_change_and_non_image_payload_do_not_enter_actual_lane(self):
        (self.root/'source.py').write_text('# changed code',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'INPUT_SHA_CHANGED'):self.checked()
        (self.root/'first.png').write_bytes(b'not image data')
        self.cases[0]['photo']['sha256']=file_sha(self.root/'first.png')
        with self.assertRaisesRegex(ValueError,'IMAGE_INVALID'):checked_case(self.cases[0],self.root)

    def test_text_packet_cannot_smuggle_photo_or_labels(self):
        value=deepcopy(self.cases[2]);value['photo']=self.cases[0]['photo']
        with self.assertRaisesRegex(ValueError,'MUST_NOT_SEND_IMAGE'):checked_case(value,self.root)
        packet=journey_packet(checked_case(self.cases[2],self.root));packet['answers']='secret'
        with self.assertRaisesRegex(ValueError,'PACKET_INVALID'):checked_packet(packet)

    def test_effective_settings_digest_ignores_key_id_not_policy(self):
        route=dict(observer=dict(model_id='vision-model',key_id='private-registration',max_output_tokens=20000),
                   planner=dict(model_id='plan-model',key_id='another',max_output_tokens=20000),
                   generation_policy=dict(max_requests=24,total_timeout_s=900))
        before=effective_settings_sha(route,self.roles)
        route['observer']['key_id']='changed';self.assertEqual(before,effective_settings_sha(route,self.roles))
        route['observer']['max_output_tokens']=40000
        self.assertNotEqual(before,effective_settings_sha(route,self.roles))
        route['observer']['max_output_tokens']=20000
        self.assertEqual(before,effective_settings_sha(route,self.roles))
        route['generation_policy']['max_requests']=23
        self.assertNotEqual(before,effective_settings_sha(route,self.roles))

    def test_actual_command_uses_ordinary_app_and_no_photo_for_text(self):
        from scripts.run_ordinary_staged_live_ten import journey_command
        settings=self.root/'settings.json';packet=self.root/'packet.json'
        command=journey_command(self.root,None,settings,benchmark_case=packet)
        self.assertEqual(command[command.index('--case')+1],'text')
        self.assertNotIn('--live-photo',command);self.assertNotIn('--site-transport-fixture',command)
        self.assertIn('--ordinary-live-settings',command);self.assertIn('--benchmark-case',command)
        photo_command=journey_command(self.root,self.root/'second.png',settings,benchmark_case=packet)
        self.assertEqual(photo_command[photo_command.index('--live-photo')+1],str(self.root/'second.png'))

    def test_ui_trim_cannot_silently_change_frozen_prompt_or_goal(self):
        value=deepcopy(self.cases[2]);value['prompt']=' '+value['prompt']
        value['prompt_sha256']=text_sha(value['prompt'])
        with self.assertRaisesRegex(ValueError,'UI_TRIM_MISMATCH'):checked_case(value,self.root)
        value=deepcopy(self.cases[2]);value['goal']['text']+=' '
        value['goal']['sha256']=text_sha(value['goal']['text'])
        with self.assertRaisesRegex(ValueError,'UI_TRIM_MISMATCH'):checked_case(value,self.root)

    def test_freeze_includes_actual_isaac_adapter_and_build_not_private_outputs(self):
        paths=['extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
               'extensions/twinpulse.extension/config/extension.toml',
               'apps/twinpulse-web/dist/assets/built.js','packages/twinpulse_core/src/twinpulse_core/model_library.py',
               'outputs/private-answer.json']
        for relative in paths:
            path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('source fixture',encoding='utf-8')
        frozen=source_freeze(self.root)
        self.assertTrue(all(str((self.root/p).resolve()) in frozen for p in paths[:-1]))
        self.assertNotIn(str((self.root/paths[-1]).resolve()),frozen)

    def test_two_photo_two_text_runner_preflights_reach_metadata_without_real_credentials_or_calls(self,provider='nebius',catalog=False,diagnostic=False):
        """Exercise manifest→isolated settings→approval, stop before metadata I/O.

        A selected config dict must survive creating the settings directory.
        This is a fake preflight regression, explicitly not live generation.
        """
        import scripts.run_ordinary_staged_live_ten as runner
        from scripts.compare_model_roles_live import metadata_get
        class MetadataBoundary(Exception):pass
        source=self.root/'settings';source.mkdir()
        for name in ('provider.json','keys.json','provider_stage_routing.json'):
            (source/name).write_text('{}',encoding='utf-8')
        class FakeSettings:
            def __init__(_,path=None):_.path=Path(path) if path else source/'provider.json'
        class FakeRegistry:
            def __init__(_,settings,credentials):_.settings=settings;_.path=settings.path.with_name('keys.json')
            def state(_):return {'entries':[{'id':'synthetic-registration','provider_profile':
                'openai' if provider=='openai' else 'nebius_token_factory','active':True}]}
            def settings_for_entry(_,identity):return object()
            def resolve(_,value):return type('FakeCredential',(),{'is_configured':lambda _:True})()
        class FakeRoutes:
            def __init__(_,registry):_.path=registry.settings.path.with_name('provider_stage_routing.json')
            def load(_):return None
            def save(_,route,changed):pass
        roles=dict(observer=dict(provider=provider,model='gpt-6-luna' if provider=='openai' else 'deepseek-ai/DeepSeek-V4.1-Flash'),
            planner=dict(provider=provider,model='gpt-6-luna' if provider=='openai' else 'nvidia/Nemotron-3_5-Lightning'))
        roles.update(repair=deepcopy(roles['planner']),critic=deepcopy(roles['observer']))
        model_catalog=None
        if catalog:
            roles['observer']['model']='test/new-vision';roles['planner']['model']='test/new-planner'
            roles.update(repair=deepcopy(roles['planner']),critic=deepcopy(roles['observer']))
            from twinpulse_provider.model_contracts import catalog_sha
            model_catalog=dict(schema_version='stage-model-catalog-1.0',verified_at='2026-10-10T00:00:00+00:00',
                valid_until='2026-10-16T00:00:00+00:00',source_sha256='a'*64,models=[
                    dict(model_id=roles[stage]['model'],visible=True,modalities=['image','text'] if stage=='observer' else ['text'],
                         context_tokens=32000,input_per_million='0.1',output_per_million='0.2') for stage in ('observer','planner')])
            path=self.root/'model-catalog.json';path.write_text(json.dumps(model_catalog),encoding='utf-8')
            self.value.update(schema_version='comparative-benchmark-1.1',model_catalog=dict(path=path.name,sha256=file_sha(path)))
        if diagnostic:
            for i,case in enumerate(self.value['cases']):
                case['split']='diagnostic';case['goal']['expected']='rejection' if i%2 else 'clarification'
        policy=replace(runner.GenerationPolicy(),max_requests=24,external_final_review=True,
                       initial_timeout_s=420,final_timeout_s=180)
        route=dict(observer=dict(key_id='synthetic-registration',model_id=roles['observer']['model'],max_output_tokens=20000),
            planner=dict(key_id='synthetic-registration',model_id=roles['planner']['model'],max_output_tokens=20000,
                         thinking_mode='default' if provider=='openai' or catalog else 'disabled'),
            generation_policy=policy.validate().to_dict())
        if model_catalog:route['model_catalog_sha256']=catalog_sha(model_catalog)
        self.value['configs']=[dict(config_id='reviewed',roles=roles,settings_sha256=effective_settings_sha(route,roles))]
        for case in self.value['cases']:case['source']['external_transmission_allowed']=True
        manifest=self.root/'manifest.json';manifest.write_text(json.dumps(self.value),encoding='utf-8')
        frozen=self.checked()['freeze']
        for case in self.value['cases']:
            output=self.root/('output-'+case['case_id'])
            argv=['runner',str(output),'--benchmark-manifest',str(manifest),
                '--case-id',case['case_id'],'--config-id','reviewed','--benchmark-profile',
                '--recommended-nebius','--request-cap','24','--approval-text','OFFLINE_FAKE_PREFLIGHT_ONLY']
            with patch.object(runner.sys,'argv',argv),patch.object(runner,'JsonProviderSettingsStore',FakeSettings),\
                 patch.object(runner,'WindowsCredentialStore',lambda:None),patch.object(runner,'KeyRegistry',FakeRegistry),\
                 patch.object(runner,'StageRoutingSettings',FakeRoutes),patch('scripts.benchmark_protocol.source_freeze',return_value=frozen),\
                 patch('scripts.compare_model_roles_live.metadata_get',side_effect=MetadataBoundary) as boundary,\
                 patch.object(runner.subprocess,'run') as launch:
                with self.assertRaises(MetadataBoundary):runner.main()
                boundary.assert_called_once();launch.assert_not_called()
                self.assertEqual(boundary.call_args.args[0],'https://api.openai.com/v1/models' if provider=='openai'
                    else 'https://api.tokenfactory.nebius.com/private/v1/models_info')
            receipt=json.loads((output/'approval.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['case_id'],case['case_id']);self.assertEqual(receipt['config_id'],'reviewed')
            self.assertEqual(receipt['settings_sha256'],self.value['configs'][0]['settings_sha256'])
            self.assertEqual(receipt['photo_sha256'],case['photo']['sha256'] if case['photo'] else None)
            if model_catalog:
                copied=json.loads((output/'reviewed-settings/stage_model_catalog.json').read_text(encoding='utf-8'))
                self.assertEqual(copied,model_catalog);self.assertEqual(receipt['route']['model_catalog_sha256'],catalog_sha(model_catalog))

    def test_all_luna_preflight_needs_no_unused_nebius_key_or_metadata_request(self):
        self.test_two_photo_two_text_runner_preflights_reach_metadata_without_real_credentials_or_calls(provider='openai')

    def test_extended_catalog_and_expected_negative_preflights_bind_ordinary_case_without_calls(self):
        self.test_two_photo_two_text_runner_preflights_reach_metadata_without_real_credentials_or_calls(catalog=True,diagnostic=True)


if __name__=='__main__':unittest.main()
