# SPDX-License-Identifier: Apache-2.0
"""Supplementary pure-data timing. Not an Isaac UI/hardware result."""
import argparse,gc,hashlib,json,time
from dataclasses import asdict
from pathlib import Path
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_core import canonical_sha256
p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--output',required=True);p.add_argument('--mode',choices=['legacy','objects'],required=True)
args=p.parse_args();raw=json.loads(Path(args.project).read_text(encoding='utf-8'))
scene=SiteDraftRecord.from_dict(raw['site_draft']).site.scene
expected=canonical_sha256(scene.to_dict()['objects'])
before=gc.get_stats();began=time.perf_counter();cpu=time.process_time()
for _ in range(200):
    actual=canonical_sha256(scene.to_dict()['objects'] if args.mode=='legacy' else [asdict(item) for item in scene.objects])
    if actual!=expected:raise ValueError('OBJECT_DIGEST_CHANGED')
result=dict(mode=args.mode,count=200,wall_s=time.perf_counter()-began,cpu_s=time.process_time()-cpu,
    object_digest=actual,source_sha256=scene.environment['source_sha256'],
    gc_collections=[a['collections']-b['collections'] for a,b in zip(gc.get_stats(),before)],
    qualification='SUPPLEMENTARY_SEPARATE_PROCESS_NOT_KIT',gc_policy_changed=False)
with Path(args.output).open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
print(json.dumps(result))
