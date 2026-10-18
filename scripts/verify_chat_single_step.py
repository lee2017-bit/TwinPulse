# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Built browser and authenticated Site API rehearsal; no provider or robot network."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.integration.test_chat_site_text_generation import ChatSiteJourneyTests, completion, observation, room, OBSERVER_MODEL, PLANNER_MODEL
from tests.integration.test_r5_product_api import png
from twinpulse_provider import InvalidProviderResponseError


def main():
    output=ROOT/'artifacts'/f'chat-single-step-20261007-{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True,exist_ok=False)
    outcomes={}
    for case in ('text','photo','retry','repair','timeout'):
        destination=output/case;destination.mkdir()
        os.environ['TWINPULSE_TEST_TMP']=str(destination/'isolated-api')
        harness=ChatSiteJourneyTests('test_text_chat_reaches_site_draft_and_checked_sim_preview_without_an_image')
        harness.setUp()
        try:
            responses=[completion('plan',PLANNER_MODEL,room())]
            if case=='photo':responses.insert(0,completion('obs',OBSERVER_MODEL,observation()))
            if case=='retry':responses.insert(0,InvalidProviderResponseError('Chat Completions output was truncated'))
            harness.install_gateway(*responses)
            if case=='repair':
                from packages.twinpulse_provider.tests.test_nebius_pipeline import ScriptedTransport,config
                from twinpulse_provider import GenerationService,NebiusChatCompletionsPipelineProvider
                harness.transport=ScriptedTransport(InvalidProviderResponseError('Chat Completions output was truncated'),
                    completion('fixed',PLANNER_MODEL,room()),delay_s=1.2)
                adapter=NebiusChatCompletionsPipelineProvider(harness.transport,observer_model_id=OBSERVER_MODEL,
                    planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1)
                harness.workflow._application.set_generation_gateway(GenerationService(adapter,config(timeout_s=10),plan_version='2.2'))
            if case=='timeout':
                import time
                from packages.twinpulse_provider.tests.test_nebius_pipeline import config
                from twinpulse_provider import GenerationService,NebiusChatCompletionsPipelineProvider
                from twinpulse_provider.reliability import AuditedChatTransport,InferenceEvidence
                class Response:
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def geturl(self):return config().endpoint_url()
                    def read(self,n):
                        time.sleep(3)
                        return json.dumps(dict(id='late',model=PLANNER_MODEL,choices=[dict(finish_reason='stop',
                            message=dict(content=json.dumps(room())))],usage=dict(prompt_tokens=10,completion_tokens=100))).encode()
                harness.transport=AuditedChatTransport(lambda:'fixture-not-a-key',InferenceEvidence(destination/'private'),
                    opener=lambda *a,**k:Response())
                adapter=NebiusChatCompletionsPipelineProvider(harness.transport,observer_model_id=OBSERVER_MODEL,
                    planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1)
                harness.workflow._application.set_generation_gateway(GenerationService(adapter,config(timeout_s=.3),plan_version='2.2'))
            harness.server._static_root=ROOT/'apps/twinpulse-web/dist'
            image=destination/'fixture.png';image.write_bytes(png())
            secret='d'*43;harness.server._bootstrap['product']=secret
            env={**os.environ,'TWINPULSE_CHAT_URL':harness.server.base_url,'TWINPULSE_CHAT_BOOTSTRAP':secret,
                 'TWINPULSE_CHAT_IMAGE':str(image),'TWINPULSE_CHAT_OUTPUT':str(destination),'TWINPULSE_CHAT_CASE':case}
            node=Path('C:/Users/jaewo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
            result=subprocess.run([str(node),str(ROOT/'apps/twinpulse-web/e2e/chat-single-step.mjs')],
                                  cwd=ROOT/'apps/twinpulse-web',env=env,timeout=60,check=False)
            expected=1 if case in ('text','timeout') else 2
            calls=len(harness.transport.calls if case=='timeout' else harness.transport.bodies)
            if calls!=expected:
                raise AssertionError(f'{case}: unexpected fixture transport count')
            state=harness.server.conversation.snapshot()
            (destination/'conversation-result.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
            outcomes[case]={'exit_code':result.returncode,'fixture_transport_calls':calls}
        finally:harness.tearDown()
    report={'status':'PASS' if all(item['exit_code']==0 for item in outcomes.values()) else 'FAIL',
            'cases':outcomes,'paid_calls':0,'robot_connections':0,'isaac_runtime':'NOT_RUN',
            'scope':'Built browser with authenticated product API and scripted provider responses only'}
    (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(output),**report}))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':sys.exit(main())
