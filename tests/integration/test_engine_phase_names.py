# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The engine host's startup phase names and the launcher's phase allowlist stay one set.

Supplementary: reads scripts/twinpulse_engine_host.py as source and runs only its own progress
writer into a temporary file; no Isaac, Kit, launcher or Windows run.
"""
import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))

from twinpulse_app import process_manager as pm

HOST = ROOT / 'scripts' / 'twinpulse_engine_host.py'


def reported_phases(source):
    """({phase names passed to _report_progress}, [calls whose phase is not a readable literal]).

    A phase given as a variable counts when every assignment to that name in the calling
    function is a string literal; anything else is listed, so it cannot slip past the check.
    """
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    phases, unreadable = set(), []
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == '_report_progress'):
            continue
        argument = call.args[0] if call.args else None
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            phases.add(argument.value)
            continue
        function = parents.get(call)
        while function is not None and not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = parents.get(function)
        if not isinstance(argument, ast.Name) or function is None:
            unreadable.append(call.lineno)
            continue
        stores = [node for node in ast.walk(function)
                  if isinstance(node, ast.Name) and node.id == argument.id and isinstance(node.ctx, ast.Store)]
        values = [parents[node].value for node in stores if isinstance(parents[node], (ast.Assign, ast.AnnAssign))]
        parameters = [item.arg for item in (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)]
        if (not stores or len(values) != len(stores) or argument.id in parameters
                or not all(isinstance(value, ast.Constant) and isinstance(value.value, str) for value in values)):
            unreadable.append(call.lineno)
            continue
        phases.update(value.value for value in values)
    return phases, unreadable


class EnginePhaseNameTests(unittest.TestCase):
    def test_the_phases_the_host_reports_are_exactly_the_launcher_allowlist(self):
        phases, unreadable = reported_phases(HOST.read_text(encoding='utf-8'))
        self.assertEqual(unreadable, [], 'each _report_progress phase must be a literal (lines listed)')
        # A host phase the allowlist lacks is dropped from the start timeout message, so that message
        # names an older phase or none; an allowlisted name the host no longer writes is dead.
        self.assertEqual(phases, set(pm.ENGINE_PROGRESS_PHASES))

    def test_the_record_the_host_writes_for_each_phase_is_read_back_by_the_launcher(self):
        phases = reported_phases(HOST.read_text(encoding='utf-8'))[0] | set(pm.ENGINE_PROGRESS_PHASES)
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            progress = folder / 'launch' / 'engine-progress.json'
            argv = ['twinpulse_engine_host.py', '--stop-file', str(folder / 'stop'), '--result-file',
                    str(folder / 'result.json'), '--viewport-capture', str(folder / 'capture.png'),
                    '--progress-file', str(progress)]
            with patch.object(sys, 'argv', argv), patch.object(sys, 'path', list(sys.path)):
                report = runpy.run_path(str(HOST), run_name='engine_phase_names_test')['_report_progress']
            for phase in sorted(phases):
                with self.subTest(phase=phase):
                    status = 401 if phase == 'bridge_wait' else None  # the host adds the bridge's last HTTP status
                    with redirect_stdout(io.StringIO()) as printed:
                        report(phase, **({'http_status': status} if status else {}))
                    self.assertIn(f'TWINPULSE_ENGINE_PHASE phase={phase} ', printed.getvalue())
                    seen = pm._engine_progress(pm._read_json(progress))  # the launcher's own reader
                    self.assertIsNotNone(seen, f'the launcher ignores the {phase!r} record the host wrote')
                    self.assertEqual((seen['phase'], seen['http_status']), (phase, status))


if __name__ == '__main__':
    unittest.main()
