# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Prepare a frozen comparison schedule without starting services or inference."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
for package in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'packages'/package/'src'))
from scripts.benchmark_protocol import prepare


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args();value=prepare(args.manifest)
    if args.output.resolve()==args.manifest.resolve():raise ValueError('SOURCE_MANIFEST_OVERWRITE_FORBIDDEN')
    # Exclusive create: never overwrite an approved schedule or old failure.
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',jobs=len(value['jobs']),HTTP=0,
        actual_run_authorized=False)))


if __name__=='__main__':main()
