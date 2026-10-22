# SPDX-License-Identifier: Apache-2.0
"""Actual independent review transcription and original41 evidence binding."""
from hashlib import sha256
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def write(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def main():
    old=read(OUT/'build27/dist/TwinPulse/_internal/resources/source-manifest.json')
    new=read(OUT/'build28/dist/TwinPulse/_internal/resources/source-manifest.json')
    manifest=read(OUT/'build28/dist/TwinPulse/windows-release-manifest.json')
    changed=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    assert changed==['extensions/twinpulse.extension/twinpulse/extension/bridge_client.py','scripts/twinpulse_engine_host.py','scripts/twinpulse_live_viewport.py'],changed
    assert all(sha256((ROOT/name).read_bytes()).hexdigest()==new[name] for name in changed)
    files=changed+['tests/integration/test_bridge_robot_channel.py','tests/integration/test_live_viewport.py','scripts/verify_robot_focus_gate.py','tests/integration/test_robot_focus_gate.py']
    write(OUT/'viewport-source-review43.json',dict(schema='read-only-independent-source-review-1.0',
        status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
        recorded_by='Main transcription from actual final source/negative-test read-only review. Reviewer did not execute App/tests/system/device actions.',
        release_id=manifest['build_id'],source_manifest_sha256=manifest['source_manifest_sha256'],
        final_reviewed_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in files},exact_product_delta_from_frozen27=changed,unresolved=[],
        fixed=['Dedicated thread-owned viewport connection, separate from control, original2s and POST retry0.',
            'Typed/non-JSON rejection and successful response preserved despite independent sticky close error.',
            'Owner finally-close; sticky cleanup error is part of host handoff and independent gate.',
            'Previous exchange detail cleared before token/encoding; each iteration error/detail is tied only to its attempted POST.'],
        references=[ref(OUT/name) for name in ('viewport-channel-final43d.log','snapshot-source-review41.json','raycast-source-review37.json')],
        limits=['Original41 remains FAIL. Root OS/connect/send cause and original errno not retained.',
            'Connection churn removed, not proof of exact historic cause cured or no recurrence.',
            'New full installed acceptance and final evidence gate required. No deadline/authority/geometry/GC-policy change.',
            'Physical/Pi/storage/braking/world alignment NOT_RUN.']))
    ui=read(OUT/'ui-41/result.json');assert ui['status']=='FAIL'
    engine=read(OUT/'runtime-final41/25341174228a44649a151a37997a19fe/engine-result.json')
    worst=engine['viewport_phase_diagnostics']['worst_io'];assert worst['frame_id']==614 and worst['http_completed'] is False
    write(OUT/'viewport-failure41-review.json',dict(status='ORIGINAL_FAIL_PRESERVED_DISPLAY_HTTP_STALL_OS_CAUSE_UNKNOWN',
        project=ui['project'],launch_id=ui['desktop']['engine']['launch_id'],release_id=ui['desktop']['engine']['release_id'],
        failure_at_ms=1792598307331,displayed_frame=613,displayed_captured_at_ms=1792598306147.874,displayed_age_ms=1183.1259765625,
        failed_step=ui['steps'][-1],worst_same_window_frame=worst,
        interpretation=['Frame614 capture/JPEG/raw wait small; request/connect/send-associated URLError held display HTTP for2047ms.',
            'Actual Isaac urllib wraps request(connect/send) OSError; exact inner reason/errno was not retained.',
            'Concurrent ordinary browser GETs mostly6–15ms; backend total outage not established.',
            'Snapshot598events/197ms began at1792598307346.879, after failure; not its cause.',
            'HTTP409 drive is after failed-view check and harness Stop fence, not the original failure trigger.'],
        references=[ref(OUT/name) for name in ('ui-41/result.json','failed-ui41-original-logs/receipt.json',
            'failed-ui41-original-logs/00-backend.log','failed-ui41-original-logs/10-dcdd3c081af14cd5a4174d728d09165e.json',
            'runtime-final41/25341174228a44649a151a37997a19fe/engine-result.json','runtime-final41/receipt.json',
            'memory-final41/receipt.json','budget-final41.json')]))
    print(json.dumps(dict(status='SOURCE_REVIEW_RECORDED_NOT_UI_ACCEPTANCE',release_id=manifest['build_id'],source_sha256=manifest['source_manifest_sha256'])))
if __name__=='__main__':main()
