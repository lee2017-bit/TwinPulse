# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Save existing local runtime/asset fingerprints only; never start Isaac."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))
from scripts.benchmark_environment import capture, identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if any(path.is_symlink() for path in (args.output, *args.output.parents)):
        raise ValueError('BENCHMARK_LINKED_OUTPUT')
    value = capture(ROOT)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(status='FINGERPRINTED_NOT_RUNTIME_TESTED',
        environment_sha256=identity(value), runtime_files=len(value['runtime_files']),
        asset_files=len(value['assets']), HTTP=0, credential_reads=0,
        actual_isaac_readiness='NOT_RUN', full_install_dependency_closure='NOT_FROZEN')))


if __name__ == '__main__':
    main()
