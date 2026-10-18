# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary state-bound hint checks, not installed UI acceptance."""
import sys
from pathlib import Path
from threading import RLock
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_app/src'))
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
sys.path.insert(0, str(ROOT / 'packages/twinpulse_provider/src'))
from twinpulse_app.product_workflow_service import ProductWorkflow


class GenerationSettlingTests(unittest.TestCase):
    def test_only_current_cancelled_worker_is_settling(self):
        workflow = object.__new__(ProductWorkflow)
        workflow._lock = RLock()
        workflow._generation_id = 'current'
        workflow._phase = 'cancelled'
        workflow._workers = {object()}
        self.assertTrue(workflow.generation_settling('current'))
        self.assertFalse(workflow.generation_settling('old'))
        self.assertFalse(workflow.generation_settling(None))
        workflow._phase = 'generating'
        self.assertFalse(workflow.generation_settling('current'))
        workflow._phase = 'cancelled'
        workflow._workers.clear()
        self.assertFalse(workflow.generation_settling('current'))

