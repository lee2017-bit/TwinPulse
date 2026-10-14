# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded offline CDR1 decoder for the three mapping ROS message types.

No ROS installation or device access. Encapsulation, alignment, strings and
sequence budgets are checked; unknown encodings are rejected, not guessed.
"""
import math
import struct


class Cdr:
    def __init__(self, data):
        if not isinstance(data, bytes) or not 4 <= len(data) <= 8 * 1024 * 1024:
            raise ValueError('CDR_SIZE')
        if data[:4] not in (b'\x00\x01\x00\x00', b'\x00\x00\x00\x00'):
            raise ValueError('CDR_ENCODING_UNSUPPORTED')
        self.data, self.pos, self.order = data, 4, '<' if data[1] == 1 else '>'

    def take(self, fmt, alignment):
        self.pos += (-(self.pos - 4)) % alignment
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data): raise ValueError('CDR_TRUNCATED')
        value = struct.unpack_from(self.order + fmt, self.data, self.pos)
        self.pos += size
        return value[0] if len(value) == 1 else list(value)

    def string(self):
        count = self.take('I', 4)
        if not 1 <= count <= 256 or self.pos + count > len(self.data):
            raise ValueError('CDR_STRING_SIZE')
        value = self.data[self.pos:self.pos + count]; self.pos += count
        if value[-1] != 0 or b'\0' in value[:-1]: raise ValueError('CDR_STRING_TERMINATOR')
        try: return value[:-1].decode('utf-8')
        except UnicodeError as exc: raise ValueError('CDR_STRING_ENCODING') from exc

    def header(self):
        sec, ns = self.take('i', 4), self.take('I', 4)
        if sec < 0 or ns >= 1_000_000_000: raise ValueError('CDR_TIMESTAMP')
        return {'stamp_ns': sec * 1_000_000_000 + ns, 'frame_id': self.string()}

    def doubles(self, count):
        values = self.take(str(count) + 'd', 8)
        if not all(math.isfinite(v) for v in values): raise ValueError('CDR_NONFINITE_POSE')
        return values

    def floats(self):
        count = self.take('I', 4)
        if count > 4096: raise ValueError('CDR_ARRAY_BUDGET')
        return [self.take('f', 4) for _ in range(count)]

    def finish(self):
        tail = self.data[self.pos:]
        if len(tail) > 7 or any(tail): raise ValueError('CDR_TRAILING_BYTES')


def decode_mapping_message(kind, data):
    reader = Cdr(data)
    if kind == 'sensor_msgs/msg/LaserScan':
        result = reader.header()
        keys = ('angle_min', 'angle_max', 'angle_increment', 'time_increment',
                'scan_time', 'range_min', 'range_max')
        result.update(zip(keys, [reader.take('f', 4) for _ in keys]))
        ranges, intensities = reader.floats(), reader.floats()
        if not all(math.isfinite(result[k]) for k in keys): raise ValueError('SCAN_METADATA_NONFINITE')
        if (not 0 < abs(result['angle_increment']) < math.tau or
            not 0 <= result['time_increment'] <= .1 or not 0 <= result['scan_time'] <= 2 or
            not 0 <= result['range_min'] < result['range_max'] <= 1000 or not ranges or
            len(intensities) not in (0, len(ranges)) or
            (len(ranges)-1)*abs(result['angle_increment']) > math.tau+.001 or
            (result['angle_max']-result['angle_min'])*result['angle_increment'] < 0):
            raise ValueError('SCAN_METADATA_INCONSISTENT')
        result['ranges_m'] = [v if math.isfinite(v) and result['range_min'] <= v <= result['range_max'] else None for v in ranges]
        # Decode the declared metadata without inventing a terminal bin. The
        # existing live navigation contract is stricter and is NOT changed here.
        result['declared_end_gap_rad'] = result['angle_max']-result['angle_min']-(len(ranges)-1)*result['angle_increment']
        directed_gap=result['declared_end_gap_rad']*(1 if result['angle_increment']>0 else -1)
        if not -.02 <= directed_gap <= .1:raise ValueError('SCAN_ANGLE_DECLARATION')
        result['invalid_returns'] = sum(v is None for v in result['ranges_m'])
        result['intensities'] = [v if math.isfinite(v) else None for v in intensities]
    elif kind == 'nav_msgs/msg/Odometry':
        result = reader.header(); result['child_frame_id'] = reader.string()
        result['position_m'] = reader.doubles(3)
        result['quaternion_xyzw'] = reader.doubles(4)
        result['pose_covariance'] = reader.doubles(36)
        result['twist'] = reader.doubles(6)
        result['twist_covariance'] = reader.doubles(36)
    elif kind == 'tf2_msgs/msg/TFMessage':
        count = reader.take('I', 4)
        if count > 128: raise ValueError('TF_SEQUENCE_BUDGET')
        items = []
        for _ in range(count):
            item = reader.header(); item['child_frame_id'] = reader.string()
            item['translation_m'] = reader.doubles(3)
            item['quaternion_xyzw'] = reader.doubles(4); items.append(item)
        result = {'transforms': items}
    else: raise ValueError('CDR_TYPE_UNSUPPORTED')
    reader.finish()
    return result
