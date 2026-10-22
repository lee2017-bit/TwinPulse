# SPDX-License-Identifier: Apache-2.0
"""No-device build orchestration; compiler artifacts below are explicit fixtures."""
from pathlib import Path
import sys
import tempfile
import re
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import guard_runtime as g


class GuardRuntimeTests(unittest.TestCase):
    def test_cmake_output_contract_is_explicit_not_host_default(self):
        source=(Path(g.__file__).parent/'guard_base/CMakeLists.txt').read_text()
        declaration=re.search(r'add_library\(([^)]*)\)',source).group(1).split()
        self.assertEqual(declaration[:2],['${PROJECT_NAME}_lib','SHARED'])
        self.assertIn('BUILD_RPATH_USE_ORIGIN TRUE',source)

    def test_static_or_missing_library_is_rejected_before_checks_and_activation(self):
        for static in (True,False):
            with self.subTest(static=static),tempfile.TemporaryDirectory() as tmp:
                calls=[]
                def build(command,log,env):
                    calls.append(command)
                    if '--build' in command:
                        path=Path(command[command.index('--build')+1]);path.mkdir(parents=True)
                        (path/'turtlebot3_ros').write_bytes(b'fixture-not-an-executable')
                        if static:(path/'libturtlebot3_node_lib.a').write_bytes(b'fixture-static-archive')
                with self.assertRaisesRegex(ValueError,'^OUTPUT_GUARD_ARTIFACT_MISSING$'):
                    g.ensure(Path(g.__file__).parent,tmp,runner=build)
                self.assertEqual(len(calls),2)
                self.assertFalse(list(Path(tmp).rglob('receipt.json')))
                failure=list(Path(tmp).rglob('failure.json'))
                self.assertEqual(len(failure),1)

    def test_build_is_separate_cached_hash_checked_and_never_launches_base(self):
        package=Path(g.__file__).parent
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def build(command,log,env):
                calls.append(command)
                self.assertEqual(env['ROS_LOCALHOST_ONLY'],'1');self.assertEqual(env['ROS_DOMAIN_ID'],'87')
                if '--build' in command and Path(command[command.index('--build')+1]).name=='build':
                    path=Path(command[command.index('--build')+1]);path.mkdir(parents=True)
                    for name in ('turtlebot3_ros','libturtlebot3_node_lib.so'):(path/name).write_bytes(b'fixture-not-an-executable')
            phases=[]
            binary,receipt=g.ensure(package,tmp,runner=build,phase=phases.append)
            self.assertEqual(phases,['BUILDING_OUTPUT_GUARD','CHECKING_OUTPUT_GUARD','CHECKING_OUTPUT_GUARD_LOADER'])
            self.assertEqual(len(calls),6);self.assertIn('ctest',calls[-2])
            self.assertEqual(calls[-1][-2:],[str(binary),'-h'])
            self.assertFalse(receipt['motion_enabled'])
            self.assertEqual(receipt['loader_check']['status'],'PASS')
            self.assertEqual(receipt['loader_check']['artifacts'],receipt['artifacts'])
            cached=[]
            second,_=g.ensure(package,tmp,runner=lambda command,log,env:cached.append(command))
            self.assertEqual(len(cached),1);self.assertEqual(cached[0][-2:],[str(binary),'-h'])
            self.assertEqual(binary,second)
            binary.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'BINARY_CHANGED'):g.ensure(package,tmp,runner=build)

    def test_build_failure_or_cancel_does_not_fall_back_to_old_binary(self):
        for fail in ('compiler','cancel'):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as tmp:
                def reject(*_):raise ValueError('TEST_'+fail)
                with self.assertRaisesRegex(ValueError,'TEST_'+fail):
                    g.ensure(Path(g.__file__).parent,tmp,runner=reject if fail=='compiler' else lambda *_:None,
                        safety=reject if fail=='cancel' else lambda:None)
                failures=list(Path(tmp).rglob('failure.json'))
                self.assertEqual(len(failures),1)
                self.assertFalse(any(p.name=='receipt.json' for p in Path(tmp).rglob('*')))

    @staticmethod
    def compiler_fixture(command,log,env):
        if '--build' in command and Path(command[command.index('--build')+1]).name=='build':
            directory=Path(command[command.index('--build')+1]);directory.mkdir(parents=True)
            for name in ('turtlebot3_ros','libturtlebot3_node_lib.so'):
                (directory/name).write_bytes(b'fixture-not-an-executable')

    def test_final_verification_error_is_not_masked_after_directory_rename(self):
        original=g.verify
        def reject_final(directory,files,**kwargs):
            if 'loader_required' not in kwargs:raise ValueError('OUTPUT_GUARD_BINARY_CHANGED')
            return original(directory,files,**kwargs)
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,'verify',side_effect=reject_final):
            records=[]
            with self.assertRaisesRegex(ValueError,'^OUTPUT_GUARD_BINARY_CHANGED$'):
                g.ensure(Path(g.__file__).parent,tmp,runner=self.compiler_fixture,
                    diagnostic=lambda row,log:records.append(row))
            failures=list(Path(tmp).rglob('failure.json'))
            self.assertEqual(len(failures),1)
            self.assertNotIn('.building-',str(failures[0]))
            self.assertEqual(records[-1]['error']['code'],'OUTPUT_GUARD_BINARY_CHANGED')
            self.assertEqual(records[-1]['active_step'],'VERIFY_FINAL_RECEIPT')

    def test_unwritable_diagnostic_and_callback_do_not_replace_original_error(self):
        original=g.write_record
        def write(path,*args,**kwargs):
            if path.name=='failure.json':raise PermissionError('injected disk failure')
            return original(path,*args,**kwargs)
        def fail(*_):raise FileNotFoundError(2,'No such file','cmake')
        records=[]
        def notify(row,log):
            records.append(row)
            raise RuntimeError('injected notification failure')
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,'write_record',write):
            with self.assertRaises(FileNotFoundError) as caught:
                g.ensure(Path(g.__file__).parent,tmp,runner=fail,diagnostic=notify)
            self.assertEqual(caught.exception.filename,'cmake')
            self.assertEqual(records[-1]['error']['filename'],'cmake')
            self.assertEqual(records[-1]['error']['errno'],2)
            self.assertEqual(records[-1]['failure_record_error'],'PermissionError')
            self.assertEqual(records[-1]['active_step'],'CONFIGURE_GUARD')

    def test_loader_failure_has_exit_code_never_returns_authority_and_retries_only_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];records=[]
            def loader_fails(command,log,env):
                calls.append(command)
                self.compiler_fixture(command,log,env)
                if command[-1]=='-h':
                    self.assertEqual(env['LD_BIND_NOW'],'1')
                    self.assertTrue(env['LD_LIBRARY_PATH'].startswith(str(Path(command[-2]).parent)))
                    self.assertNotIn('.building-',command[-2])
                    self.assertNotIn('-i',command)
                    return 127
            with self.assertRaisesRegex(ValueError,'^OUTPUT_GUARD_LOADER_FAILED$'):
                g.ensure(Path(g.__file__).parent,tmp,runner=loader_fails,
                    diagnostic=lambda row,log:records.append(row))
            self.assertEqual(records[-1]['steps'][-1]['exit_code'],127)
            self.assertEqual(records[-1]['status'],'FAILED_NOT_ACTIVATED')
            directory=next(Path(tmp).glob('guard-builds/*'))
            with self.assertRaisesRegex(ValueError,'LOADER_NOT_VERIFIED'):
                g.verify(directory,g.sources(Path(g.__file__).parent))
            retried=[]
            binary,receipt=g.ensure(Path(g.__file__).parent,tmp,
                runner=lambda command,log,env:retried.append(command))
            self.assertEqual(retried,[[*calls[-1]]])
            self.assertEqual(receipt['loader_check']['status'],'PASS')
            self.assertTrue(binary.is_file())

    def test_help_branch_precedes_ros_initialization_and_device_constructor(self):
        source=(Path(g.__file__).parent/'guard_base/src/node_main.cpp').read_text()
        help_start=source.index('if (rcutils_cli_option_exist')
        help_end=source.index('return 0;',help_start)
        self.assertLess(help_end,source.index('rclcpp::init'))
        self.assertLess(help_end,source.index('std::make_shared<robotis::turtlebot3::TurtleBot3>'))

    def test_interrupted_receipt_replace_preserves_complete_cache_and_explicit_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary,_=g.ensure(Path(g.__file__).parent,tmp,runner=self.compiler_fixture)
            receipt=binary.parent.parent/'receipt.json';original=receipt.read_bytes()
            replace=Path.replace
            def fail(path,target):
                if path.name.startswith('receipt.json.tmp-'):raise OSError('injected disk failure')
                return replace(path,target)
            with patch.object(Path,'replace',fail),self.assertRaises(OSError):
                g.ensure(Path(g.__file__).parent,tmp,runner=self.compiler_fixture)
            self.assertEqual(receipt.read_bytes(),original)
            retried=[]
            g.ensure(Path(g.__file__).parent,tmp,runner=lambda command,*_:retried.append(command))
            self.assertEqual(len(retried),1);self.assertEqual(retried[0][-1],'-h')

    def test_cleanup_error_is_recorded_without_masking_operator_stop(self):
        records=[];checks=[]
        def safety():
            checks.append(1)
            if len(checks)>1:raise ValueError('OPERATOR_STOP')
        class Child:
            pid=1;returncode=None
            def poll(self):return None
        with tempfile.TemporaryDirectory() as tmp,patch.object(g.subprocess,'Popen',return_value=Child()),\
                patch.object(g.os,'killpg',side_effect=PermissionError('injected cleanup failure'),create=True):
            with self.assertRaisesRegex(ValueError,'^OPERATOR_STOP$'):
                g.ensure(Path(g.__file__).parent,tmp,safety=safety,diagnostic=lambda row,log:records.append(row))
            self.assertEqual(records[-1]['error']['code'],'OPERATOR_STOP')
            self.assertEqual(records[-1]['steps'][-1]['cleanup_error']['exception_type'],'PermissionError')
            self.assertFalse(records[-1]['steps'][-1]['child_reaped'])

    def test_rejected_cache_link_never_receives_a_failure_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);cache=home/'guard-builds';cache.mkdir()
            source_files=g.sources(Path(g.__file__).parent)
            import hashlib,json
            identity=hashlib.sha256(json.dumps(source_files,sort_keys=True).encode()).hexdigest()
            final=cache/identity;final.mkdir()
            original=Path.is_symlink;records=[]
            def link(path):return path==final or original(path)
            with patch.object(Path,'is_symlink',link),self.assertRaisesRegex(ValueError,'CACHE_ESCAPE'):
                g.ensure(Path(g.__file__).parent,home,diagnostic=lambda row,log:records.append(row))
            self.assertFalse((final/'failure.json').exists())
            self.assertEqual(records[-1]['failure_record_error'],'ValueError')

    def test_receipt_source_id_and_final_directory_must_match_source_hash_before_loader(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            package=Path(g.__file__).parent
            binary,receipt=g.ensure(package,tmp,runner=self.compiler_fixture)
            directory=binary.parent.parent
            changed=dict(receipt,source_id='0'*64)
            g.write_record(directory/'receipt.json',changed,Path(tmp))
            with self.assertRaisesRegex(ValueError,'BUILD_IDENTITY'):
                g.ensure(package,tmp,runner=lambda *_:self.fail('Changed identity must fail before loader'))
            g.write_record(directory/'receipt.json',receipt,Path(tmp))
            moved=directory.with_name('0'*64);directory.rename(moved)
            with self.assertRaisesRegex(ValueError,'BUILD_IDENTITY'):
                g.verify(moved,g.sources(package))


if __name__=='__main__':unittest.main()
