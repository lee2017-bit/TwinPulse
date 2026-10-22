# SPDX-License-Identifier: Apache-2.0
"""Exact unchanged installed32 module comparison; never App acceptance."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
source=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/releases/20261021T183711Z-6b83ac7cbba1/_internal/resources/packages/twinpulse_app/src/twinpulse_app/project_catalog.py'
spec=importlib.util.spec_from_file_location('twinpulse_app.project_catalog',source)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
names=('test_bedroom_creation_failure_never_publishes_partial_project_and_same_id_retries',
       'test_bedroom_import_and_publish_failures_leave_name_retryable',
       'test_explicit_saved_bedroom_project_is_reviewable_and_does_not_switch',
       'test_legacy_partial_room_requires_explicit_fingerprint_and_preserves_original',
       'test_same_request_id_cannot_enter_two_project_creations_at_once',
       'test_create_api_requires_session_csrf_and_exact_body',
       'test_two_projects_and_changed_source_are_reported_without_switch_or_writes')
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName('tests.integration.test_a2_project_catalog.ProjectCatalogTests.'+n) for n in names)
print('CLASSIFICATION: exact installed32 catalog, old-source comparison only; failures stay failures',flush=True)
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
