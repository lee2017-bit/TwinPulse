# SPDX-License-Identifier: Apache-2.0
"""Offline source-contract probe, not App import or calibrated scene evidence."""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('NEW_RECEIPT_REQUIRED')
    before = sha256(args.input.read_bytes()).hexdigest()
    isaac = Path(r'C:\isaacsim')
    library = list((isaac / 'extscache').glob('omni.usd.libs-*.cp312'))
    if len(library) != 1:
        raise ValueError('EXISTING_USD_NOT_UNIQUE')
    handles = [os.add_dll_directory(str(library[0] / 'bin')), os.add_dll_directory(str(isaac / 'kit'))]
    sys.path.insert(0, str(library[0]))
    spec = importlib.util.spec_from_file_location('tp_roomplan_source_probe', ROOT / 'scripts/twinpulse_library_worker.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    try:
        worker.inspect_usd(args.input)
        verdict = dict(status='ACCEPTED_BY_SOURCE_INSPECTOR_NOT_APP_ACCEPTANCE')
    except ValueError as error:
        verdict = dict(status='EXPECTED_TYPED_REJECTION', reason=str(error))
    from pxr import Sdf, Usd, UsdGeom
    layer = Sdf.Layer.FindOrOpen(str(args.input))
    stage = Usd.Stage.Open(layer, Usd.Stage.LoadNone)
    from collections import Counter
    counts = Counter()
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            counts.update(UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get())
    result = dict(schema='source-only-library-contract-probe-1.0', original_input=verdict,
                  source_sha256=before, source_unchanged=before == sha256(args.input.read_bytes()).hexdigest(),
                  inspector_source_sha256=sha256((ROOT / 'scripts/twinpulse_library_worker.py').read_bytes()).hexdigest(),
                  face_vertex_count_histogram=dict(counts),
                  limits=['No App or installed worker path invoked; source function only.',
                          'No unit value invented, source edits, conversion or physics acceptance.'])
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
