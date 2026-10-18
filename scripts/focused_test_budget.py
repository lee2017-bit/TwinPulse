"""Local evidence accounting only; never dispatches a provider request."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

def snapshot(runtime):
    rows={};files=[]
    for path in sorted((runtime/'ordinary-generation').glob('*.ledger.json')):
        raw=path.read_bytes();value=json.loads(raw)
        files.append(dict(name=path.name,sha256=sha256(raw).hexdigest()))
        for row in value.get('requests',[]):
            if row.get('attempt_id'):rows[row['attempt_id']]=row
    return dict(at_utc=datetime.now(timezone.utc).isoformat(),files=files,requests=rows)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--before',type=Path)
    parser.add_argument('--prior-total',type=Decimal,default=Decimal('.8546553'),help='Recorded cumulative additional-50 campaign total before this snapshot')
    args=parser.parse_args();runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime';value=snapshot(runtime)
    if args.before:
        before=json.loads(args.before.read_text(encoding='utf-8-sig'));new={k:r for k,r in value['requests'].items() if k not in before['requests']}
        rates={r['model_id']:r for r in json.loads((runtime/'stage_model_catalog.json').read_text(encoding='utf-8'))['models']}
        cost=Decimal(0);unknown=Decimal(0)
        for row in new.values():
            rate=rates[row['model_id']];usage=row.get('usage')
            if usage:cost+=(Decimal(str(rate['input_per_million']))*usage['prompt_tokens']+Decimal(str(rate['output_per_million']))*usage['completion_tokens'])/1000000
            else:unknown+=(Decimal(str(rate['input_per_million']))*rate['context_tokens']+Decimal(str(rate['output_per_million']))*row['max_tokens'])/1000000
        value.update(new_requests=new,new_http=len(new),new_estimated_usd=str(cost),new_unknown_usd=str(unknown),
            prior_additional_50_usd=str(args.prior_total),protected_additional_50_total=str(args.prior_total+cost+unknown),
            prior_20_campaign='14.9450973 including UNKNOWN .4770432, separate and unchanged',limit_usd='50',
            within_approved_total=args.prior_total+cost+unknown<=Decimal('50'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in value.items() if k not in ('requests','new_requests','files')},ensure_ascii=False))
if __name__=='__main__':main()
