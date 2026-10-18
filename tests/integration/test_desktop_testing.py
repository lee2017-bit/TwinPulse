# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary testing entry contracts; no UI or robot calls."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import os
from unittest.mock import patch
from twinpulse_app.desktop_testing import configure_testing


class TestingEntryTests(unittest.TestCase):
    def test_normal_start_discards_inherited_debug_flag(self):
        with TemporaryDirectory() as directory:
            env={'TWINPULSE_UI_TEST_CDP_PORT':'19222'}
            self.assertEqual(configure_testing([],Path(directory),env),[])
            self.assertNotIn('TWINPULSE_UI_TEST_CDP_PORT',env)

    def test_explicit_test_uses_one_local_port_without_saved_setting(self):
        with TemporaryDirectory() as directory:
            env={};self.assertEqual(configure_testing(['--automation-test'],Path(directory),env),[])
            self.assertIn(int(env['TWINPULSE_UI_TEST_CDP_PORT']),range(19222,19232))
            self.assertFalse(list(Path(directory).iterdir()))

    def test_raw_debug_arguments_are_not_forwarded(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'USE_AUTOMATION_TEST_ENTRY'):
                configure_testing(['--remote-debugging-address=0.0.0.0'],Path(directory),{})

    def test_test_flag_is_launcher_only_and_not_repeatable(self):
        with TemporaryDirectory() as directory:
            for arguments in (['--automation-test','--automation-test'],['--install','--automation-test'],['--internal-role','backend','--automation-test']):
                with self.subTest(arguments=arguments),self.assertRaisesRegex(ValueError,'AUTOMATION_TEST_LAUNCH_ONLY'):
                    configure_testing(arguments,Path(directory),{})

    def test_running_mode_mismatch_never_stops_or_replaces_owner(self):
        for enabled in (False,True):
            with self.subTest(enabled=enabled),TemporaryDirectory() as directory:
                root=Path(directory);launch='a'*32;record=root/'launches'/launch/'desktop-automation.json';record.parent.mkdir(parents=True)
                record.write_text(json.dumps({'enabled':enabled,'port':19222 if enabled else None}))
                owner={'launch_id':launch,'owner_pid':os.getpid()};(root/'launcher.lock').write_text(json.dumps(owner))
                with self.assertRaises(ValueError):configure_testing([] if enabled else ['--automation-test'],root,{})
                self.assertEqual(json.loads((root/'launcher.lock').read_text()),owner)
                env={};self.assertEqual(configure_testing(['--automation-test'] if enabled else [],root,env),[])
                self.assertEqual(env,{'TWINPULSE_UI_TEST_CDP_PORT':'19222'} if enabled else {})

    def test_child_role_does_not_apply_launcher_mode_conflict(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);launch='b'*32;record=root/'launches'/launch/'desktop-automation.json';record.parent.mkdir(parents=True)
            record.write_text(json.dumps({'enabled':True,'port':19222}));(root/'launcher.lock').write_text(json.dumps({'launch_id':launch,'owner_pid':os.getpid()}))
            env={'TWINPULSE_UI_TEST_CDP_PORT':'19222'}
            self.assertEqual(configure_testing(['--help'],root,env,role='robot-readiness'),['--help']);self.assertEqual(env,{})
            with self.assertRaisesRegex(ValueError,'AUTOMATION_TEST_LAUNCH_ONLY'):configure_testing(['--automation-test'],root,{},role='backend')

    def test_stale_lock_is_left_for_existing_manager_recovery(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);launch='c'*32;record=root/'launches'/launch/'desktop-automation.json';record.parent.mkdir(parents=True)
            record.write_text(json.dumps({'enabled':True,'port':19222}));owner={'launch_id':launch,'owner_pid':1234};(root/'launcher.lock').write_text(json.dumps(owner))
            with patch('twinpulse_app.process_manager._pid_alive',return_value=False):self.assertEqual(configure_testing([],root,{}),[])
            self.assertEqual(json.loads((root/'launcher.lock').read_text()),owner)

    def test_lock_pins_mode_before_desktop_record_is_published(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);(root/'launcher.lock').write_text(json.dumps({'launch_id':'d'*32,'owner_pid':os.getpid(),'desktop_automation':True,'automation_port':19223}))
            with self.assertRaisesRegex(ValueError,'EXIT_TEST_MODE'):configure_testing([],root,{})
            env={};self.assertEqual(configure_testing(['--automation-test'],root,env),[]);self.assertEqual(env['TWINPULSE_UI_TEST_CDP_PORT'],'19223')

    def test_partial_lock_reaches_manager_retry_without_false_mode_conflict(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);(root/'launcher.lock').write_text('{')
            self.assertEqual(configure_testing([],root,{}),[])
            env={};self.assertEqual(configure_testing(['--automation-test'],root,env),[])
            self.assertIn('TWINPULSE_UI_TEST_CDP_PORT',env)


if __name__=='__main__':unittest.main()
