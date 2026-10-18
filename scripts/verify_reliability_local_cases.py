# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""T05--T08 on one saved LIVE-generated room, through isolated product/chat APIs.

The broker is offline: this does not qualify new PhysX or physical execution.
No provider requests. Each of eight cases starts with the same original room.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for p in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/p/'src'))
from tests.integration.test_chat_conversation import ChatConversationTests
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.project_store import ProjectRecord
from twinpulse_app.scene_changes import SceneChangeHistory
from twinpulse_core.simulation_goal import preview_review
from twinpulse_app.simulation_assets import burger_inventory


def main(args):
    args.output.mkdir(parents=True,exist_ok=False)
    raw=args.source.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    source=SiteDraftRecord.from_dict(json.loads(raw)['site_draft'])
    original=source.to_dict();history=SceneChangeHistory.empty('default',source)
    scene=source.site.scene
    floor=next(o for o in scene.objects if o.kind=='floor')
    cx,cy=floor.transform.position_m[:2];width,depth=floor.shape.dimensions_m[:2]
    add=None
    for dx in (-.6,-.3,0,.3,.6):
        for dy in (-.6,-.3,0,.3,.6):
            x=round(cx+width/2*dx,3);y=round(cy+depth/2*dy,3)
            call=dict(call_id='added_chair',tool='place_furniture',arguments=dict(id='added_chair',kind='chair',
                catalog_version='furniture-blocks-1.0',center_m=[x,y],yaw_deg=0))
            try:history.preview(source,operation_id='precheck',mode='add',tool_call=call)
            except ValueError:continue
            add=(x,y);break
        if add:break
    if add is None:raise ValueError('No checked chair position in fixed test grid')
    bed=next(c for c in source.plan.calls if c.tool=='place_furniture' and c.arguments['kind']=='bed')
    moved=None
    for delta in (.15,-.15,.3,-.3):
        call=bed.to_dict();call['arguments']['center_m']=[bed.arguments['center_m'][0],round(bed.arguments['center_m'][1]+delta,3)]
        try:history.preview(source,operation_id='precheck',mode='change',target_call_id=bed.call_id,tool_call=call)
        except ValueError:continue
        moved=call['arguments'];break
    if moved is None:raise ValueError('No checked bed-only move in test candidates')
    preview=preview_review(scene,burger_inventory());start=preview['plan']['start'];goal=preview['plan']['goal']
    cases={
      'T05':('add',f'Add a chair x={add[0]} y={add[1]}'),
      'T06':('change',f"Move bed x={moved['center_m'][0]} y={moved['center_m'][1]} yaw={moved['yaw_deg']}"),
      'T07':('new',f'Go from x={start[0]} y={start[1]} to x={goal[0]} y={goal[1]}'),
      'T08':('new',f'Go from x={start[0]} y={start[1]} to nonexistent_console_999')}
    report=dict(scope='local_product_API_saved_live_room_offline_broker',source_sha256=digest,
        source_revision=scene.revision,provider_requests=0,robot_connections=0,actual_Isaac='NOT_RUN',jobs=[])
    for name,(mode,text) in cases.items():
      for repeat in (1,2):
        identity=f'{name}-r{repeat}';destination=args.output/identity;destination.mkdir()
        os.environ['TWINPULSE_TEST_TMP']=str(destination/'runtime')
        harness=ChatConversationTests('test_schema_and_stale_revision_and_unknown_choice_are_rejected');harness.setUp()
        item=dict(case=identity,input=text,status='FAIL')
        try:
            app=harness.workflow._application
            record=ProjectRecord(project_id='default',latest_input=source.input_revision,site_draft=source)
            app._artifact_store.save(source.input_revision,());app._project_store.save(record);app._project=record
            harness.workflow._phase='restore_review_required'
            harness.workflow.resume_saved_scene('default',scene.revision,source.input_revision.digest)
            harness.workflow.simulation_preview()
            state=harness.call(dict(action='message',request_id=identity,text=text,mode=mode,attachment=None))
            if name in ('T05','T06'):
                card=state['cards'][-1];assert card['kind']=='scene_edit',state['messages'][-1]
                action=dict(action='answer',request_id=identity+'-apply',card_id=card['id'],choice_id='apply',
                    expected_session_revision=card['expected_session_revision'])
                state=harness.call(action);harness.call(action)
                assert len([e for e in state['events'] if e['type']=='scene_edit_completed'])==1
                assert harness.workflow.snapshot()['site_draft']['revision']!=scene.revision
                assert app.site_draft.to_dict()==original
            elif name=='T07':
                assert state['simulation_review']['plan']['goal']==goal
                assert not state['simulation_review']['plan']['physical_authority']
            else:
                assert 'SIM_TARGET_NOT_FOUND' in state['messages'][-1]['content'],state['messages'][-1]
                assert state['simulation_review'] is None
            assert app.site_draft.to_dict()==original
            assert not harness.broker.public_state('unowned')['operations']
            assert hashlib.sha256(args.source.read_bytes()).hexdigest()==digest
            (destination/'conversation.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
            item['status']='PASS'
        except Exception as error:item.update(error_type=type(error).__name__,message=str(error)[:700])
        finally:harness.tearDown()
        report['jobs'].append(item);print(identity+': '+item['status'],flush=True)
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if all(j['status']=='PASS' for j in report['jobs']) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('--source',required=True,type=Path)
    raise SystemExit(main(parser.parse_args()))
