# SPDX-License-Identifier: Apache-2.0
"""Offline read-only catalog measurement, not an installed App acceptance."""
import argparse
import cProfile
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import pstats
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.project_catalog import ProjectCatalog

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(exist_ok=False)
    root=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
    catalog=ProjectCatalog(root,'default');rows=[]
    for label in ('cold','warm'):
        profile=cProfile.Profile();wall=time.perf_counter();cpu=time.process_time()
        value=profile.runcall(catalog.snapshot)
        row=dict(label=label,wall_s=time.perf_counter()-wall,cpu_s=time.process_time()-cpu,
                 response_sha256=sha256(json.dumps(value,sort_keys=True).encode()).hexdigest(),rows=len(value['projects']))
        sink=io.StringIO();pstats.Stats(profile,stream=sink).sort_stats('cumulative').print_stats(35)
        (out/(label+'.profile.txt')).write_text(sink.getvalue(),encoding='utf-8')
        (out/(label+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8');rows.append(row)
    result=dict(classification='OFFLINE_CURRENT_SOURCES_READ_ONLY_NOT_INSTALLED_HTTP_OR_LOAD_REPRODUCTION',
                catalog_sha256=sha256((ROOT/'packages/twinpulse_app/src/twinpulse_app/project_catalog.py').read_bytes()).hexdigest(),rows=rows)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
