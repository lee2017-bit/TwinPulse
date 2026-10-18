# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic audit corruption tests, never live model success evidence."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.summarize_photo_output_campaign import checked_raw


class OutputAuditTests(unittest.TestCase):
    def test_late_length_raw_is_audited_without_claiming_generation_success(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.json'
            raw=json.dumps(dict(model='fixture-model',usage=dict(completion_tokens=10000),
                choices=[dict(finish_reason='length',message=dict(content=None))])).encode()
            evidence=dict(attempt_id='fixture',model_id='fixture-model',max_tokens=10000,
                response_redacted=raw.decode(),response_truncated=False,response_byte_count=len(raw),
                response_sha256=hashlib.sha256(raw).hexdigest(),elapsed_s=40,cancelled=True)
            row=dict(attempt_id='fixture',model_id='fixture-model',max_tokens=10000,finished_at='fixture',
                usage=dict(completion_tokens=10000),charged_or_reserved_usd='.001')
            path.write_text(json.dumps(evidence))
            result=checked_raw(path,row,cap=10000)
            self.assertEqual(result['finish_reason'],'length')
            self.assertEqual(result['content_characters'],0)
            self.assertTrue(result['late_after_cancellation'])
            self.assertNotIn('success',result)
            for field,value in (('max_tokens',8000),('finished_at',None),('usage',dict(completion_tokens=1))):
                with self.assertRaises(ValueError):checked_raw(path,{**row,field:value},cap=10000)
            for field,value in (('max_tokens',8000),('response_truncated',True),('response_sha256','bad'),
                                ('response_byte_count',len(raw)+1)):
                path.write_text(json.dumps({**evidence,field:value}))
                with self.assertRaises(ValueError):checked_raw(path,row,cap=10000)


if __name__=='__main__':unittest.main()
