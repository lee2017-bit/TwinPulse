# SPDX-License-Identifier: Apache-2.0
"""Read-only evidence audit. Derived receipts do not grant Apply or retry."""
import argparse,hashlib,json,os
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('project');parser.add_argument('output',type=Path);args=parser.parse_args()
root=Path(__file__).resolve().parents[1];runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
if not args.project.startswith('chat_') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in args.project):raise ValueError('PROJECT_ID')
source=runtime/'projects'/args.project/'environment-imports/photo-proposals'
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
rows=[]
for folder in source.iterdir():
    if not folder.is_dir():continue
    copies=[]
    for p in folder.rglob('*'):
        if not p.is_file():continue
        relative=p.relative_to(source)
        # Project-owned model job evidence only, never credentials/configuration.
        raw=p.read_bytes();target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        copies.append(dict(path=str(relative),bytes=len(raw),sha256=sha(raw)))
    job=read(folder/'job.json');usage=read(folder/'usage.ledger.json') if (folder/'usage.ledger.json').exists() else {'requests':[]}
    rows.append(dict(job_id=job['job_id'],status=job['status'],error=job['error'],response_sha256=job['response_sha256'],
        source_sha256=job['source_sha256'],photo_sha256=job['photo']['sha256'],requests=len(usage['requests']),copies=copies))
receipt=dict(scope='DERIVED_EVIDENCE_ONLY_NOT_MODEL_QUALITY_OR_ALIGNMENT',project_id=args.project,jobs=rows,total_requests=sum(r['requests'] for r in rows))
(out/'audit.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False))
