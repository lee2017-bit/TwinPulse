# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit isolated acceptance hook; never a live model or production route.

Only replaces the provider response in an explicit fixture process and injects
one named storage/ACK fault in an owned test transaction. Actual App contracts,
broker, Isaac receipts, durable history and UI remain unchanged.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from scripts import twinpulse_backend as host
from twinpulse_provider import ProviderConfig,ProviderCapabilities,ProviderResponse,SceneEditProposalService
from twinpulse_app.scene_edit_transaction import SceneEditTransaction


class ExplicitFeedbackProvider:
    async def generate(self,request,token,config):
        context=json.loads(request.prompt)
        text=context['request_text']
        result=dict(schema_version='scene-edit-proposal-1.1',context_sha256=context['context_sha256'],
            mode='clarify',explanation='Move the synthetic support by how many metres along X?',patch=None)
        if '0.2 metres along X' in text:
            support=deepcopy(next(c for c in context['current_plan']['calls'] if c['arguments'].get('id')=='support'))
            support['arguments']['center_m'][0]+=.2
            result.update(mode='dependency',explanation='Move only the synthetic support and its checked descendants by 0.2 m.',
                patch=dict(patch_version='scene-dependency-patch-1.0',edits=[dict(action='change',target_id='support',
                    reason='Explicit fixture feedback',tool_call=support)]))
        elif 'out of bounds' in text:
            support=deepcopy(next(c for c in context['current_plan']['calls'] if c['arguments'].get('id')=='support'))
            support['arguments']['center_m']=[100.,100.]
            result.update(mode='dependency',explanation='Explicit invalid fixture candidate; the real preview must reject it.',
                patch=dict(patch_version='scene-dependency-patch-1.0',edits=[dict(action='change',target_id='support',
                    reason='Negative fixture acceptance',tool_call=support)]))
        evidence=Path(os.environ['TWINPULSE_EXPLICIT_FEEDBACK_EVIDENCE'])
        with evidence.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(request_id=request.request_id,context=context,response=result,
                external_api=False),ensure_ascii=False)+'\n')
        return ProviderResponse(request.request_id,result,'explicit-feedback-fixture',config.model_id)


def main():
    if '--fixture-mode' not in sys.argv:
        raise SystemExit('EXPLICIT_FIXTURE_ONLY_NO_LIVE_PROVIDER')
    fault=os.environ.get('TWINPULSE_EXPLICIT_EDIT_FAULT','')
    if fault not in ('','commit','ack'):raise SystemExit('UNKNOWN_EXPLICIT_FAULT')
    slow_undo=float(os.environ.get('TWINPULSE_EXPLICIT_SLOW_UNDO_S','0'))
    if slow_undo not in (0.,4.):raise SystemExit('UNKNOWN_EXPLICIT_PREPARATION_DELAY')
    feedback=bool(os.environ.get('TWINPULSE_EXPLICIT_FEEDBACK_EVIDENCE'))
    if feedback or slow_undo:
        original=host.ProductWorkflow
        class FixtureWorkflow(original):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                if feedback:
                    self.scene_edit_proposal_service=SceneEditProposalService(ExplicitFeedbackProvider(),ProviderConfig(
                        base_url='https://fixture.invalid/v1/',endpoint_path='responses',model_id='explicit-feedback-fixture',
                        api_key_env='UNUSED',capabilities=ProviderCapabilities(False,True),timeout_s=5.,max_attempts=1))
            def _register_scene_change(self,record,history):
                artifact=super()._register_scene_change(record,history)
                transaction=getattr(self,'scene_edit_transaction',None)
                if (slow_undo and history.operations and history.operations[-1].mode=='undo' and
                        transaction and transaction.value and transaction.value['state']=='STAGED'):
                    time.sleep(slow_undo)  # Explicit owned-test delay, never an engine ACK or fake frame.
                return artifact
        host.ProductWorkflow=FixtureWorkflow
    if fault=='commit':
        original=SceneEditTransaction._commit
        fired=False
        def fail_once(self,store,history):
            nonlocal fired
            if not fired:
                fired=True
                raise OSError('EXPLICIT_FIXTURE_DISK_BEFORE_COMMIT')
            return original(self,store,history)
        SceneEditTransaction._commit=fail_once
    elif fault=='ack':
        original=SceneEditTransaction._wait
        fired=False
        def lose_once(self,owner,operation):
            nonlocal fired
            receipt=original(self,owner,operation)
            if not fired:
                fired=True
                raise TimeoutError('EXPLICIT_FIXTURE_ACK_NOT_JOURNALED')
            return receipt
        SceneEditTransaction._wait=lose_once
    return host.main()


if __name__=='__main__':raise SystemExit(main())
