# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned, bounded idle preview Build/capture using the existing engine broker.

Internal generation port only. No HTTP/model-supplied commands, Run, saved-scene
editing or physical authority. A receipt and a fresh coherent JPEG are required.
"""
import asyncio
import time
from uuid import uuid4

from twinpulse_core import SiteToolPlan, execute_site_tool_plan, canonical_sha256
from twinpulse_provider.errors import ProviderConfigurationError, GenerationCancelledError
from .command_broker import BrokerError


class GenerationRenderPort:
    supports_incremental_preview = True
    def __init__(self, broker, viewport, owner, input_revision, *, current):
        self.broker, self.viewport = broker, viewport
        self.owner, self.input_revision, self.current = owner, input_revision, current
        self.engine_identity = None

    def preflight(self):
        state = self.broker.public_state(self.owner)
        snapshot = state.get('snapshot') or {}
        if (not self.owner or not self.current() or not state['engine_connected']
                or snapshot.get('runtime_state') == 'running' or snapshot.get('safety_state')
                or self.broker.has_pending_operations()):
            raise ProviderConfigurationError('RENDER_PREVIEW_ENGINE_NOT_READY')
        feature = state.get('engine_readiness', {}).get('site_scene_build_v2') or {}
        if 'generation_room_visual_v1' not in snapshot.get('capabilities', ()):
            raise ProviderConfigurationError('RENDER_PREVIEW_VISUAL_CAPABILITY_MISSING')
        # Broker performs the authoritative feature gate again on submission.
        if feature.get('ready') is False and feature.get('code') != 'runtime_command_unavailable':
            raise ProviderConfigurationError('RENDER_PREVIEW_'+str(feature.get('code') or 'capability_missing').upper())
        self.engine_identity = (state['engine_session_id'], state['stage_epoch'])

    def assert_current(self, metadata):
        state = self.broker.supervisor_state()
        snapshot = state.get('snapshot') or {}
        if (not self.current() or not state['engine_connected']
                or (state['engine_session_id'], state['stage_epoch']) != self.engine_identity
                or metadata['applied_revision'] != snapshot.get('applied_revision')
                or snapshot.get('runtime_state') == 'running' or snapshot.get('safety_state')
                or self.broker.has_pending_operations()):
            raise ProviderConfigurationError('RENDER_REVIEW_SUPERSEDED')

    async def capture(self, plan, candidate_revision, token, timeout_s):
        if token.is_cancelled or not self.current():
            raise GenerationCancelledError('Render preview cancelled')
        state = self.broker.supervisor_state()
        if (not state['engine_connected'] or
                (state['engine_session_id'], state['stage_epoch']) != self.engine_identity):
            raise ProviderConfigurationError('RENDER_PREVIEW_ENGINE_CHANGED')
        checked = SiteToolPlan.from_dict(plan)
        source = ('drawing' if self.input_revision.input_kind == 'drawing' else
                  'photo' if self.input_revision.images else 'manual')
        scene = execute_site_tool_plan(checked, source=source, source_ref=self.input_revision.digest).scene
        artifact_id, request_id = 'generation-preview:'+uuid4().hex, 'generation-preview:'+uuid4().hex
        operation = None
        receipt_frame_floor = None
        receipt_observed_ms = None
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time()+min(120, timeout_s)
            lease = self.broker.acquire_lease(self.owner)
            # An idle adapter advertises Build only after it observes the owned
            # lease on the next bridge exchange. Capability != momentary permission.
            # Do not submit early or bypass the broker's authoritative gate.
            while not self.broker.site_scene_capable():
                if token.is_cancelled or not self.current():
                    raise GenerationCancelledError('Render preview cancelled')
                fresh=self.broker.supervisor_state()
                if (not fresh['engine_connected'] or
                        (fresh['engine_session_id'],fresh['stage_epoch'])!=self.engine_identity):
                    raise ProviderConfigurationError('RENDER_PREVIEW_ENGINE_CHANGED')
                if loop.time()>=deadline:
                    raise ProviderConfigurationError('RENDER_PREVIEW_COMMAND_PERMISSION_TIMEOUT')
                self.broker.renew_lease(self.owner,lease['control_lease_id'])
                await asyncio.sleep(.1)
            from twinpulse_core.generation_visual import generation_visual
            self.broker.register_site_scene(artifact_id, scene,
                visual_preview=generation_visual(checked, scene, self.broker.project_id))
            operation = self.broker.submit(self.owner, {'client_request_id': request_id,
                'command_type': 'build_site_scene', 'artifact_id': artifact_id,
                'expected_applied_revision': scene.revision})
            while loop.time() < deadline:
                if token.is_cancelled or not self.current():
                    raise GenerationCancelledError('Render preview cancelled')
                self.broker.renew_lease(self.owner, lease['control_lease_id'])
                result = self.broker.request_outcome(self.owner, request_id)
                if result['status'] not in ('accepted', 'claimed', 'running', 'succeeded'):
                    raise ProviderConfigurationError('RENDER_PREVIEW_BUILD_'+result['status'].upper()+': '+
                        str((result.get('receipt') or {}).get('error_code') or 'receipt_failed'))
                if result['status'] == 'succeeded':
                    receipt = result.get('receipt') or {}
                    status, jpeg = self.viewport.image_packet()
                    frame = status.get('frame')
                    if receipt_frame_floor is None:
                        # Same collision revision can still mean new catalog
                        # appearance. Never bind a pre-Build JPEG to a new plan.
                        receipt_frame_floor = frame['frame_id'] if frame else -1
                        receipt_observed_ms = time.time()*1000
                        await asyncio.sleep(.1)
                        continue
                    view = self.broker.public_state(self.owner).get('build_view') or {}
                    if (receipt.get('applied_revision') == scene.revision and jpeg and frame
                            and frame['frame_id'] > receipt_frame_floor
                            and frame['captured_at_ms'] >= receipt_observed_ms
                            and view.get('command_id') == result['command_id'] and view.get('status') == 'succeeded'
                            and frame['applied_revision'] == scene.revision
                            and (frame['engine_session_id'], frame['stage_epoch']) == self.engine_identity
                            and not status.get('camera_pending')):
                        metadata = {k:v for k,v in frame.items() if k != 'url'}
                        metadata.update(command_id=result['command_id'], scene_revision=scene.revision,
                            candidate_revision=candidate_revision, plan_sha256=canonical_sha256(plan),
                            project_id=self.broker.project_id, preview_only=True, Run='NOT_RUN', physical_authority=False)
                        self.assert_current(metadata)
                        return {'metadata': metadata, 'jpeg': jpeg}
                await asyncio.sleep(.1)
            raise ProviderConfigurationError('RENDER_PREVIEW_RECEIPT_OR_FRAME_TIMEOUT')
        except BrokerError as error:
            raise ProviderConfigurationError('RENDER_PREVIEW_'+error.code.upper()) from error
        finally:
            if operation is not None:
                try:
                    result = self.broker.request_outcome(self.owner, request_id)
                    if not result.get('receipt'):
                        self.broker.cancel(self.owner, result['command_id'])
                except BrokerError as cleanup_error:
                    # Running Build cannot be interrupted. Retain that fact,
                    # but never mask the primary cancellation/timeout cause.
                    if token.diagnostics:
                        token.diagnostics.child('render_preview_cleanup').finish('failed', error_code=cleanup_error.code)
