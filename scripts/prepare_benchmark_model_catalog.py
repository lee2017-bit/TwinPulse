# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Convert saved provider metadata to a frozen, credential-free model catalog.

This local preparation never checks current account availability or grants
money, sends images, starts Isaac, or changes ordinary global settings.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.benchmark_protocol import read_json,file_sha
from twinpulse_provider.model_contracts import catalog_from_inventory,catalog_sha,model_supported


def report(catalog):
    rows=[]
    for row in catalog['models']:
        roles={stage:('CATALOG_MODALITY_SUPPORTED_NOT_RUNTIME_VERIFIED' if model_supported(catalog,stage,row['model_id'])
            else 'INELIGIBLE_NOT_VISIBLE_OR_REQUIRED_MODALITY') for stage in ('observer','planner')}
        rows.append(dict(model_id=row['model_id'],roles=roles))
    return dict(schema_version='benchmark-model-catalog-report-1.0',catalog_sha256=catalog_sha(catalog),
        models=rows,account_availability='NOT_CHECKED_NO_NETWORK',strict_json_support='UNVERIFIED',
        independent_repair_critic='NOT_IMPLEMENTED_INHERITED_ROLES_ONLY',
        HTTP=0,inference=0,actual_run_authorized=False,physical_authority=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--valid-until',required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    paths=[args.inventory.resolve(),args.output.resolve(),args.report.resolve()]
    if len(set(paths))!=3:raise ValueError('BENCHMARK_CATALOG_OVERWRITE_FORBIDDEN')
    if any(p.exists() for p in paths[1:]):raise ValueError('BENCHMARK_CATALOG_OUTPUT_ALREADY_EXISTS')
    value=catalog_from_inventory(read_json(args.inventory),valid_until=args.valid_until)
    for path,content in ((args.output,value),(args.report,{**report(value),'catalog_file_sha256':None})):
        if path==args.report:content['catalog_file_sha256']=file_sha(args.output)
        with path.open('x',encoding='utf-8') as stream:json.dump(content,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(status='CATALOG_PREPARED_NOT_EXECUTED',models=len(value['models']),HTTP=0)))


if __name__=='__main__':main()
