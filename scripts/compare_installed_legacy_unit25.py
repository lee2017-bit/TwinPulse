# SPDX-License-Identifier: Apache-2.0
"""Run unchanged legacy unit cases against exact installed19 Python sources.

Not an ordinary App/robot journey. It cannot promote a failed test to PASS.
The import finder prevents test sys.path additions from hiding that baseline.
"""
import importlib.abc
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/jaewo/AppData/Local/TwinPulse/installed/releases/20261020T212337Z-99993da012c3/_internal/resources/packages')
if not SOURCE.is_dir():raise ValueError('EXACT_BASELINE_SOURCE_REQUIRED')
class Installed(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        package=fullname.split('.')[0]
        if package not in {'twinpulse_app','twinpulse_core','twinpulse_provider'}:return None
        relative=fullname.split('.')[1:];base=SOURCE/package/'src'/package
        directory=base.joinpath(*relative)
        if (directory/'__init__.py').is_file():return importlib.util.spec_from_file_location(fullname,directory/'__init__.py',submodule_search_locations=[str(directory)])
        if directory.with_suffix('.py').is_file():return importlib.util.spec_from_file_location(fullname,directory.with_suffix('.py'))
        raise ModuleNotFoundError('Installed baseline member absent: '+fullname)
sys.meta_path.insert(0,Installed());sys.path.insert(0,str(ROOT))
names=['test_ambiguous_navigation_choice_rechecks_scene_and_does_not_generate',
 'test_goal_failure_keeps_conversation_and_linked_execution_diagnosis',
 'test_navigation_missing_start_and_real_rejection_are_recorded',
 'test_real_local_api_ambiguous_objects_select_one_without_build_or_generation',
 'test_discarded_response_does_not_raise_or_reexecute']
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName('tests.integration.test_chat_conversation.ChatConversationTests.'+name) for name in names)
print('CLASSIFICATION: BASELINE_COMPARISON_ONLY; exact installed19 source; failures retained, not counted as PASS',flush=True)
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
