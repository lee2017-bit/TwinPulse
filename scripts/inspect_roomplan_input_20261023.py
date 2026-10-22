# SPDX-License-Identifier: Apache-2.0
"""Read-only RoomPlan/USD evidence inspection; no Kit, App, network or import.

Uses the already installed Isaac static USD library and existing Pillow. Raw
input remains byte-identical. Projections are analysis pictures, not Isaac
renders, metric calibration or physics/navigation acceptance.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys


def inspect(source, output, isaac_root):
    source = source.resolve(strict=True)
    if output.exists():
        raise ValueError('NEW_OUTPUT_DIRECTORY_REQUIRED')
    before = sha256(source.read_bytes()).hexdigest()
    libraries = list((isaac_root / 'extscache').glob('omni.usd.libs-*.cp312'))
    if len(libraries) != 1:
        raise ValueError('ONE_EXISTING_CP312_USD_LIBRARY_REQUIRED')
    handles = [os.add_dll_directory(str(libraries[0] / 'bin')),
               os.add_dll_directory(str(isaac_root / 'kit'))]
    sys.path.insert(0, str(libraries[0]))
    from pxr import Gf, Sdf, Usd, UsdGeom
    from PIL import Image, ImageDraw

    layer = Sdf.Layer.FindOrOpen(str(source))
    if layer is None:
        raise ValueError('USD_LAYER_OPEN_FAILED')
    references = list(layer.GetExternalReferences())
    assets = list(layer.GetExternalAssetDependencies())
    if references or assets or layer.subLayerPaths:
        raise ValueError('EXTERNAL_DEPENDENCIES_REQUIRE_SEPARATE_REVIEW')
    stage = Usd.Stage.Open(layer, Usd.Stage.LoadNone)
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy]
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes)
    world = bounds.ComputeWorldBound(stage.GetDefaultPrim()).ComputeAlignedRange()
    objects, polygons = [], []
    physics = []
    types = Counter()
    for prim in stage.Traverse():
        types[prim.GetTypeName()] += 1
        physics_names = [a.GetName() for a in prim.GetAttributes()
                         if a.GetName().startswith(('physics:', 'physx'))]
        physics_schemas = [str(s) for s in prim.GetAppliedSchemas()
                           if 'Physics' in str(s) or 'Physx' in str(s)]
        if physics_names or physics_schemas:
            physics.append(dict(path=str(prim.GetPath()), attributes=physics_names,
                                schemas=physics_schemas))
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        transform = cache.GetLocalToWorldTransform(prim)
        points = [transform.Transform(Gf.Vec3d(p)) for p in mesh.GetPointsAttr().Get()]
        if not all(math.isfinite(float(v)) for point in points for v in point):
            raise ValueError('NONFINITE_MESH')
        counts = list(mesh.GetFaceVertexCountsAttr().Get())
        indices = list(mesh.GetFaceVertexIndicesAttr().Get())
        if sum(counts) != len(indices) or any(i < 0 or i >= len(points) for i in indices):
            raise ValueError('INVALID_MESH_TOPOLOGY')
        holes = set(mesh.GetHoleIndicesAttr().Get() or [])
        box = bounds.ComputeWorldBound(prim).ComputeAlignedRange()
        name = prim.GetName()
        category = ''.join(c for c in name if not c.isdigit())
        row = dict(name=name, category=category, path=str(prim.GetPath()),
                   vertices=len(points), faces=len(counts), hole_faces=sorted(holes),
                   world_min_native=list(box.GetMin()), world_max_native=list(box.GetMax()),
                   world_aabb_size_native=list(box.GetSize()),
                   properties=[str(p) for p in prim.GetPropertyNames()],
                   applied_schemas=list(prim.GetAppliedSchemas()))
        objects.append(row)
        offset = 0
        for face_index, count in enumerate(counts):
            face = [list(points[i]) for i in indices[offset:offset + count]]
            offset += count
            if face_index not in holes:
                polygons.append((category, name, face))

    output.mkdir(parents=True)
    authored_unit = layer.pseudoRoot.HasInfo('metersPerUnit')
    floor = next((o for o in objects if o['category'] == 'Floor'), None)
    walls = [o for o in objects if o['category'] == 'Wall']
    native_wall_height = max(o['world_aabb_size_native'][1] for o in walls) if walls else None
    result = dict(
        schema='roomplan-static-inspection-1.0', status='INSPECTED_NOT_IMPORTED_OR_CALIBRATED',
        checked_at_utc=datetime.now(timezone.utc).isoformat(),
        source=dict(name=source.name, bytes=source.stat().st_size, sha256=before,
                    header=source.read_bytes()[:8].decode('ascii', errors='replace')),
        usd_version=list(Usd.GetVersion()), creator=layer.customLayerData.get('creator'),
        default_prim=str(stage.GetDefaultPrim().GetPath()), up_axis=str(UsdGeom.GetStageUpAxis(stage)),
        meters_per_unit_authored=authored_unit,
        resolved_meters_per_unit=float(UsdGeom.GetStageMetersPerUnit(stage)),
        units_verdict='AUTHORED_NOT_INDEPENDENTLY_CALIBRATED' if authored_unit else 'MISSING_AUTHORED_UNITS_DO_NOT_AUTOCALIBRATE',
        world_min_native=list(world.GetMin()), world_max_native=list(world.GetMax()),
        world_aabb_size_native=list(world.GetSize()),
        wall_height_native=native_wall_height,
        wall_height_if_fallback_centimeters_m=native_wall_height * .01 if native_wall_height else None,
        wall_height_if_confirmed_meters_m=native_wall_height,
        external_references=references, external_assets=assets, sublayers=list(layer.subLayerPaths),
        prim_types=dict(types), mesh_categories=dict(Counter(o['category'] for o in objects)),
        mesh_vertices=sum(o['vertices'] for o in objects), mesh_faces=sum(o['faces'] for o in objects),
        authored_physics=physics, floor=floor, meshes=objects,
        limits=[
            'Reported same-site relationship is user supplied, not independent spatial registration.',
            'Native units and Y-up are preserved. Meters is plausible from dimensions but not authored or measured.',
            'Bounds are axis-aligned composed bounds, not room dimensions or surveyed floor area.',
            'No collision, navigation, App import, Undo, save/reopen, renderer or robot acceptance is implied.',
            'These are actual-mesh analysis projections; no photo camera pose or hidden geometry is inferred.',
        ])
    palette = dict(Floor='#e6edf2', Wall='#5c6c7a', Window='#3ba6cc', Door='#a87942',
                   Sofa='#dbaa67', Table='#73b6a8', Chair='#77a964', Refrigerator='#999cb7', Storage='#c796be')
    for mode in ('top', 'oblique'):
        def projection(p):
            x, y, z = p
            return (x, z) if mode == 'top' else (x - .62 * z, .34 * x + .43 * z - y)
        projected = [projection(p) for _, _, face in polygons for p in face]
        mn = [min(p[i] for p in projected) for i in (0, 1)]
        mx = [max(p[i] for p in projected) for i in (0, 1)]
        scale = min(1020 / max(mx[0] - mn[0], .001), 820 / max(mx[1] - mn[1], .001))
        def screen(p):
            q = projection(p)
            return (80 + (q[0] - mn[0]) * scale, 110 + (q[1] - mn[1]) * scale)
        image = Image.new('RGB', (1200, 1050), 'white')
        draw = ImageDraw.Draw(image)
        draw.text((30, 24), f'RoomPlan original USD - {mode} actual-mesh projection', fill='#173241')
        draw.text((30, 47), 'Y-up. Native units; metersPerUnit NOT authored. NOT Isaac/collision acceptance.', fill='#924b14')
        ordered = sorted(polygons, key=lambda row: (row[0] != 'Floor',
                         sum(p[1] for p in row[2]) / len(row[2])))
        for category, name, face in ordered:
            draw.polygon([screen(p) for p in face], fill=palette.get(category, '#ccd7da'), outline='#53616c')
        for obj in objects:
            if obj['category'] not in ('Wall', 'Window', 'Door', 'Floor'):
                center = [(a + b) / 2 for a, b in zip(obj['world_min_native'], obj['world_max_native'])]
                pt = screen(center)
                draw.text(pt, obj['name'], fill='#111111', stroke_width=2, stroke_fill='white')
        draw.text((30, 1008), 'Local private analysis: no scan/photo uploaded; no axis/scale/source mutation.', fill='#274653')
        path = output / f'roomplan-{mode}.png'
        image.save(path)
    after = sha256(source.read_bytes()).hexdigest()
    result['source_unchanged'] = before == after
    if not result['source_unchanged']:
        raise ValueError('SOURCE_CHANGED')
    (output / 'usd-inspection.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'source', 'up_axis', 'meters_per_unit_authored',
                     'resolved_meters_per_unit', 'world_aabb_size_native', 'wall_height_native',
                     'prim_types', 'mesh_categories', 'mesh_vertices', 'mesh_faces', 'source_unchanged')}))
    print(json.dumps(dict(authored_physics_count=len(physics), output=str(output))))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--isaac-root', type=Path, default=Path(r'C:\isaacsim'))
    args = parser.parse_args()
    inspect(args.input, args.output, args.isaac_root)
