# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Host opt-in argument boundaries. No backend start, credentials or paid call."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch, Mock

ROOT=Path(__file__).resolve().parents[2]


class CompactLaunchTests(unittest.TestCase):
    def test_approved_300s_backend_reaches_bootstrap_guard_without_starting(self):
        result=self.command('scripts/twinpulse_backend.py','--ready-file','unused.json',
            '--inference-timeout-s','300','--inference-campaign','unused-campaign.json')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Bootstrap environment is missing',result.stderr)
        self.assertNotIn('Timeout override',result.stderr)
        self.assertFalse((ROOT/'unused.json').exists())

    def test_longer_deadline_requires_live_campaign_and_is_bounded_before_output(self):
        for script,args in (
                ('scripts/twinpulse_backend.py',['--ready-file','unused.json','--inference-timeout-s']),
                ('scripts/verify_chat_sim_journey.py',['unused-output','--case','image','--live-timeout-s'])):
            for deadline in ('89','180','300','301'):
                result=self.command(script,*args,deadline)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('requires an explicit live campaign',result.stderr)
            result=self.command(script,*args,'301','--inference-campaign' if 'backend' in script else '--live-campaign','unused-campaign.json')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('bounded deadline 90..300',result.stderr)
        self.assertFalse((ROOT/'unused-output').exists())
    def test_output_cap_requires_host_approval_before_bootstrap_or_output(self):
        for script,args in (
                ('scripts/twinpulse_backend.py',['--ready-file','unused.json','--inference-output-token-cap']),
                ('scripts/verify_chat_sim_journey.py',['unused-output','--case','image','--output-token-cap'])):
            for cap in ('10000','10001','0'):
                result=self.command(script,*args,cap)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('requires an explicit live campaign',result.stderr)
        self.assertFalse((ROOT/'unused-output').exists())
    def test_unbuilt_engine_report_does_not_mask_generation_failure(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('compact_test_engine_host',ROOT/'scripts/twinpulse_engine_host.py')
        module=importlib.util.module_from_spec(spec)
        with patch.object(sys,'argv',['host','--stop-file','unused-stop','--result-file','unused-result',
                                     '--viewport-capture','unused-capture']):
            spec.loader.exec_module(module)
        self.assertIsNone(module.APP)
        self.assertIsNone(module._mission_visual_marker(None))
        stage=Mock();stage.GetPrimAtPath.return_value=None
        self.assertIsNone(module._mission_visual_marker(stage))
        stage.GetPrimAtPath.assert_called_with('/World/TwinPulse/Presentation/AutomaticMission')
        stage.GetPrimAtPath.return_value=Mock()
        stage.GetPrimAtPath.return_value.GetCustomData.return_value={'mission_id':'test'}
        self.assertEqual(module._mission_visual_marker(stage),{'mission_id':'test'})

    def command(self,script,*arguments):
        env={k:v for k,v in os.environ.items() if k not in
             {'TWINPULSE_PRODUCT_BOOTSTRAP','TWINPULSE_ENGINE_BOOTSTRAP'}}
        return subprocess.run([sys.executable,str(ROOT/script),*arguments],cwd=ROOT,
            env=env,text=True,capture_output=True,timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)

    def test_backend_rejects_missing_campaign_before_bootstrap_or_credentials(self):
        result=self.command('scripts/twinpulse_backend.py','--ready-file','unused.json','--experimental-compact-photo')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('requires an explicit live campaign',result.stderr)

    def test_template_policy_requires_host_live_campaign_and_keeps_default(self):
        result=self.command('scripts/twinpulse_backend.py','--ready-file','unused.json',
                            '--experimental-planner-no-thinking')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('requires an explicit live campaign',result.stderr)
        result=self.command('scripts/verify_chat_sim_journey.py','unused-output','--case','image',
                            '--planner-template-policy','off')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('requires an explicit live campaign',result.stderr)
        self.assertFalse((ROOT/'unused-output').exists())

    def test_backend_rejects_fixture_offline_or_replay_even_with_campaign(self):
        for mode in (['--fixture-mode'],['--offline'],['--replay-report','unused-report.json']):
            with self.subTest(mode=mode):
                result=self.command('scripts/twinpulse_backend.py','--ready-file','unused.json',
                    '--experimental-compact-photo','--inference-campaign','unused-campaign.json',*mode)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('requires an explicit live campaign',result.stderr)

    def test_journey_rejects_unmarked_or_nonphoto_compact_modes_before_output(self):
        for arguments in (['--case','text'],['--case','image'],
                ['--case','image','--live-photo','unused.jpg'],
                ['--case','image','--live-photo','unused.jpg','--site-transport-fixture','--fault']):
            with self.subTest(arguments=arguments):
                result=self.command('scripts/verify_chat_sim_journey.py','unused-output','--compact-photo',*arguments)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('Compact photo requires',result.stderr)
        self.assertFalse((ROOT/'unused-output').exists())


if __name__=='__main__':unittest.main()
