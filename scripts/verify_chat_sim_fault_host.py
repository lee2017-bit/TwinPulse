# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fixed, opt-in isolated test host. Never selected by the product launcher."""
import runpy
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
frame_fault = '--inject-first-frame-loss' in sys.argv
pose_fault = '--inject-sim-fault' in sys.argv
apply_fault = '--inject-build-apply-fault' in sys.argv
if sum((frame_fault, pose_fault, apply_fault)) != 1:
    raise SystemExit('Exactly one explicit isolated fault mode is required')
sys.argv.remove('--inject-build-apply-fault' if apply_fault else '--inject-first-frame-loss' if frame_fault else '--inject-sim-fault')
cleanup_fault = '--inject-sim-cleanup-fault' in sys.argv
if cleanup_fault:
    if not pose_fault:raise SystemExit('Cleanup fault requires pose fault')
    sys.argv.remove('--inject-sim-cleanup-fault')
sys.path.insert(0,str(ROOT/'extensions/twinpulse.extension'))
host=runpy.run_path(str(ROOT/'scripts/twinpulse_engine_host.py'),run_name='owned_fault_contract')
if not host['_start_simulation_app']():raise SystemExit(1)
from twinpulse.extension.runtime import TwinPulseRuntime
from unittest.mock import patch

original_step=TwinPulseRuntime._site_physics_step
def pose_fault_once(self):
    if self.site_plan is not None and self.state=='running' and self._physics_steps>80 and not getattr(self,'_contract_fault_injected',False):
        self._contract_fault_injected=True
        with patch.object(self,'robot_pose_3d',side_effect=RuntimeError('SIM_TEST_POSE_LOST')):
            if cleanup_fault:
                with patch.object(self,'_site_zero',side_effect=RuntimeError('SIM_TEST_CLEANUP_FAILED')):
                    return original_step(self)
            return original_step(self)
    return original_step(self)
if apply_fault:
    # Known exception at the actual adapter/runtime apply boundary, before
    # mutation. This does not claim mid-USD rollback coverage.
    def fail_site_apply(self,*args,**kwargs):
        raise RuntimeError('SIM_TEST_APPLY_FAILED')
    TwinPulseRuntime.build_site_scene=fail_site_apply
elif pose_fault:
    TwinPulseRuntime._site_physics_step=pose_fault_once
else:
    from twinpulse_live_viewport import LiveViewportPublisher
    original_init=LiveViewportPublisher.__init__
    def suppress_current_frame_delivery(self,bridge):
        original_init(self,bridge)
        original_post=bridge._post
        def post_without_frame(path,payload):
            # Actual GPU scheduling, capture and JPEG encoding remain intact.
            # Only the isolated publisher's frame delivery is suppressed; this
            # is NOT a claimed GPU/capture or real network failure.
            if path=='/v1/engine/viewport':payload={**payload,'frame':None}
            return original_post(path,payload)
        bridge._post=post_without_frame
    LiveViewportPublisher.__init__=suppress_current_frame_delivery
raise SystemExit(host['main']())
