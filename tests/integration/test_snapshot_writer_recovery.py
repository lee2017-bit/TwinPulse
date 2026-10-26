# SPDX-License-Identifier: Apache-2.0
"""2026-10-26 review #9: one failed snapshot write must not disable the writer for the session."""
from pathlib import Path
import tempfile
import time
import unittest

from tests.integration import test_r5_product_api  # noqa: F401  (adds package source paths)


class SnapshotWriterRecoveryTest(unittest.TestCase):
    def test_failed_write_is_recorded_and_a_later_write_clears_the_fault(self):
        from twinpulse_app.fleet_recorder import FleetSnapshotWriter
        writer=FleetSnapshotWriter()
        with tempfile.TemporaryDirectory() as tmp:
            blocker=Path(tmp,'file');blocker.write_text('x')
            writer.submit(blocker/'under-a-file.json',b'{}')  # mkdir fails: a file is in the way
            for _ in range(200):
                if writer.error:break
                time.sleep(.01)
            self.assertEqual(writer.error,'SNAPSHOT_WRITE_FAILED');self.assertTrue(writer.thread.is_alive())
            good=Path(tmp,'ok','snapshot.json')
            writer.submit(good,b'{}')  # accepted: the writer is still running
            for _ in range(200):
                if good.is_file() and writer.error is None:break
                time.sleep(.01)
            self.assertTrue(good.is_file());self.assertIsNone(writer.error);self.assertEqual(writer.failures,1)
            receipt=writer.close()
            # The lost snapshot stays on record: the session receipt is honest, the writer is not dead.
            self.assertFalse(receipt['complete']);self.assertEqual(receipt['failures'],1);self.assertIsNone(receipt['error'])


if __name__=='__main__':unittest.main()
