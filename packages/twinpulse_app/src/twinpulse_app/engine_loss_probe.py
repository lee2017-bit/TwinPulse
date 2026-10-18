# SPDX-License-Identifier: Apache-2.0
"""Confirm process loss, not sensor freshness or permission to move.

The backend publishes once per second. Two different stale publications are
required only when it explicitly proves no active/uncertain physical runtime.
Physical work or unknown proof keeps the original immediate cleanup policy.
"""
class EngineLossProbe:
    def __init__(self,clock):
        self.clock=clock;self.last_marker=None;self.last_content=None;self.advanced=clock()
        self.stale_since=None;self.stale_identity=None;self.stale_samples=0

    def observe(self,value):
        now=self.clock()
        if not isinstance(value,dict):return 'failed'
        sequence=value.get('status_sample_id')
        marker=sequence if type(sequence) is int and sequence>0 else value.get('sampled_at_utc')
        content=(value.get('engine_session_id'),value.get('engine_connected'),value.get('physical_runtime_active'))
        if self.last_marker is not None and (type(marker)!=type(self.last_marker) or marker<self.last_marker
                or marker==self.last_marker and content!=self.last_content):return 'failed'
        advanced=marker is not None and (self.last_marker is None or type(marker)==type(self.last_marker) and marker>self.last_marker)
        if advanced:self.last_marker=marker;self.last_content=content;self.advanced=now
        if now-self.advanced>=3.:return 'failed'
        if value.get('engine_connected') is True:
            self.stale_since=None;self.stale_identity=None;self.stale_samples=0
            return 'healthy'
        if not value.get('engine_session_id'):return 'failed'
        if value.get('physical_runtime_active') is not False:return 'failed'
        # Legacy/corrupt producers cannot qualify through repeated reads.
        if type(sequence) is not int or sequence<=0:return 'failed'
        if self.stale_since is None:self.stale_since=now
        identity=value['engine_session_id']
        if advanced:
            self.stale_samples=self.stale_samples+1 if identity==self.stale_identity else 1
            self.stale_identity=identity
        if self.stale_samples>=2 and now-self.stale_since>=1.:return 'failed'
        return 'failed' if now-self.stale_since>=3. else 'pending'
