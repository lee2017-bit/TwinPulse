# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-transport tests of post-session evidence export and context binding."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_app/src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_provider/src'))
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from twinpulse_app.robot_evidence_export import export_finished_session, MODE_FILES
from inspect_robot_evidence import inspect, main, ros_decoder, SESSION_FILES, STATIONARY_FILES
from prepare_robot import STATIONARY_FILES as EXPORTED_STATIONARY_FILES
from raw_ros_record import HEADER, MAGIC, RawRosRecorder


class EvidenceExportTests(unittest.TestCase):
    def test_scan_modes_export_raw_and_driver_then_inspect_and_resume_without_transport(self):
        for mode in ('qualify_scan','control_scan','scan','mission','localize'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'source';source.mkdir()
                raw=RawRosRecorder(source/'ros-messages.raw',serializer=lambda v:v)
                self.assertTrue(raw.record('scan',b'exact-cdr-fixture'))
                footer=raw.close()
                report={'robot_session_id':'manual-'+'f'*32,'mode':mode,
                        'boot_id':'boot','release_id':'release','raw_ros':footer}
                (source/'report.json').write_text(json.dumps(report))
                for name in MODE_FILES[mode]:
                    if not (source/name).exists():(source/name).write_text(name)
                key,known=root/'key',root/'known';key.write_text('fixture');known.write_text('fixture')
                copied=[]
                def transfer(command,**_):
                    name=Path(command[-1]).name.removesuffix('.part');copied.append(name)
                    Path(command[-1]).write_bytes((source/name).read_bytes())
                    return subprocess.CompletedProcess(command,0,b'',b'')
                receipt=export_finished_session(report,root/'saved',runner=transfer,scp='scp',key=key,known=known)
                self.assertEqual(receipt['status'],'COMPLETE')
                self.assertEqual(set(copied),set(MODE_FILES[mode]))
                self.assertEqual(inspect(root/'saved')['status'],'COMPLETE')
                resumed=export_finished_session(report,root/'saved',
                    runner=lambda *_a,**_k:self.fail('Verified raw must not transfer again'),scp='scp',key=key,known=known)
                self.assertEqual(resumed['status'],'COMPLETE')
                if mode=='localize':
                    def missing_reference(command,**kwargs):
                        if Path(command[-1]).name=='survey-reference.json.part':
                            return subprocess.CompletedProcess(command,1,b'',b'not found')
                        return transfer(command,**kwargs)
                    partial=export_finished_session(report,root/'missing-reference',runner=missing_reference,
                        scp='scp',key=key,known=known)
                    self.assertEqual(partial['status'],'INCOMPLETE')
                    self.assertEqual(inspect(root/'missing-reference')['status'],'INCOMPLETE')
                    copied.clear()
                    recovered=export_finished_session(report,root/'missing-reference',runner=transfer,
                        scp='scp',key=key,known=known)
                    self.assertEqual(copied,['survey-reference.json'])
                    self.assertEqual(recovered['status'],'COMPLETE')
                    self.assertEqual(inspect(root/'missing-reference')['status'],'COMPLETE')
                    invalid={**recovered,'schema_version':'unknown-localize-schema'}
                    (root/'missing-reference/export.json').write_text(json.dumps(invalid),encoding='utf-8')
                    with self.assertRaisesRegex(ValueError,'EXPORT_SCHEMA_INVALID'):
                        inspect(root/'missing-reference')

    def test_unsafe_receipt_path_stops_before_any_transfer(self):
        report={'robot_session_id':'manual-'+'1'*32,'mode':'off',
                'boot_id':'boot-one','release_id':'release-one'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            destination=root/'saved'
            destination.mkdir()
            (destination/'export.json').mkdir()
            key,known=root/'key',root/'known'
            key.write_text('fixture');known.write_text('fixture')
            with self.assertRaisesRegex(ValueError,'EVIDENCE_RECEIPT_PATH_UNSAFE'):
                export_finished_session(report,destination,
                                        runner=lambda *_a,**_k:self.fail('transport called'),
                                        scp='scp',key=key,known=known)

    def test_unsafe_staging_path_is_incomplete_without_using_it(self):
        report={'robot_session_id':'manual-'+'2'*32,'mode':'off',
                'boot_id':'boot-two','release_id':'release-two'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            destination=root/'saved'
            destination.mkdir()
            (destination/'before.log.part').mkdir()
            key,known=root/'key',root/'known'
            key.write_text('fixture');known.write_text('fixture')
            calls=[]
            def transfer(command,**_):
                name=Path(command[-1]).name.removesuffix('.part')
                calls.append(name)
                Path(command[-1]).write_text(json.dumps(report) if name=='report.json' else name)
                return subprocess.CompletedProcess(command,0,b'',b'')
            receipt=export_finished_session(report,destination,runner=transfer,
                                            scp='scp',key=key,known=known)
            self.assertEqual(receipt['status'],'INCOMPLETE')
            self.assertEqual(receipt['files']['before.log']['status'],'LOCAL_PATH_UNSAFE_OR_STALE')
            self.assertNotIn('before.log',calls)
            self.assertTrue((destination/'before.log.part').is_dir())

    def test_offline_inspector_file_contract_matches_both_exporters(self):
        self.assertEqual(SESSION_FILES, MODE_FILES)
        self.assertEqual(STATIONARY_FILES, EXPORTED_STATIONARY_FILES)
        for mode in ('qualify_scan','control_scan','scan'):
            self.assertTrue({'driver.log','telemetry.json','ros-messages.raw',
                             'ros-messages.raw.footer.json'}<=set(MODE_FILES[mode]))

    def test_forged_complete_receipt_cannot_omit_required_files_or_report_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'robot_session_id':'manual-'+'e'*32, 'mode':'control',
                      'boot_id':'boot-five', 'release_id':'release-five'}
            (root/'report.json').write_text(json.dumps(report), encoding='utf-8')
            data = (root/'report.json').read_bytes()
            receipt = {'schema_version':'robot-session-export-1',
                       'robot_session_id':report['robot_session_id'], 'mode':'control',
                       'robot_originals_retained':True, 'binding':'VERIFIED',
                       'status':'COMPLETE', 'files':{'report.json':{
                           'status':'COPIED', 'bytes':len(data),
                           'sha256':hashlib.sha256(data).hexdigest()}}}
            (root/'export.json').write_text(json.dumps(receipt), encoding='utf-8')
            result = inspect(root)
            self.assertEqual(result['status'],'INCOMPLETE')
            self.assertIn('EXPORT_FILE_SET_MISMATCH',result['contract_errors'])
            self.assertEqual(result['raw_ros']['reason'],'RAW_FILES_NOT_VERIFIED')
            receipt['mode']='off'
            report['mode']='off'
            (root/'report.json').write_text(json.dumps(report),encoding='utf-8')
            data=(root/'report.json').read_bytes()
            receipt['files']['report.json'].update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            receipt['files'].update({name:{'status':'COPIED', 'bytes':len(name),
                                           'sha256':hashlib.sha256(name.encode()).hexdigest()}
                                     for name in MODE_FILES['off'] if name!='report.json'})
            for name in MODE_FILES['off']:
                if name!='report.json':
                    (root/name).write_text(name,encoding='utf-8')
            (root/'export.json').write_text(json.dumps(receipt),encoding='utf-8')
            self.assertEqual(inspect(root)['status'],'COMPLETE')
            report['robot_session_id']='manual-'+'f'*32
            (root/'report.json').write_text(json.dumps(report),encoding='utf-8')
            data=(root/'report.json').read_bytes()
            receipt['files']['report.json'].update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            (root/'export.json').write_text(json.dumps(receipt),encoding='utf-8')
            result=inspect(root)
            self.assertEqual(result['status'],'INCOMPLETE')
            self.assertIn('SESSION_REPORT_BINDING_MISMATCH',result['contract_errors'])

    def test_stationary_receipt_cannot_claim_complete_without_raw_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            report={'run_id':'20260930T010203Z-abcdef01'}
            (root/'report.json').write_text(json.dumps(report),encoding='utf-8')
            data=(root/'report.json').read_bytes()
            receipt={'schema_version':'robot-evidence-export-1','run_id':report['run_id'],
                     'robot_originals_retained':True,'raw_replay':{'status':'VERIFIED_OFFLINE'},
                     'report_binding':{'status':'VERIFIED_SAME_RUN'},'status':'COMPLETE',
                     'files':{'report.json':{'status':'COPIED','bytes':len(data),
                                           'sha256':hashlib.sha256(data).hexdigest()}}}
            (root/'export.json').write_text(json.dumps(receipt),encoding='utf-8')
            result=inspect(root)
            self.assertEqual(result['status'],'INCOMPLETE')
            self.assertIn('EXPORT_FILE_SET_MISMATCH',result['contract_errors'])

    def test_ambiguous_receipt_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'export.json').write_text('{"schema_version":"robot-session-export-1",'
                                            '"schema_version":"robot-evidence-export-1"}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'EVIDENCE_JSON_DUPLICATE_KEY'):
                inspect(root)
            with patch.object(sys,'argv',['inspect_robot_evidence',str(root)]), patch('builtins.print') as printed:
                self.assertEqual(main(),2)
            self.assertEqual(json.loads(printed.call_args.args[0])['reason'],'EVIDENCE_JSON_DUPLICATE_KEY')

    def test_ros_decoder_adapter_uses_allowlisted_message_class_and_exact_bytes(self):
        rclpy=ModuleType('rclpy');rclpy.__path__=[]
        serialization=ModuleType('rclpy.serialization')
        nav=ModuleType('nav_msgs');nav.__path__=[]
        nav_msg=ModuleType('nav_msgs.msg')
        class Odometry:pass
        nav_msg.Odometry=Odometry
        serialization.deserialize_message=lambda payload,kind:(payload,kind)
        with patch.dict(sys.modules,{'rclpy':rclpy,'rclpy.serialization':serialization,
                                     'nav_msgs':nav,'nav_msgs.msg':nav_msg}):
            decoder=ros_decoder()
            self.assertEqual(decoder(b'\x00\xff','nav_msgs/msg/Odometry'),(b'\x00\xff',Odometry))
            with self.assertRaisesRegex(ValueError,'ROS_TYPE_NOT_ALLOWLISTED'):
                decoder(b'x','other_msgs/msg/Thing')

    def test_control_and_localize_raw_must_bind_to_worker_report_not_just_its_footer(self):
        for mode in ('control','localize'):
            with self.subTest(mode=mode):
                self._check_report_raw_binding(mode)

    def _check_report_raw_binding(self,mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'
            source.mkdir()
            raw = RawRosRecorder(source/'ros-messages.raw',serializer=lambda value:value)
            self.assertTrue(raw.record('odom',b'original'))
            footer = raw.close()
            report = {'robot_session_id':'manual-'+'b'*32,'mode':mode,
                      'boot_id':'boot-two','release_id':'release-two','raw_ros':footer}
            (source/'report.json').write_text(json.dumps(report),encoding='utf-8')
            for name in MODE_FILES[mode]:
                if not (source/name).exists():
                    (source/name).write_text(name,encoding='utf-8')
            key,known=root/'key',root/'known'
            key.write_text('fixture');known.write_text('fixture')
            def transfer(command,**_):
                name=Path(command[-1]).name.removesuffix('.part')
                Path(command[-1]).write_bytes((source/name).read_bytes())
                return subprocess.CompletedProcess(command,0,b'',b'')
            result=export_finished_session(report,root/'saved',runner=transfer,
                                           scp='scp',key=key,known=known)
            self.assertEqual(result['status'],'COMPLETE')
            unavailable=inspect(root/'saved',require_decode=True)
            self.assertEqual(unavailable['status'],'INCOMPLETE')
            self.assertEqual(unavailable['raw_ros']['message_decode'],'ROS_DECODER_UNAVAILABLE')
            decoded=inspect(root/'saved',decoder=lambda payload,kind:(kind,payload),require_decode=True)
            self.assertEqual(decoded['status'],'COMPLETE')
            self.assertEqual(decoded['raw_ros']['message_decode'],'CUSTOM_DECODER_COMPLETE')
            self.assertEqual(decoded['raw_ros']['decoded_messages'],1)
            self.assertEqual(decoded['raw_ros']['message_diagnostics']['examples'][0]['reason'],'MESSAGE_SHAPE')
            rejected_decode=inspect(root/'saved',decoder=lambda *_: (_ for _ in ()).throw(ValueError('bad CDR')),
                                    require_decode=True)
            self.assertEqual(rejected_decode['status'],'INCOMPLETE')
            self.assertIn('RAW_MESSAGE_DECODE_FAILED_SEQUENCE_0',rejected_decode['raw_ros']['reason'])
            report['raw_ros']={**footer,'sha256':'0'*64}
            (source/'report.json').write_text(json.dumps(report),encoding='utf-8')
            rejected=export_finished_session(report,root/'changed',runner=transfer,
                                             scp='scp',key=key,known=known)
            self.assertEqual(rejected['status'],'INCOMPLETE')
            self.assertEqual(rejected['binding'],'REJECTED')

    def test_complete_off_session_and_missing_file_is_explicit(self):
        report = {'robot_session_id':'manual-'+'a'*32,'mode':'off',
                  'boot_id':'boot-one','release_id':'release-one'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key, known = root/'key', root/'known'
            key.write_text('fixture')
            known.write_text('fixture')
            def transfer(command, **_):
                name = Path(command[-1]).name.removesuffix('.part')
                if name == 'report.json':
                    Path(command[-1]).write_text(json.dumps(report))
                else:
                    Path(command[-1]).write_text(name)
                return subprocess.CompletedProcess(command,0,b'',b'')
            result = export_finished_session(report,root/'saved',runner=transfer,
                                             scp='scp',key=key,known=known)
            self.assertEqual(result['status'],'COMPLETE')
            self.assertEqual(result['binding'],'VERIFIED')
            self.assertEqual(set(result['files']),set(MODE_FILES['off']))
            self.assertEqual(inspect(root/'saved')['status'],'COMPLETE')
            resumed = export_finished_session(report,root/'saved',
                runner=lambda *_a,**_k:self.fail('verified files must not be fetched again'),
                scp='scp',key=key,known=known)
            self.assertEqual(resumed['status'],'COMPLETE')
            (root/'saved/off.log').write_text('tampered')
            self.assertEqual(inspect(root/'saved')['status'],'INCOMPLETE')
            fetched = []
            def repair(command, **kwargs):
                fetched.append(Path(command[-1]).name)
                return transfer(command,**kwargs)
            repaired = export_finished_session(report,root/'saved',runner=repair,
                                               scp='scp',key=key,known=known)
            self.assertEqual(fetched,['off.log.part'])
            self.assertEqual(repaired['status'],'COMPLETE')
            def missing(command, **kwargs):
                if Path(command[-1]).name == 'before.log.part':
                    return subprocess.CompletedProcess(command,1,b'',b'not found')
                return transfer(command,**kwargs)
            partial = export_finished_session(report,root/'partial',runner=missing,
                                              scp='scp',key=key,known=known)
            self.assertEqual(partial['status'],'INCOMPLETE')
            self.assertEqual(partial['files']['before.log']['status'],'MISSING_OR_TRANSFER_FAILED')
            fetched.clear()
            recovered = export_finished_session(report,root/'partial',runner=repair,
                                                scp='scp',key=key,known=known)
            self.assertEqual(fetched,['before.log.part'])
            self.assertEqual(recovered['status'],'COMPLETE')

    def test_rehashed_malformed_raw_cannot_make_complete_export(self):
        for mode in ('control','localize'):
            with self.subTest(mode=mode):
                self._check_malformed_raw(mode)

    def _check_malformed_raw(self,mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'
            source.mkdir()
            raw_path = source/'ros-messages.raw'
            recorder = RawRosRecorder(raw_path, serializer=lambda value:value)
            self.assertTrue(recorder.record('odom', b'original'))
            footer = recorder.close()
            original = raw_path.read_bytes()
            offset = len(MAGIC)
            meta_size, payload_size = HEADER.unpack(original[offset:offset + HEADER.size])
            start = offset + HEADER.size
            metadata = json.loads(original[start:start + meta_size])
            metadata['receipt_monotonic_ns'] = -1
            encoded = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()
            payload = original[start + meta_size:start + meta_size + payload_size]
            changed = MAGIC + HEADER.pack(len(encoded), len(payload)) + encoded + payload
            raw_path.write_bytes(changed)
            footer['bytes'] = len(changed)
            footer['sha256'] = hashlib.sha256(changed).hexdigest()
            (source/'ros-messages.raw.footer.json').write_text(json.dumps(footer))
            report = {'robot_session_id':'manual-'+'c'*32,'mode':mode,
                      'boot_id':'boot-three','release_id':'release-three','raw_ros':footer}
            (source/'report.json').write_text(json.dumps(report))
            for name in MODE_FILES[mode]:
                if not (source/name).exists():
                    (source/name).write_text(name)
            key,known=root/'key',root/'known'
            key.write_text('fixture');known.write_text('fixture')
            def transfer(command,**_):
                name=Path(command[-1]).name.removesuffix('.part')
                Path(command[-1]).write_bytes((source/name).read_bytes())
                return subprocess.CompletedProcess(command,0,b'',b'')
            result=export_finished_session(report,root/'saved',runner=transfer,
                                           scp='scp',key=key,known=known)
            self.assertEqual(result['status'],'INCOMPLETE')
            self.assertEqual(result['binding'],'REJECTED')
            self.assertIn('RAW_FRAME_METADATA_INVALID',result['binding_reason'])
            self.assertEqual(inspect(root/'saved')['status'],'INCOMPLETE')

    def test_invalid_remote_report_id_is_rejected_before_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'ROBOT_EVIDENCE_ID_OR_MODE_INVALID'):
                export_finished_session({'robot_session_id':'../wrong','mode':'control'},directory,
                                        runner=lambda *_a,**_k:self.fail('transport called'))

    def test_stale_generated_partial_is_discarded_and_refetched(self):
        report={'robot_session_id':'manual-'+'d'*32,'mode':'off',
                'boot_id':'boot-four','release_id':'release-four'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); destination=root/'saved';destination.mkdir()
            stale=destination/'before.log.part';stale.write_text('preserved partial')
            key,known=root/'key',root/'known';key.write_text('fixture');known.write_text('fixture')
            fetched=[]
            def transfer(command,**_):
                name=Path(command[-1]).name.removesuffix('.part')
                fetched.append(name)
                Path(command[-1]).write_text(json.dumps(report) if name=='report.json' else name)
                return subprocess.CompletedProcess(command,0,b'',b'')
            receipt=export_finished_session(report,destination,runner=transfer,
                                            scp='scp',key=key,known=known)
            self.assertEqual(receipt['status'],'COMPLETE')
            self.assertTrue(receipt['files']['before.log']['stale_partial_discarded'])
            self.assertFalse(stale.exists())
            self.assertIn('before.log',fetched)


if __name__=='__main__':
    unittest.main()
