# SPDX-License-Identifier: Apache-2.0
"""No-device build orchestration; compiler artifacts below are explicit fixtures."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import guard_runtime as g


class GuardRuntimeTests(unittest.TestCase):
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
            self.assertEqual(phases,['BUILDING_OUTPUT_GUARD','CHECKING_OUTPUT_GUARD'])
            self.assertEqual(len(calls),5);self.assertIn('ctest',calls[-1])
            self.assertFalse(receipt['motion_enabled'])
            self.assertTrue(all('turtlebot3_ros' not in command for command in calls))
            second,_=g.ensure(package,tmp,runner=lambda *_:self.fail('Cache must not rebuild'))
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


if __name__=='__main__':unittest.main()
