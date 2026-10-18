# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline integrity tests for exact-byte passive ROS recording."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from raw_ros_record import (HEADER, MAGIC, RawRosRecorder, inspect_recording,
                            replay_recording)


class RawRecorderTests(unittest.TestCase):
    def test_callback_receipt_is_preserved_before_serialization(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ros-messages.raw';recorder=RawRosRecorder(path,serializer=lambda v:v,
                monotonic_ns=lambda:999)
            self.assertTrue(recorder.record('odom',b'raw',receipt_monotonic_ns=123))
            self.assertTrue(recorder.close()['complete'])
            self.assertEqual(inspect_recording(path)[0][0]['receipt_monotonic_ns'],123)

    def test_blocked_writer_close_is_bounded_and_never_writes_complete_footer(self):
        class BlockedStream:
            def __init__(self,original):self.original=original
            def write(self,data):entered.set();gate.wait(2);return self.original.write(data)
            def flush(self):self.original.flush()
            def close(self):self.original.close()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ros-messages.raw';gate=threading.Event();entered=threading.Event()
            recorder=RawRosRecorder(path,serializer=lambda v:v);recorder.stream=BlockedStream(recorder.stream)
            try:
                recorder.record('scan',b'raw');self.assertTrue(entered.wait(1));start=time.monotonic()
                result=recorder.close(timeout=.001)
                self.assertLess(time.monotonic()-start,.2);self.assertFalse(result['complete'])
                self.assertEqual(result['errors'],['RAW_WRITER_CLOSE_TIMEOUT'])
                self.assertFalse(path.with_suffix('.raw.footer.json').exists())
            finally:gate.set();recorder.writer.join(1)

    def test_subscriber_enqueue_does_not_wait_for_slow_disk_writer(self):
        class SlowStream:
            def __init__(self, original, gate):
                self.original, self.gate = original, gate

            def write(self, data):
                if not self.gate.wait(2):
                    raise OSError('timed out fixture writer')
                return self.original.write(data)

            def flush(self):
                self.original.flush()

            def close(self):
                self.original.close()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            gate = threading.Event()
            recorder = RawRosRecorder(path, serializer=lambda value: value)
            recorder.stream = SlowStream(recorder.stream, gate)
            start = time.monotonic()
            self.assertTrue(recorder.record('scan', b'raw'))
            self.assertLess(time.monotonic() - start, .2)
            gate.set()
            self.assertTrue(recorder.close()['complete'])
            self.assertEqual(inspect_recording(path)[0][1], b'raw')

    def test_bounded_queue_rejects_without_blocking_or_marking_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            recorder = RawRosRecorder(path, serializer=lambda message: message,
                                      max_pending_bytes=1)
            self.assertFalse(recorder.record('scan', b'data'))
            footer = recorder.close()
            self.assertIn('RAW_QUEUE_CAP_REACHED', footer['errors'][0])
            with self.assertRaisesRegex(ValueError, 'RAW_INCOMPLETE'):
                inspect_recording(path)

    def test_writer_error_is_explicit_and_keeps_partial_bundle(self):
        class FailingStream:
            def __init__(self, original):
                self.original = original

            def write(self, _):
                raise OSError('disk full')

            def flush(self):
                self.original.flush()

            def close(self):
                self.original.close()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            recorder = RawRosRecorder(path, serializer=lambda message: message)
            recorder.stream = FailingStream(recorder.stream)
            self.assertTrue(recorder.record('scan', b'data'))
            footer = recorder.close()
            self.assertFalse(footer['complete'])
            self.assertIn('disk full', footer['errors'][0])
            with self.assertRaisesRegex(ValueError, 'RAW_INCOMPLETE'):
                inspect_recording(path)

    def test_preserves_rejected_payload_bytes_and_nonfinite_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            recorder = RawRosRecorder(path, serializer=lambda message: message,
                                      monotonic_ns=lambda: 123)
            payloads = (b'odom\x00\xff\x7f\xf8\x00\x00', b'scan\x00\x01', b'tf\x00')
            for topic, payload in zip(('odom', 'scan', '/tf'), payloads):
                recorder.record(topic, payload)
            footer = recorder.close()
            self.assertEqual(recorder.close(), footer)
            frames = inspect_recording(path)
            self.assertEqual([data for _, data in frames], list(payloads))
            self.assertEqual([meta['sequence'] for meta, _ in frames], [0, 1, 2])
            self.assertEqual(footer['counts']['odom'], 1)
            self.assertEqual(footer['drop_counts']['odom'], 0)
            self.assertGreater(footer['queue_high_water_bytes'], 0)
            self.assertTrue(footer['complete'])
            decoded = replay_recording(path, lambda payload, kind: (kind, payload))
            self.assertEqual([item[1][1] for item in decoded], list(payloads))
            self.assertEqual(decoded[0][1][0], 'nav_msgs/msg/Odometry')
            with self.assertRaisesRegex(ValueError, 'RAW_MESSAGE_DECODE_FAILED_SEQUENCE_1'):
                replay_recording(path, lambda payload, _kind: (_ for _ in ()).throw(RuntimeError())
                                 if payload == payloads[1] else payload)

    def test_truncation_and_drops_never_look_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            recorder = RawRosRecorder(path, serializer=lambda message: message,
                                      max_bytes=200)
            recorder.record('odom', b'x' * 1024)
            footer = recorder.close()
            self.assertFalse(footer['complete'])
            self.assertEqual(footer['dropped'], 1)
            self.assertEqual(footer['drop_counts']['odom'], 1)
            with self.assertRaisesRegex(ValueError, 'RAW_INCOMPLETE'):
                inspect_recording(path)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            recorder = RawRosRecorder(path, serializer=lambda message: message)
            recorder.record('scan', b'first')
            recorder.close()
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'RAW_FRAME_TRUNCATED'):
                inspect_recording(path)

    def test_footer_tampering_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            recorder = RawRosRecorder(path, serializer=lambda message: message)
            recorder.record('scan', b'full-ranges')
            recorder.close()
            footer_path = path.with_suffix('.raw.footer.json')
            footer = json.loads(footer_path.read_text())
            footer['counts']['scan'] = 2
            footer_path.write_text(json.dumps(footer))
            with self.assertRaisesRegex(ValueError, 'RAW_INCOMPLETE'):
                inspect_recording(path)
            footer['counts']['scan'] = 1
            footer['path'] = 'other.raw'
            footer_path.write_text(json.dumps(footer))
            with self.assertRaisesRegex(ValueError, 'RAW_DIGEST_OR_SIZE_MISMATCH'):
                inspect_recording(path)

    def test_rehashed_invalid_frame_metadata_still_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            recorder = RawRosRecorder(path, serializer=lambda message: message)
            self.assertTrue(recorder.record('odom', b'original'))
            recorder.close()
            footer_path = path.with_suffix('.raw.footer.json')
            footer = json.loads(footer_path.read_text(encoding='utf-8'))
            original = path.read_bytes()
            offset = len(MAGIC)
            meta_size, payload_size = HEADER.unpack(original[offset:offset + HEADER.size])
            start = offset + HEADER.size
            meta = json.loads(original[start:start + meta_size])
            meta['receipt_monotonic_ns'] = -1
            encoded = json.dumps(meta, sort_keys=True, separators=(',', ':')).encode('utf-8')
            payload = original[start + meta_size:start + meta_size + payload_size]
            changed = MAGIC + HEADER.pack(len(encoded), len(payload)) + encoded + payload
            path.write_bytes(changed)
            footer['bytes'] = len(changed)
            footer['sha256'] = hashlib.sha256(changed).hexdigest()
            footer_path.write_text(json.dumps(footer), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'RAW_FRAME_METADATA_INVALID'):
                inspect_recording(path)

    def test_oversized_footer_is_rejected_before_json_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ros-messages.raw'
            recorder = RawRosRecorder(path, serializer=lambda message: message)
            recorder.close()
            path.with_suffix('.raw.footer.json').write_bytes(b' ' * (16 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, 'RAW_BUNDLE_SIZE_INVALID'):
                inspect_recording(path)


if __name__ == '__main__':
    unittest.main()
