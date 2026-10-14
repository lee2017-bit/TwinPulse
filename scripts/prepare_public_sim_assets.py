# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Make an inspected public copy of existing ROBOTIS-derived USD layers.

Run with the installed Isaac Python (pxr). It opens no SimulationApp, hardware,
provider, or network. Originals stay unchanged. A new destination is required.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = re.compile(r'(?:[A-Za-z]:[\\/]+Users[\\/]+|/home/)', re.I)
Sdf = Usd = None


def strip_documentation(layer):
    def clean(path):
        spec = layer.GetObjectAtPath(path)
        if spec and 'documentation' in spec.ListInfoKeys():
            spec.ClearInfo('documentation')
    layer.Traverse(Sdf.Path.absoluteRootPath, clean)


def composed_scene_fingerprint(stage):
    # Flattened_Prototype_N numbering depends on layer identifiers and is not
    # stable across paths. Compare the same composed authored prim paths,
    # including instance proxies, attribute values and relationship targets.
    rows=[]
    for prim in Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()):
        attributes=[]
        for attribute in prim.GetAttributes():
            value=attribute.Get()
            if isinstance(value,Sdf.AssetPath):value=value.path
            attributes.append((attribute.GetName(),str(attribute.GetTypeName()),str(value),
                [(time,str(attribute.Get(time))) for time in attribute.GetTimeSamples()],
                sorted(str(path) for path in attribute.GetConnections())))
        relationships=[(r.GetName(),sorted(str(path) for path in r.GetTargets())) for r in prim.GetRelationships()]
        rows.append((str(prim.GetPath()),prim.GetTypeName(),prim.IsActive(),prim.IsInstanceable(),
            list(prim.GetAppliedSchemas()),sorted(attributes),sorted(relationships)))
    return sha256(json.dumps(sorted(rows),sort_keys=True).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--isaac-root',type=Path,default=Path(r'C:\isaacsim'))
    args=parser.parse_args()
    # Load only the installed static USD library; no Kit/SimulationApp startup.
    global Sdf, Usd
    libraries=list((args.isaac_root/'extscache').glob('omni.usd.libs-*.cp312'))
    if len(libraries)!=1:raise ValueError('SELECT_ONE_INSTALLED_USD_LIBRARY')
    dll_handles=[os.add_dll_directory(str(libraries[0]/'bin')),
                 os.add_dll_directory(str(args.isaac_root/'kit'))]
    sys.path.insert(0,str(libraries[0]))
    from pxr import Sdf as sdf, Usd as usd
    Sdf, Usd = sdf, usd
    output=args.output.resolve()
    if output.exists():raise ValueError('PUBLIC_ASSET_OUTPUT_ALREADY_EXISTS')
    source=ROOT/'artifacts/robot-models/burger-isaac/usd/turtlebot3_burger_1'
    files=sorted(p for p in source.rglob('*') if p.is_file())
    if len(files)!=9:raise ValueError('ORIGINAL_ASSET_CLOSURE_CHANGED')
    output.mkdir(parents=True)
    (output/'usd').mkdir()
    rows={};before={}
    for path in files:
        relative=path.relative_to(source).as_posix()
        before[relative]=sha256(path.read_bytes()).hexdigest()
        layer=Sdf.Layer.FindOrOpen(str(path))
        if layer is None:raise ValueError('ASSET_LAYER_OPEN_FAILED')
        original=Sdf.Layer.CreateAnonymous('original.usda');original.TransferContent(layer)
        strip_documentation(original)
        public=Sdf.Layer.CreateAnonymous('public.usda');public.TransferContent(layer)
        strip_documentation(public)
        # Documentation removal is the only USD content edit. Original creator,
        # mesh data, physics, materials, and relative reference paths stay intact.
        if original.ExportToString()!=public.ExportToString():
            raise ValueError('PUBLIC_ASSET_NON_DOCUMENTATION_EDIT')
        public.customLayerData={**public.customLayerData,
            'twinpulseModification':'TwinPulse 2026: removed exporter documentation with local paths; '
                'geometry, physics and relative references preserved. ROBOTIS origin and Apache-2.0 notice: ../SOURCE.json and ../ROBOTIS-LICENSE.'}
        if PRIVATE.search(public.ExportToString()):raise ValueError('PUBLIC_ASSET_PRIVATE_METADATA_REMAINS')
        destination=output/'usd'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        if not public.Export(str(destination)):raise ValueError('PUBLIC_ASSET_EXPORT_FAILED')
        rows[relative]=sha256(destination.read_bytes()).hexdigest()
    # No unknown external asset/texture closure can enter this copy.
    for path in (output/'usd').rglob('*'):
        if not path.is_file():continue
        layer=Sdf.Layer.FindOrOpen(str(path))
        for reference in layer.GetExternalReferences():
            target=(path.parent/reference).resolve()
            if not target.is_relative_to(output/'usd') or not target.is_file():
                raise ValueError('PUBLIC_ASSET_EXTERNAL_REFERENCE')
    for name,root in [('original',source),('public',output/'usd')]:
        stage=Usd.Stage.Open(str(root/'turtlebot3_burger.usda'))
        if stage is None:raise ValueError('PUBLIC_ASSET_STAGE_OPEN_FAILED')
        fingerprint=composed_scene_fingerprint(stage)
        if name=='original':original_fingerprint=fingerprint
        elif fingerprint!=original_fingerprint:raise ValueError('PUBLIC_ASSET_COMPOSED_SCENE_CHANGED')
    lineage=json.loads((ROOT/'artifacts/robot-models/burger-prepared/source.json').read_text())
    shutil.copy2(ROOT/'artifacts/robot-models/turtlebot3-source/LICENSE',output/'ROBOTIS-LICENSE')
    origin={'source':lineage['source'],'commit':lineage['commit'],'license':lineage['license'],
        'source_urdf_sha256':lineage['source_urdf_sha256'],'mesh_sha256':lineage['mesh_sha256'],
        'converter':'URDF USD Converter v0.1.3',
        'modification':'TwinPulse removed exporter documentation containing local absolute paths. Geometry, physics, materials and relative references are unchanged.',
        'composed_scene_comparison':'equal_after_documentation_removal',
        'composed_scene_sha256':original_fingerprint,
        'original_usd_sha256':before,'public_usd_sha256':rows,
        'scope':'ROBOTIS-derived geometry only; no Isaac/Kit runtime, importer binary, model weights, or asset packs'}
    (output/'SOURCE.json').write_text(json.dumps(origin,indent=2,sort_keys=True),encoding='utf-8')
    if any(sha256((source/name).read_bytes()).hexdigest()!=digest for name,digest in before.items()):
        raise ValueError('ORIGINAL_ASSET_CHANGED')
    print(json.dumps({'status':'inspected_copy','files':len(rows),'composed_scene_equal':True,
        'originals_unchanged':True,'public_manifest':rows}))


if __name__=='__main__':main()
