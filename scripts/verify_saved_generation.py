# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reopen exact closed-run product bytes; no provider, Build, Run or robot."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))

def main():
    from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path)
    args=parser.parse_args();root=args.run.resolve()
    if not root.is_relative_to(ROOT/'artifacts'):raise ValueError('OWNED_ARTIFACT_RUN_REQUIRED')
    result=json.loads((root/'result.json').read_text())
    if result['status']!='PASS' or result['supervisor']['phase']!='stopped':
        raise ValueError('CLOSED_SUCCESSFUL_RUN_REQUIRED')
    path=root/'runtime/active_project.json';before=path.read_bytes()
    store=ProjectStore(path);saved=store.load();draft=saved.site_draft
    if draft is None:raise ValueError('SAVED_GENERATED_SITE_REQUIRED')
    app=ApplicationService(None,project_store=store);broker=CommandBroker()
    workflow=ProductWorkflow(app,broker,mode='explicit_fixture',generation_settings_getter=lambda:{})
    reopened=workflow.resume_saved_scene(saved.project_id,draft.site.scene.revision,draft.input_revision.digest)
    assert reopened['acknowledged_revision'] is None and not broker.has_pending_operations()
    assert path.read_bytes()==before and store.load().site_draft.to_dict()==draft.to_dict()
    evidence=dict(status='PASS',input_revision=draft.input_revision.digest,
        plan_sha256=draft.plan_sha256,scene_revision=draft.site.scene.revision,
        project_file_sha256=hashlib.sha256(before).hexdigest(),source_unchanged=True,
        automatic_dispatch=False,provider_calls=0,robot_connections=0,physical_authority=False)
    with (root/'saved-generation-reopen.json').open('x',encoding='utf-8') as stream:
        json.dump(evidence,stream,indent=2)
    print('SAVED_GENERATION_REOPEN=PASS')
    return 0

if __name__=='__main__':raise SystemExit(main())
