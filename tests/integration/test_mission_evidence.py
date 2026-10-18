# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Historical full-map export boundaries. No robot connection or device I/O."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[2]
for part in ('twinpulse_core/src','twinpulse_app/src','twinpulse_robot_safety'):
    sys.path.insert(0,str(ROOT/'packages'/part))
from twinpulse_core.mission_evidence_contract import mission_evidence,checked_mission_evidence,evidence_bytes,decode_evidence,FILE_NAME
from twinpulse_core.adaptive_mission_contract import nominal_room
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.current_mission_evidence import CurrentMissionEvidence
from twinpulse_core.room_localization import compose
from twinpulse_core.automatic_photo_alignment import align_photo_map
from twinpulse_app.robot_evidence_export import export_finished_session,load_mission_evidence,MODE_FILES
from twinpulse_app.physical_controller import PhysicalController
from observed_runtime import RobotObservedFactory
from raw_ros_record import RawRosRecorder
sys.path.insert(0,str(ROOT/'scripts'))
from inspect_robot_evidence import inspect
from tests.integration.test_automatic_photo_service import recipe


def fixture(root):
    _,objects=recipe(root,'evidence_room',1.)
    scope={'schema':'observed-mission-scope-4.0','project_id':'evidence_room',
        'goal':{'mode':'SURVEY_ONLY','xy':[0.,0.],'room_revision':'a'*64,'duration_s':45.},
        'reference':None,'alignment':None,'nominal':nominal_room(objects,.182,'a'*64)}
    context={'project_id':'evidence_room','session_id':'manual-'+'b'*32,
        'boot_id':'boot-one','release_id':'c'*64,'source_revision':'c'*64,'origin':'live_ros'}
    frames=[{'sequence':i+1,'stamp_ns':1_000_000_000+i*100_000_000,'pose':[i*.05,0.,0.],
        'points':[[j*.01,1.] for j in range(24)],'origins':[[0.,0.]]*24} for i in range(8)]
    body={'schema':'session-survey-map-1.0','project_id':context['project_id'],'source_revision':context['source_revision'],
        'keyframes':frames,'endpoint_cells':[[j*.01,1.] for j in range(24)],
        'tracking_endpoints':[compose(f['pose'],[*p,0.])[:2] for f in frames for p in f['points']],
        'tracking_endpoint_basis':'ACCEPTED_SURVEY_DESKEWED_RETURNS_ODOMETRY_PROJECTED',
        'reference_eligible':False,'mapping_method':'CAUSAL_DESKEWED_ODOMETRY_PROJECTION_NOT_GLOBAL_SLAM',
        'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False}
    saved={**body,'revision':canonical_sha256(body)}
    fit=align_photo_map(saved,scope['nominal']['objects'],height_m=.182,policy='align_only')
    fit['report_revision']=canonical_sha256(fit)
    return scope,context,saved,fit


class MissionEvidenceTests(unittest.TestCase):
    def test_full_map_retains_all_frames_and_tracking_points_not_current_pose(self):
        with TemporaryDirectory() as td:
            scope,context,saved,fit=fixture(Path(td))
            value=mission_evidence(scope,'d'*32,'e'*64,context,saved,fit)
            self.assertEqual(value['survey_map'],saved);self.assertEqual(value['photo_alignment'],fit)
            self.assertEqual(len(value['survey_map']['tracking_endpoints']),192)
            self.assertFalse(value['current_pose_valid']);self.assertFalse(value['motion_authorized'])
            # Opening a historical reference does not instantiate a saved pose.
            tracker=CurrentMissionEvidence(saved,fit,{**context,'session_id':'new-session'},'a'*64)
            self.assertIsNone(tracker.transform);self.assertIsNone(tracker.capture)

    def test_changed_context_scope_request_map_and_authority_are_rejected(self):
        with TemporaryDirectory() as td:
            scope,context,saved,fit=fixture(Path(td))
            original=mission_evidence(scope,'d'*32,'e'*64,context,saved,fit)
            for case in ('context','scope','request','map_hash','tracking','order','authority','fit_source','fit_hash','nonfinite'):
                with self.subTest(case=case):
                    value=deepcopy(original)
                    if case=='context':value['context']['boot_id']='different-boot'
                    elif case=='scope':value['scope_sha256']='0'*64
                    elif case=='request':value['request_sha256']='0'*64
                    elif case=='map_hash':value['survey_map']['revision']='0'*64
                    elif case=='tracking':value['survey_map']['tracking_endpoints']=value['survey_map']['tracking_endpoints'][:160]
                    elif case=='order':value['survey_map']['keyframes'][1]['sequence']=1
                    elif case=='authority':value['current_pose_valid']=True
                    elif case=='fit_source':value['photo_alignment']['source_map_revision']='0'*64
                    elif case=='fit_hash':value['photo_alignment']['reason']='TAMPERED'
                    else:value['survey_map']['endpoint_cells'][0][0]=float('nan')
                    if case!='nonfinite':value['revision']=canonical_sha256({k:v for k,v in value.items() if k!='revision'})
                    with self.assertRaises(ValueError):checked_mission_evidence(value,scope,'d'*32,'e'*64,context)

    def test_robot_file_exclusive_and_no_stdout_big_map(self):
        with TemporaryDirectory() as td:
            root=Path(td);scope,context,saved,fit=fixture(root)
            factory=RobotObservedFactory.__new__(RobotObservedFactory)
            factory.scope=scope;factory.context=context;factory.request={'mission_id':'d'*32,'request_sha256':'e'*64}
            factory.mission=SimpleNamespace(survey_map=saved,fit_result=fit,worker=None)
            factory.output=lambda _ : self.fail('full map must not enter the live control channel')
            descriptor=factory.save_evidence(root)
            self.assertEqual(descriptor['bytes'],(root/FILE_NAME).stat().st_size)
            before=(root/FILE_NAME).read_bytes()
            with self.assertRaises(FileExistsError):factory.save_evidence(root)
            self.assertEqual((root/FILE_NAME).read_bytes(),before)

    def test_post_cleanup_export_resume_tamper_and_original_failure_preserved(self):
        with TemporaryDirectory() as td:
            root=Path(td);scope,context,saved,fit=fixture(root);source=root/'source';source.mkdir()
            data,descriptor=evidence_bytes(mission_evidence(scope,'d'*32,'e'*64,context,saved,fit))
            (source/FILE_NAME).write_bytes(data)
            recorder=RawRosRecorder(source/'ros-messages.raw',serializer=lambda v:v)
            recorder.record('scan',b'exact-original-raw');footer=recorder.close()
            report={'mode':'mission','robot_session_id':context['session_id'],'boot_id':context['boot_id'],
                'release_id':context['release_id'],'mission_evidence':descriptor,'raw_ros':footer,
                'mission_id':'d'*32,'mission_request_sha256':'e'*64,
                'status':'FAILED','reason':'INPUT_DEADLINE_EXPIRED','cleanup_confirmed':True}
            (source/'report.json').write_text(json.dumps(report))
            for name in MODE_FILES['mission']:
                if not (source/name).exists():(source/name).write_text(name)
            key=root/'key';known=root/'known';key.write_text('fixture');known.write_text('fixture')
            fetched=[]
            def transfer(command,**_):
                name=Path(command[-1]).name.removesuffix('.part');fetched.append(name)
                Path(command[-1]).write_bytes((source/name).read_bytes())
                return subprocess.CompletedProcess(command,0,b'',b'')
            destination=root/'saved'
            result=export_finished_session(report,destination,runner=transfer,scp='scp',key=key,known=known)
            self.assertEqual(result['status'],'COMPLETE');self.assertIn(FILE_NAME,fetched)
            inspection=inspect(destination)
            self.assertEqual(inspection['status'],'COMPLETE');self.assertEqual(inspection['mission_evidence']['status'],'MATCH')
            self.assertEqual(inspection['mission_evidence']['alignment_status'],'INSUFFICIENT_EVIDENCE')
            value=load_mission_evidence(destination,report,scope,'d'*32,'e'*64)
            self.assertEqual(value['survey_map'],saved);self.assertEqual(report['reason'],'INPUT_DEADLINE_EXPIRED')
            fetched.clear()
            export_finished_session(report,destination,runner=transfer,scp='scp',key=key,known=known)
            self.assertFalse(fetched)
            (destination/FILE_NAME).write_bytes(data+b' ')
            self.assertEqual(inspect(destination)['status'],'INCOMPLETE')
            with self.assertRaisesRegex(ValueError,'MISSION_EVIDENCE_FILE_HASH'):
                load_mission_evidence(destination,report,scope,'d'*32,'e'*64)
            export_finished_session(report,destination,runner=transfer,scp='scp',key=key,known=known)
            self.assertEqual(fetched,[FILE_NAME])
            load_mission_evidence(destination,report,scope,'d'*32,'e'*64)
            receipt=json.loads((destination/'export.json').read_text());receipt['binding']='REJECTED'
            (destination/'export.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'MISSION_EVIDENCE_EXPORT_NOT_VERIFIED'):
                load_mission_evidence(destination,report,scope,'d'*32,'e'*64)

    def test_test_exporter_cannot_replace_real_robot_transport(self):
        with TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'TEST_EVIDENCE_EXPORTER_REQUIRES_TEST_COMMAND'):
                PhysicalController(td,evidence_exporter=lambda *_: {})

    def test_duplicate_json_and_invalid_descriptor_never_load_or_fetch(self):
        with self.assertRaisesRegex(ValueError,'MISSION_EVIDENCE_DUPLICATE_KEY'):
            decode_evidence(b'{"motion_authorized":false,"motion_authorized":true}')
        with TemporaryDirectory() as td:
            report={'mode':'mission','robot_session_id':'manual-'+'b'*32,
                'mission_evidence':{'schema':'mission-evidence-file-1.0','file':'../other.json',
                    'bytes':10,'sha256':'a'*64,'revision':'b'*64}}
            with self.assertRaisesRegex(ValueError,'MISSION_EVIDENCE_DESCRIPTOR'):
                export_finished_session(report,Path(td)/'saved',runner=lambda *_a,**_k:self.fail('transport called'))


if __name__=='__main__':unittest.main()
