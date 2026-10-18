# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fresh-user and non-ASCII settings contracts; not native UI acceptance."""
from copy import deepcopy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.harness_store import HarnessStore
from twinpulse_app.robot_registry_service import RobotRegistryService
from twinpulse_provider.harness_profiles import default_profile,edited_profile,MAX_TEXT,SUPER
from twinpulse_provider.harness_profiles import binding

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(dir=ROOT/'artifacts/test-tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_fresh_registry_does_not_invent_or_auto_select_a_robot(self):
        devices=SimpleNamespace(lock=RLock(),diagnostics=None,readiness=None,controller=None,contexts=[],
            assert_document_available=lambda:None)
        service=RobotRegistryService(devices,self.root,discoverer=lambda:self.fail('implicit discovery'))
        snapshot=service.request(None,'owner')
        self.assertEqual(snapshot['robots'],[]);self.assertIsNone(snapshot['active_id'])
        self.assertEqual(snapshot['revision'],0);self.assertEqual(snapshot['discovery']['state'],'idle')
        with self.assertRaisesRegex(Exception,'Select a registered robot'):
            service.request(dict(action='connect',expected_revision=0),'owner')
    def test_preexisting_registry_and_selection_are_preserved_without_discovery(self):
        devices=SimpleNamespace(lock=RLock(),diagnostics=None,readiness=None,controller=None,contexts=[],
            assert_document_available=lambda:None)
        service=RobotRegistryService(devices,self.root)
        saved=service.request(dict(action='register',expected_revision=0,label='User robot',adapter_id='unreviewed',
            endpoint=dict(host='robot.example',user='operator',port=2222,ros_domain_id=3)),'owner')
        selected=service.request(dict(action='select',expected_revision=1,id=saved['robots'][0]['id']),'owner')
        original=service.registry.path.read_bytes()
        restored=RobotRegistryService(devices,self.root,discoverer=lambda:self.fail('implicit discovery'))
        self.assertEqual(restored.request(None,'owner')['active_id'],selected['active_id'])
        self.assertEqual(restored.registry.path.read_bytes(),original)
    def test_full_length_korean_harness_roundtrips_and_baseline_stays_immutable(self):
        store=HarnessStore(self.root);baseline=default_profile('nebius',SUPER,'planner')
        original=deepcopy(baseline);old=store.save(baseline)
        instructions={stage:'한'*MAX_TEXT for stage in baseline['instructions']}
        edited=edited_profile(baseline,instructions,name='korean-full')
        ref=store.save(edited)
        self.assertEqual(store.resolve(ref,provider='nebius',model=SUPER,role='planner')['profile'],edited)
        self.assertIn(ref,store.list_refs(provider='nebius',model=SUPER,role='planner'))
        self.assertEqual(store.resolve(old,provider='nebius',model=SUPER,role='planner')['profile'],original)
        self.assertEqual(baseline,original)

    def test_isolated_trial_keeps_exact_profile_without_reading_global_profiles_for_manifest(self):
        from scripts.run_ordinary_staged_live_ten import copy_trial_settings
        source=self.root/'source';source.mkdir();target=self.root/'copy';target.mkdir()
        baseline=default_profile('nebius',SUPER,'planner')
        profile=edited_profile(baseline,{**baseline['instructions'],'planning':'Independent profile test'},name='copied')
        frozen=binding(profile);store=HarnessStore(source);reference=store.save(profile)
        settings=SimpleNamespace(path=source/'settings.json');registry=SimpleNamespace(path=source/'keys.json')
        route_path=source/'routes.json'
        for path in (settings.path,registry.path,route_path):path.write_text('{}',encoding='utf-8')
        routes=SimpleNamespace(path=route_path,load=lambda:{'selected':reference},
            harness_bindings=lambda route:{'planner':frozen})
        original={path:path.read_bytes() for path in source.rglob('*') if path.is_file()}
        copy_trial_settings(settings,registry,routes,target)
        self.assertEqual(HarnessStore(target).resolve(reference,provider='nebius',model=SUPER,role='planner'),frozen)
        self.assertEqual({path:path.read_bytes() for path in source.rglob('*') if path.is_file()},original)
        isolated=self.root/'manifest';isolated.mkdir()
        routes.load=lambda:self.fail('Manifest isolation must not read global routes or profiles')
        copy_trial_settings(settings,registry,routes,isolated,manifest_bound=True)
        self.assertFalse((isolated/route_path.name).exists());self.assertFalse((isolated/'harness-profiles').exists())

if __name__=='__main__':unittest.main()
