# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from recording_timestamp_contract import strictly_increasing_packet_times

class RecordingTimestampTests(unittest.TestCase):
    def test_original_one_millisecond_pair_is_valid_before_rescaling(self):
        self.assertTrue(strictly_increasing_packet_times([dict(pts=126680,dts=126680),dict(pts=126681,dts=126681)]))
    def test_invalid_original_clocks_are_never_hidden_by_passthrough(self):
        for rows in ([],[dict(pts=1,dts=1)], [dict(pts=1,dts=1),dict(pts=1,dts=2)],
                     [dict(pts=1,dts=1),dict(pts=2,dts=1)], [dict(pts=2,dts=2),dict(pts=1,dts=1)],
                     [dict(pts=1,dts=1),dict(pts=2)], [dict(pts=1,dts=1),dict(pts='2',dts=2)],
                     [dict(pts=1,dts=1),dict(pts=True,dts=2)], [dict(pts=1,dts=1),None]):
            with self.subTest(rows=rows):self.assertFalse(strictly_increasing_packet_times(rows))

if __name__=='__main__':unittest.main()
