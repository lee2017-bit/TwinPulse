# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Offline native parser faults and original-byte replay; no device imports."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'packages/twinpulse_robot_safety'))
from native_stream import NativeDecoder, NativeStream

UNKNOWN = bytes.fromhex('a5 5a 04 00 fe 3a 06 39 00 00 00')


def packet(first=100, last=200, *, ring=False, bad=False):
    """Angles are upstream q6 integers; payload is a nonzero synthetic return."""
    count = 1 if ring else 2
    raw = bytearray(struct.pack('<2sBBHHH', b'\xaa\x55', int(ring), count,
        first*2+1, last*2+1, 0) + b'\x04\x04\x01'*count)
    checksum = 0x55aa ^ (int(ring) | count << 8) ^ (first*2+1) ^ (last*2+1)
    for at in range(10, len(raw), 3):
        checksum ^= raw[at] ^ int.from_bytes(raw[at+1:at+3], 'little')
    struct.pack_into('<H', raw, 8, checksum ^ int(bad))
    return bytes(raw)


class ObservedRings(NativeStream):
    def __init__(self):
        super().__init__('.', lambda *_: None, clock=lambda: 1.)
        self.stream_id = 'offline-not-hardware'
        self.summaries = []

    def _frame(self, packets, complete, **kwargs):
        super()._frame(packets, complete, **kwargs)
        frame = self.latest_frame()
        self.summaries.append({key: frame[key] for key in (
            'frame_sequence', 'complete', 'raw_sha256', 'nodes_sha256',
            'source_byte_span', 'quality', 'interval_fallback')})


class NativeQualityTests(unittest.TestCase):
    def test_corrupt_interval_cannot_contaminate_next_valid_fallback(self):
        good, corrupt, fallback = packet(), packet(100, 1000, bad=True), packet(1000, 900)
        decoder = NativeDecoder()
        decoder.feed(good, 1.)
        prior = decoder.previous_interval
        invalid = decoder.feed(corrupt, 1.1)[0]
        self.assertFalse(invalid['checksum_valid'])
        self.assertEqual(decoder.previous_interval, prior)
        actual = decoder.feed(fallback, 1.2)[0]
        reference = NativeDecoder()
        reference.feed(good, 1.)
        expected = reference.feed(fallback, 1.2)[0]
        self.assertTrue(actual['checksum_valid'])
        self.assertTrue(actual['interval_fallback'])
        self.assertEqual([n['angle_deg'] for n in actual['nodes']],
                         [n['angle_deg'] for n in expected['nodes']])
        self.assertTrue(all(n['distance_m'] == 0 for n in invalid['nodes']))

    def test_unknown_span_survives_every_split_without_whitelisting(self):
        first, second = packet(ring=True), packet()
        raw = first + UNKNOWN + second
        for split in range(1, len(raw)):
            with self.subTest(split=split):
                decoder = NativeDecoder()
                rows = decoder.feed(raw[:split], 1.) + decoder.feed(raw[split:], 1.1)
                self.assertEqual(len(rows), 2)
                gap = rows[1]['preceding_unframed']
                self.assertEqual((gap['start'], gap['end'], gap['length']),
                                 (len(first), len(first)+len(UNKNOWN), len(UNKNOWN)))
                self.assertEqual(gap['classification'], 'UNKNOWN')
                self.assertEqual(gap['raw_sha256'], hashlib.sha256(UNKNOWN).hexdigest())
                self.assertEqual(gap['prefix_hex'], UNKNOWN.hex(' '))
                self.assertEqual(decoder.packet_bytes+decoder.noise_bytes+len(decoder.buffer), len(raw))
                self.assertEqual(decoder.unframed_segments, 1)
                self.assertTrue(all(p['checksum_valid'] for p in rows))

    def test_unknown_between_rings_taints_closing_ring_once_and_keeps_all_nodes(self):
        start, normal = packet(ring=True), packet()
        raw = start + normal + UNKNOWN + start + normal + start
        for chunk_size in (1, 7, 17, len(raw)):
            with self.subTest(chunk_size=chunk_size):
                decoder, stream = NativeDecoder(), ObservedRings()
                count = 0
                for offset in range(0, len(raw), chunk_size):
                    rows = decoder.feed(raw[offset:offset+chunk_size], 1.)
                    count += sum(len(p['nodes']) for p in rows)
                    stream._accept_packets(rows)
                self.assertEqual(count, 7)
                self.assertEqual([s['complete'] for s in stream.summaries], [False, True])
                quality = stream.summaries[0]['quality']
                self.assertTrue(quality['packet_contiguous'])
                self.assertEqual(quality['unframed_bytes'], len(UNKNOWN))
                self.assertEqual(len(quality['unframed_spans']), 1)
                self.assertEqual(stream.summaries[1]['quality']['unframed_spans'], ())
                self.assertEqual(stream.summaries[0]['raw_sha256'], hashlib.sha256(start+normal).hexdigest())

    def test_unknown_inside_ring_is_not_hidden_by_valid_scan_checksums(self):
        decoder, stream = NativeDecoder(), ObservedRings()
        stream._accept_packets(decoder.feed(packet(ring=True)+UNKNOWN+packet()+packet(ring=True), 1.))
        quality = stream.summaries[0]['quality']
        self.assertFalse(stream.summaries[0]['complete'])
        self.assertFalse(quality['packet_contiguous'])
        self.assertEqual(quality['checksum_invalid_packets'], 0)
        self.assertEqual(quality['unframed_bytes'], len(UNKNOWN))

    def test_invalid_header_and_truncated_tail_have_exact_byte_accounting(self):
        invalid = b'\xaa\x55\x00\xff' + b'\x01'*6
        raw = invalid + packet() + UNKNOWN + b'\xaa\x55\x01'
        decoder = NativeDecoder()
        rows = decoder.feed(raw, 1.)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['preceding_unframed']['length'], len(invalid))
        self.assertEqual(decoder.noise_bytes, len(invalid)+len(UNKNOWN))
        self.assertEqual(decoder.pending_unframed()['raw_sha256'], hashlib.sha256(UNKNOWN).hexdigest())
        self.assertEqual(bytes(decoder.buffer), b'\xaa\x55\x01')
        self.assertEqual(decoder.packet_bytes+decoder.noise_bytes+len(decoder.buffer), len(raw))
        self.assertEqual(decoder.unframed_segments, 2)

    def test_saved_full_original_stream_preserves_201_unknown_gaps_and_202_incomplete_rings(self):
        folder = ROOT/'outputs/robot-retest-20261018/analysis'
        if not (folder/'native-original.raw').is_file():
            self.skipTest('Preserved local raw fixture is unavailable; hardware acceptance is not implied')
        raw = (folder/'native-original.raw').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '7a50ff3fec3cb24e500faead1e5b5d0caeea8b0654ad2db615aa491ebaa21522')
        chunks = json.loads((folder/'native-chunks.json').read_text())
        original = json.loads((folder/'native-replay.json').read_text())
        decoder, stream = NativeDecoder(), ObservedRings()
        packets = nodes = fallbacks = 0
        for chunk in chunks:
            data = raw[chunk['offset']:chunk['offset']+chunk['length']]
            self.assertEqual(hashlib.sha256(data).hexdigest(), chunk['sha256'])
            rows = decoder.feed(data, chunk['receipt_end_s'])
            packets += len(rows)
            nodes += sum(len(p['nodes']) for p in rows)
            fallbacks += sum(p['interval_fallback'] for p in rows)
            stream._accept_packets(rows)
        self.assertEqual((packets, nodes, fallbacks, decoder.errors), (103514, 2433198, 1, 0))
        self.assertEqual((len(stream.summaries), sum(not f['complete'] for f in stream.summaries)), (6081, 202))
        self.assertEqual((decoder.packet_bytes, decoder.noise_bytes, len(decoder.buffer)), (8334734, 2259, 0))
        self.assertEqual(decoder.packet_bytes+decoder.noise_bytes+len(decoder.buffer), len(raw))
        gaps = [(f['frame_sequence'], g) for f in stream.summaries for g in f['quality']['unframed_spans']]
        self.assertEqual(len(gaps), 202)  # 48 startup bytes plus all 201 periodic unknown spans.
        periodic = [(frame, g) for frame, g in gaps if g['length'] == 11]
        self.assertEqual(len(periodic), 201)
        self.assertEqual([(f, g['start'], g['end']) for f, g in periodic],
                         [(g['frame'], g['start'], g['end']) for g in original['gaps']])
        for _, gap in gaps:
            self.assertEqual(gap['classification'], 'UNKNOWN')
            self.assertEqual(gap['raw_sha256'], hashlib.sha256(raw[gap['start']:gap['end']]).hexdigest())
        failed = stream.summaries[392]
        self.assertFalse(failed['complete'])
        self.assertEqual(failed['quality']['unframed_spans'][0]['prefix_hex'], UNKNOWN.hex(' '))


if __name__ == '__main__':
    unittest.main()
