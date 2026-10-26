# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""No devices: session-storage guard, start-refusal detail and the stderr cleanup receipt.

phys09 (2026-10-26): the robot SD card was 100% full, the journal met ENOSPC mid-run, the
worker exited and the PC saw only 'FLEET_WORKER_REJECTED:OSError'. These tests pin the
fail-closed replacements: refuse before devices, fault with a named reason, say why on stderr.
"""
import errno
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
import fleet_worker
from fleet_worker import (FleetWorker,InputLines,session_storage,rejection_detail,
    SESSION_DISK_RESERVE_BYTES,SESSION_DISK_FAULT_BYTES)


def context():
    return dict(schema='physical-live-start-1.0',operation_id='o'*32,robot_id='b'*32,project_id='default',
                connection_epoch='c'*32,binding_sha256='a'*64,worker_sha256='a'*64)


def usage_of(free):
    return lambda _:SimpleNamespace(total=64*SESSION_DISK_RESERVE_BYTES,used=0,free=free)


class Control:
    def __init__(self,*_,**__):self.stop_requested=threading.Event();self.cancel=threading.Event();self.field_until=1.
    def start(self):pass
    def snapshot(self):
        return dict(control_state='UNPREPARED',blockers=['UNPREPARED'],drive_ready=False,
                    battery=dict(voltage_v=11.9,percent=None,source='measured',sample_monotonic_s=None))
    def close(self):return dict(control_state='CLOSED',worker_reaped=True,cleanup_confirmed=True)


class Native:
    def __init__(self,*_):pass
    def latest_frame(self):return None
    def snapshot(self):return {'lidar_state':'OFF'}
    def stop(self):pass
    def close(self):return {'lidar_state':'OFF'}


class SessionStorageTests(unittest.TestCase):
    def test_free_space_states_and_unknown_on_statvfs_failure(self):
        self.assertEqual(session_storage('/x',usage=usage_of(SESSION_DISK_RESERVE_BYTES))['state'],'OK')
        low=session_storage('/x',usage=usage_of(SESSION_DISK_RESERVE_BYTES-1))
        self.assertEqual((low['state'],low['free_bytes'],low['reserve_bytes']),
                         ('LOW',SESSION_DISK_RESERVE_BYTES-1,SESSION_DISK_RESERVE_BYTES))
        def broken(_):raise OSError(errno.EIO,'Input/output error')
        unknown=session_storage('/x',usage=broken)
        self.assertEqual((unknown['state'],unknown['free_bytes'],unknown['reason']),('UNKNOWN',None,'OSError'))
        self.assertLess(SESSION_DISK_FAULT_BYTES,SESSION_DISK_RESERVE_BYTES)

    def test_rejection_detail_names_errno_strerror_and_path_on_one_printable_line(self):
        path='/home/ubuntu/.local/share/twinpulse/fleet/sessions/'+'o'*32
        self.assertEqual(rejection_detail(OSError(errno.ENOSPC,'No space left on device',path)),
                         'OSError:ENOSPC:No space left on device:'+path)
        self.assertEqual(rejection_detail(ValueError('WORKER_BUNDLE_MISMATCH')),'WORKER_BUNDLE_MISMATCH')
        self.assertEqual(rejection_detail(ValueError('not a code')),'ValueError')
        self.assertEqual(rejection_detail(OSError('plain')),'OSError:NO_ERRNO::')
        detail=rejection_detail(OSError(errno.EACCES,'bad\nline\x00','/p\n'))
        self.assertNotIn('\n',detail);self.assertNotIn('\x00',detail)
        self.assertEqual(detail,'PermissionError:EACCES:bad?line?:/p?')  # the concrete OSError subclass is the class
        self.assertLessEqual(len(rejection_detail(OSError(errno.ENAMETOOLONG,'x'*500,'/'+'y'*500))),300)

    def test_main_refuses_a_low_disk_before_release_board_or_device_access(self):
        line=(json.dumps(context())+'\n').encode()
        with patch.object(fleet_worker.sys,'argv',['fleet_worker.py']), \
                patch.object(fleet_worker.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(line))), \
                patch.dict(os.environ,TWINPULSE_FLEET_BUNDLE_SHA256='a'*64), \
                patch.object(fleet_worker,'session_storage',return_value=dict(free_bytes=100*1024*1024,
                    reserve_bytes=SESSION_DISK_RESERVE_BYTES,state='LOW')) as probe, \
                patch.object(fleet_worker,'FleetWorker',side_effect=AssertionError('worker constructed')), \
                patch.object(Path,'read_text',side_effect=AssertionError('boot id read')), \
                patch.object(Path,'mkdir',side_effect=AssertionError('session directory created')):
            with self.assertRaisesRegex(ValueError,'^SESSION_DISK_LOW_100MB_FREE$'):fleet_worker.main()
        self.assertEqual(probe.call_count,1)
        self.assertEqual(rejection_detail(ValueError('SESSION_DISK_LOW_100MB_FREE')),'SESSION_DISK_LOW_100MB_FREE')

    def test_main_still_rejects_a_wrong_bundle_before_touching_storage(self):
        value=context();value['worker_sha256']='b'*64
        line=(json.dumps(value)+'\n').encode()
        with patch.object(fleet_worker.sys,'argv',['fleet_worker.py']), \
                patch.object(fleet_worker.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(line))), \
                patch.dict(os.environ,TWINPULSE_FLEET_BUNDLE_SHA256='a'*64), \
                patch.object(fleet_worker,'session_storage',side_effect=AssertionError('storage probed')):
            with self.assertRaisesRegex(ValueError,'^WORKER_BUNDLE_MISMATCH$'):fleet_worker.main()


class StorageGuardWorkerTests(unittest.TestCase):
    def worker(self,tmp,events,**kwargs):
        worker=FleetWorker(context(),tmp,events.append,control_factory=Control,native_factory=Native,**kwargs)
        worker.context.update(boot_id='b'*32,release_id='c'*64)
        worker._idle_board=lambda:None
        return worker

    def test_heartbeat_carries_storage_and_the_fault_line_fails_closed_before_enospc(self):
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=self.worker(tmp,events)
            self.assertIn(worker.heartbeat()['storage']['state'],('OK','LOW','UNKNOWN'))
            free=[SESSION_DISK_FAULT_BYTES]
            worker.storage_probe=lambda:dict(free_bytes=free[0],reserve_bytes=SESSION_DISK_RESERVE_BYTES,state='LOW')
            worker._sample_storage()
            # LOW but still above the fault line: shown, not faulted (the start refusal owns the reserve).
            self.assertFalse(worker.recording_failed)
            beat=worker.heartbeat()
            self.assertEqual((beat['storage']['state'],beat['storage']['free_bytes']),('LOW',SESSION_DISK_FAULT_BYTES))
            self.assertNotIn('RECORDING_INCOMPLETE',beat['blockers'])
            free[0]=SESSION_DISK_FAULT_BYTES-1
            worker._sample_storage()
            self.assertTrue(worker.recording_failed);self.assertEqual(worker.recording_failure_reason,'SESSION_DISK_LOW')
            self.assertTrue(worker.control.stop_requested.is_set());self.assertTrue(worker.control.cancel.is_set())
            self.assertEqual(worker.control.field_until,0.)
            beat=worker.heartbeat()
            self.assertIn('RECORDING_INCOMPLETE',beat['blockers']);self.assertFalse(beat['drive_ready'])
            self.assertEqual(beat['recording_failure_reason'],'SESSION_DISK_LOW')
            # A later UNKNOWN probe (statvfs failed) neither clears the fault nor renames it.
            worker.storage_probe=lambda:dict(free_bytes=None,reserve_bytes=SESSION_DISK_RESERVE_BYTES,state='UNKNOWN',reason='OSError')
            worker._sample_storage()
            self.assertEqual(worker.recording_failure_reason,'SESSION_DISK_LOW')
            self.assertEqual(worker.heartbeat()['storage']['state'],'UNKNOWN')
            worker.journal.close();worker.protocol.close()

    def test_unknown_storage_alone_never_faults_the_session(self):
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=self.worker(tmp,events)
            worker.storage_probe=lambda:dict(free_bytes=None,reserve_bytes=SESSION_DISK_RESERVE_BYTES,state='UNKNOWN',reason='OSError')
            worker._sample_storage()
            self.assertFalse(worker.recording_failed);self.assertFalse(worker.control.stop_requested.is_set())
            worker.journal.close();worker.protocol.close()

    def test_cleanup_verdict_reaches_stderr_receipt_and_matches_the_terminal_ack(self):
        lines=[];events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=self.worker(tmp,events,receipt_writer=lines.append)
            incoming=InputLines(io.BytesIO(b''));incoming.failed.wait(1)
            self.assertEqual(worker.run(incoming),0)
            self.assertEqual(len(lines),1)
            self.assertTrue(lines[0].startswith('FLEET_WORKER_CLEANUP:'));self.assertTrue(lines[0].endswith('\n'))
            self.assertEqual(lines[0].count('\n'),1)
            verdict=json.loads(lines[0][len('FLEET_WORKER_CLEANUP:'):])
            final=events[-1]['data'];self.assertEqual(final['subsystem'],'session')
            self.assertEqual(verdict,dict(confirmed=True,reason=final['reason'],recording_complete=True,
                recording_failure_reason=None,control_state='CLOSED',lidar_state='OFF',journal_error=None))
            self.assertEqual(verdict['reason'],'INPUT_EOF')
            self.assertTrue(json.loads((Path(tmp)/'receipt.json').read_text())['complete'])

    def test_stderr_receipt_names_the_first_recording_fault_and_never_promotes_completion(self):
        lines=[];events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=self.worker(tmp,events,receipt_writer=lines.append)
            worker._recording_fault('SESSION_DISK_LOW')
            incoming=InputLines(io.BytesIO(b''));incoming.failed.wait(1)
            worker.run(incoming)
            verdict=json.loads(lines[-1][len('FLEET_WORKER_CLEANUP:'):])
            self.assertTrue(verdict['confirmed']);self.assertFalse(verdict['recording_complete'])
            self.assertEqual(verdict['recording_failure_reason'],'SESSION_DISK_LOW')
            receipt=json.loads((Path(tmp)/'receipt.json').read_text())
            self.assertFalse(receipt['complete']);self.assertEqual(receipt['recording_failure_reason'],'SESSION_DISK_LOW')

    def test_a_failing_stderr_writer_cannot_block_cleanup_or_the_receipt(self):
        events=[]
        def broken(line):raise OSError(errno.EPIPE,'Broken pipe')
        with tempfile.TemporaryDirectory() as tmp:
            worker=self.worker(tmp,events,receipt_writer=broken)
            incoming=InputLines(io.BytesIO(b''));incoming.failed.wait(1)
            self.assertEqual(worker.run(incoming),0)
            self.assertTrue(events[-1]['data']['confirmed'])
            self.assertTrue(json.loads((Path(tmp)/'receipt.json').read_text())['complete'])

    def test_default_receipt_writer_is_inert_and_stderr_receipt_writes_fd_2(self):
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=self.worker(tmp,events)
            self.assertIsNone(worker.receipt_writer('FLEET_WORKER_CLEANUP:{}\n'))
            worker.journal.close();worker.protocol.close()
        writes=[]
        with patch.object(fleet_worker.os,'write',side_effect=lambda fd,data:writes.append((fd,data)) or len(data)):
            fleet_worker.stderr_receipt('FLEET_WORKER_CLEANUP:{"confirmed":true}\n')
        self.assertEqual(writes,[(2,b'FLEET_WORKER_CLEANUP:{"confirmed":true}\n')])


if __name__=='__main__':unittest.main()
