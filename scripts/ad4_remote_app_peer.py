# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned offline verification App process, separate from the Isaac interpreter.

Runs the real App/API/controller with the existing synthetic ROS subprocess.
Ephemeral bootstrap credentials arrive only on stdin and are never saved.
"""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
for package in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))


def main(state,output):
    from tests.integration.test_automatic_photo_service import RaycastSource,recipe
    from tests.integration.test_automatic_demo_service import GEOMETRY
    from tests.integration.test_a2_room_recipe import NoGateway
    from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore,LocalApiServer
    from twinpulse_app.automatic_demo_service import AutomaticDemoService
    from twinpulse_app.automatic_mission_service import AutomaticMissionService
    from twinpulse_app.physical_controller import PhysicalController
    from twinpulse_app.remote_observed_adapter import RemoteObservedAdapter
    from twinpulse_app.session_history import review_session
    from twinpulse_core.adaptive_mission_contract import nominal_room
    from tests.fixtures.observed_robot_process import fixture_evidence_exporter
    from rehearse_offline_app import NoCredentials
    config=json.loads(sys.stdin.buffer.readline(4096))
    if set(config)!={'product_secret','engine_secret'} or any(type(v) is not str or not 32<=len(v)<=128 for v in config.values()):
        raise ValueError('OFFLINE_APP_PEER_CONFIGURATION')
    pid='mission_room';peer=state/'peer';world=json.loads((peer/'synthetic-world.json').read_text())
    vertices=world['vertices'];outline={'segments':[[vertices[i],vertices[(i+1)%len(vertices)]] for i in range(len(vertices))]}
    automatic=AutomaticDemoService(state,pid,source_factory=lambda *a:RaycastSource(pid,outline),geometry_loader=lambda:GEOMETRY)
    controller=PhysicalController(state,command=lambda _r,_m:[sys.executable,'-B',str(ROOT/'tests/fixtures/observed_robot_process.py'),str(peer)],evidence_exporter=fixture_evidence_exporter(peer))
    adapters=[];server=None;mission=None
    try:
        def factory(prior,room,effective,goal):
            scope={'schema':'observed-mission-scope-2.0','project_id':pid,'goal':goal,'reference':None,'alignment':None,
                'nominal':nominal_room(effective['objects'],.182,effective['effective_revision'])}
            adapter=RemoteObservedAdapter(controller,lambda _:{},scope);adapters.append(adapter);return adapter
        factory.supports_remote_correction=True
        mission=AutomaticMissionService(automatic,adapter_factory=factory)
        broker=CommandBroker(project_id=pid)
        app=ApplicationService(NoGateway(),project_store=ProjectStore.for_project(state,pid),project_id=pid)
        original=app._project_store.path.read_bytes()
        workflow=ProductWorkflow(app,broker,mode='simulation_offline',generation_settings_getter=lambda:{'request_schema':'offline-1.0'})
        server=LocalApiServer(broker,product_bootstrap_secret=config['product_secret'],engine_bootstrap_secret=config['engine_secret'],
            product_workflow=workflow,static_root=ROOT/'apps/twinpulse-web/dist',session_history_root=state,credential_store=NoCredentials())
        server.automatic_mission.close();server.automatic_demo.close();server.automatic_demo=automatic;server.automatic_mission=mission
        server.start();print(json.dumps({'state':'OFFLINE_APP_READY','base_url':server.base_url}),flush=True)
        # API/mission/controller threads run independently of this waiting thread.
        request=json.loads(sys.stdin.buffer.readline(256))
        if request!={'action':'finish'}:raise ValueError('OFFLINE_APP_PEER_FINISH_REQUEST')
        if mission.worker and mission.worker.is_alive():raise ValueError('OFFLINE_APP_PEER_MISSION_STILL_ACTIVE')
        if len(adapters)!=1:raise ValueError('OFFLINE_APP_PEER_START_COUNT')
        job=mission.job;history=review_session(state,job['job_id']);status=controller.snapshot(adapters[0].owner)
        if app._project_store.path.read_bytes()!=original:raise ValueError('OFFLINE_APP_PEER_ORIGINAL_CHANGED')
        summary={'status':'CAPTURED','job':job,'scope':adapters[0].scope,
            'controller':{k:status.get(k) for k in ('busy','cleanup_confirmed','sensor_cleanup_confirmed')},
            'correction_exchange':history['correction_exchange'],
            'operation_statuses':[operation.status for operation in broker._operations.values()],
            'original_project_unchanged':True,'physical_validation':'NOT_RUN','robot_connections':0}
        (output/'remote-app-result.json').write_text(json.dumps(summary,allow_nan=False),encoding='utf-8')
        print(json.dumps({'state':'OFFLINE_APP_CAPTURED'}),flush=True)
    finally:
        if server:server.stop()
        else:
            if mission:mission.close()
            automatic.close()
        controller.close()


if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
