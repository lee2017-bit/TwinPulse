# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local evidence summary, never dispatches inference or promotes fixtures.

Each selected run keeps its own denominator/source hash. Diagnostic probes and
old failures are historical, not discarded or combined into a final 24/24 claim.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core import SiteToolPlan,execute_site_tool_plan
from twinpulse_core.room_items import room_inventory
from tests.fixtures.historical_room_photo_inventory import photo_reference,inventory_coverage

EXPECTED={'T01':{'bed','wardrobe','desk','chair'},'T02':{'sofa','dining_table','storage'},
          'T03':{'bed','wardrobe','desk','chair'},'T04':{'bed','desk'}}


def summarize(root):
    campaign=json.loads((root/'campaign.json').read_text(encoding='utf-8'))
    report=dict(scope='live_campaign_local_evidence_only',whole_demo_ready=False,
        physical_validation='NOT_RUN',photo_dimension_accuracy='NOT_MEASURED',
        request_count=len(campaign['requests']),request_limit=campaign['max_requests'],
        estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in campaign['requests']),Decimal(0))),
        invoice_verified=False,unknown_attempts=[r['attempt_id'] for r in campaign['requests'] if r['status']=='outcome_unknown'],runs=[])
    # Only this campaign's bounded top-level outputs, no recursive user storage.
    for path in sorted(root.glob('*/result.json')):
        result=json.loads(path.read_text(encoding='utf-8'))
        rows=[]
        for job in result.get('jobs',[]):
            diagnostic=job.get('diagnostics',{})
            row=dict(case=job['case'],status=job['status'],elapsed_s=job.get('elapsed_s'),
                repair_count=diagnostic.get('repair_count'),evaluation_mode=job.get('evaluation_mode'),
                first_valid=job['status']=='VALIDATED' and diagnostic.get('repair_count')==0)
            plan_file=path.parent/(job['case']+'-plan.json')
            if plan_file.exists():
                plan=SiteToolPlan.from_dict(json.loads(plan_file.read_text(encoding='utf-8')))
                draft=execute_site_tool_plan(plan,source='manual',source_ref=hashlib.sha256(plan_file.read_bytes()).hexdigest())
                kinds={c.arguments.get('kind') for c in plan.calls if c.tool in ('place_furniture','place_room_item')}
                expected=EXPECTED.get(job['case'].split('-')[0])
                if expected:
                    row['missing_requested_kinds']=sorted(expected-kinds)
                    row['additional_kinds_for_review']=sorted(kinds-expected)
                    row['requested_coverage_pass']=not row['missing_requested_kinds']
                    row['major_relationships']='NOT_SCORED'
                reference=photo_reference(job.get('photo_sha256'))
                if reference:
                    coverage=inventory_coverage(reference,room_inventory(plan,draft.scene))
                    row['missing_required_photo_items']=coverage['missing_route_items']
                    row['route_inventory_complete']=coverage['route_inventory_complete']
                row['geometry_contract']='VALIDATED_NOT_PHYSICAL'
            rows.append(row)
        item=dict(run=path.parent.name,artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            status=result.get('status'),rows=rows,output_policy=result.get('output_policy'),
            source_sha256=result.get('source_sha256'))
        tested=[r for r in rows if r['status'] in ('FAIL','VALIDATED')]
        if tested:
            latency=[r['elapsed_s'] for r in tested if r['elapsed_s'] is not None]
            item.update(model_job_count=len(tested),first_valid_count=sum(r['first_valid'] for r in tested),
                final_valid_count=sum(r['status']=='VALIDATED' for r in tested))
            if latency:item['latency_s']=dict(mean=round(statistics.mean(latency),3),
                median=round(statistics.median(latency),3),maximum=max(latency))
        report['runs'].append(item)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    output=summarize(args.root)
    (args.root/'summary.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='runs'},indent=2))
