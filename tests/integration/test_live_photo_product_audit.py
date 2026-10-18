# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Product audit namespace/hash boundaries. No live calls or runtime launch."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from scripts.summarize_live_photo_product import checked_generation_progress


class LivePhotoProductAuditTests(unittest.TestCase):
    def records(self):
        saved=SimpleNamespace(request_id='provider-inner',plan_sha256='plan-hash')
        progress=dict(status='validated',repair_count=1,attempts=[dict(validation='passed',
            photo_quality=dict(plan_sha256='plan-hash',constraints_sha256='constraints-hash'))])
        report=dict(browser=dict(workflow=dict(site_draft=dict(request_id='provider-inner')),
            conversation=dict(generation=dict(request_id='chat-outer',progress=progress))))
        return saved,report,dict(constraints_sha256='constraints-hash')

    def test_chat_and_provider_request_ids_are_distinct_but_plan_binding_is_required(self):
        saved,report,quality=self.records()
        progress=checked_generation_progress(saved,report,quality)
        self.assertEqual(progress['repair_count'],1)
        before=deepcopy(report)
        checked_generation_progress(saved,report,quality)
        self.assertEqual(report,before)

    def test_mismatched_saved_provider_id_or_accepted_hash_rejected(self):
        for fault in ('provider_id','plan','constraints','status','validation','repair'):
            saved,report,quality=self.records()
            progress=report['browser']['conversation']['generation']['progress']
            if fault=='provider_id':report['browser']['workflow']['site_draft']['request_id']='foreign'
            elif fault in ('plan','constraints'):progress['attempts'][-1]['photo_quality'][fault+'_sha256']='foreign'
            elif fault=='status':progress['status']='failed'
            elif fault=='validation':progress['attempts'][-1]['validation']='failed'
            else:progress['repair_count']=True
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                checked_generation_progress(saved,report,quality)
