# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary acceptance-purpose checks, not fresh model/photo evidence."""
import asyncio
from dataclasses import replace
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace

from test_render_review_loop import case,pending_case,provider,DynamicFixtureTransport,review_response
from test_budgeted_generation import config
from twinpulse_provider import GenerationService
from twinpulse_core.draft_refinement import checked_refinement


class EditableObstaclePriorTests(unittest.TestCase):
    def test_finite_room_summary_policy_is_flash_specific(self):
        from twinpulse_provider.render_review import finite_flash_options
        self.assertEqual(finite_flash_options('deepseek-ai/DeepSeek-V4.1-Flash'),{'reasoning_effort':'none'})
        self.assertEqual(finite_flash_options('nvidia/nemotron-3-super-120b-a12b'),{})
        self.assertEqual(finite_flash_options('other-observer'),{})

    def test_old_truncation_and_cancel_cannot_silently_change_wire_policy(self):
        from twinpulse_core import canonical_sha256
        from twinpulse_provider.generation_store import GenerationStore,input_digest
        from twinpulse_provider.errors import ProviderConfigurationError
        for stop in ('PROVIDER_OUTPUT_TRUNCATED','GENERATION_CANCELLED'):
            for old_hash in (None,'0'*64):
                with self.subTest(stop=stop,old_hash=old_hash),TemporaryDirectory() as folder:
                    request,*_=case();transport=DynamicFixtureTransport([])
                    pipeline=provider(transport);pipeline.store=GenerationStore(Path(folder))
                    parent=dict(request_id='old-request',approval_id='old-approval',input_sha256=input_digest(request),
                        harness_bindings=pipeline.harness_bindings,budget={'stop_reason':stop})
                    if old_hash is not None:parent['stage_route_sha256']=old_hash
                    pipeline.store.save('checkpoint','a'*64,parent)
                    scope=SimpleNamespace(approved_render_review=True,approval_id='new-approval',
                        approved_checkpoint_sha256=canonical_sha256(parent))
                    request=replace(request,inference_scope=scope,continuation_checkpoint='a'*64)
                    with self.assertRaisesRegex(ProviderConfigurationError,'CONTINUATION_STAGE_ROUTE_CHANGED'):
                        asyncio.run(GenerationService(pipeline,config(timeout_s=300),plan_version='2.2').generate(request))
                    self.assertEqual(transport.bodies,[])

    def test_current_geometry_with_photo_conflict_is_saved_without_visual_repair(self):
        request,port,observation,structure,objects,_=case()
        request=replace(request,draft_goal='editable_obstacle_prior')
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,
            lambda body:review_response(body,contradiction=True)])
        result=asyncio.run(GenerationService(provider(transport),config(timeout_s=300),plan_version='2.2').generate(request))
        provenance=result.provider_provenance;record=provenance['draft_refinement']
        self.assertEqual(len(transport.bodies),4)
        self.assertEqual(record['stop_reason'],'EDITABLE_PRIOR_READY')
        self.assertEqual(provenance['quality_review']['status'],'needs_revision')
        self.assertTrue(record['geometry_checks']['checks_complete'])
        self.assertFalse(record['physical_authority'])
        checked_refinement(record,result.plan.to_dict(),request_id=request.request_id,progressive=provenance['progressive_twin'])

    def test_pending_support_is_preserved_without_exhausting_repairs(self):
        request,port,observation,structure,objects,_=pending_case()
        request=replace(request,draft_goal='editable_obstacle_prior')
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects])
        result=asyncio.run(GenerationService(provider(transport),config(timeout_s=300),plan_version='2.2').generate(request))
        provenance=result.provider_provenance;record=provenance['draft_refinement']
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(record['stop_reason'],'EDITABLE_PRIOR_READY')
        self.assertTrue(provenance['progressive_twin']['unresolved'])
        self.assertFalse(record['geometry_checks']['checks_complete'])
        self.assertFalse(provenance['physical_authority'])
        self.assertEqual(provenance['budget']['repairs'],0)


if __name__=='__main__':unittest.main()
