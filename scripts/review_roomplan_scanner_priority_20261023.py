# SPDX-License-Identifier: Apache-2.0
"""Offline real-input review. No Kit, App, model call, devices or source edits."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\jaewo\OneDrive\문서\카카오톡 받은 파일\Project-2610222326.usd')
OUT = REPO / 'outputs/roomplan-scanner-review-20261023'
sys.dont_write_bytecode = True


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    usd = list(Path(r'C:\isaacsim\extscache').glob('omni.usd.libs-*.cp312'))
    if len(usd) != 1:
        raise ValueError('ONE_EXISTING_USD_RUNTIME_REQUIRED')
    handles = [os.add_dll_directory(str(usd[0] / 'bin')), os.add_dll_directory(r'C:\isaacsim\kit')]
    sys.path[:0] = [str(usd[0]), str(REPO / 'scripts'), str(REPO / 'packages/twinpulse_core/src')]
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade
    from twinpulse_environment_worker import inspect_environment
    from twinpulse_core.environment_source import checked_environment
    from twinpulse_core.environment_navigation import navigation_cells

    before = digest(SOURCE)
    layer = Sdf.Layer.FindOrOpen(str(SOURCE))
    stage = Usd.Stage.Open(layer, Usd.Stage.LoadNone)
    transforms = UsdGeom.XformCache()
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render', 'proxy'])
    prims = []
    faces = Counter()
    metadata_names = []
    for prim in stage.Traverse():
        row = dict(path=str(prim.GetPath()), type=prim.GetTypeName(),
                   properties=list(prim.GetPropertyNames()),
                   metadata_keys=sorted(prim.GetAllAuthoredMetadata()))
        if prim.IsA(UsdGeom.Xformable):
            row['world_transform'] = [list(r) for r in transforms.GetLocalToWorldTransform(prim)]
            row['local_transform'] = [list(r) for r in UsdGeom.Xformable(prim).GetLocalTransformation()]
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            faces.update(mesh.GetFaceVertexCountsAttr().Get())
            box = bounds.ComputeWorldBound(prim).ComputeAlignedRange()
            row['world_bounds_native'] = [list(box.GetMin()), list(box.GetMax())]
            material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            row['material'] = str(material.GetPath()) if material else None
        for name in row['properties'] + row['metadata_keys']:
            if any(token in name.lower() for token in ('confidence', 'dimensions', 'identifier', 'category')):
                metadata_names.append(dict(path=row['path'], name=name))
        prims.append(row)
    try:
        inspect_environment(SOURCE, None)
        unknown_units = 'UNEXPECTED_ACCEPTANCE'
    except ValueError as error:
        unknown_units = str(error)
    environment = checked_environment(inspect_environment(SOURCE, 'm'))
    expected_error = 0.
    for obj in environment['meshes']:
        prim = stage.GetPrimAtPath(obj['source_path'])
        matrix = transforms.GetLocalToWorldTransform(prim)
        raw = UsdGeom.Mesh(prim).GetPointsAttr().Get()
        for original, imported in zip(raw, obj['points_m']):
            x, y, z = matrix.Transform(Gf.Vec3d(*original))
            expected = [float(x), -float(z), float(y) + environment['floor_offset_m']]
            expected_error = max(expected_error, *(abs(a-b) for a, b in zip(imported, expected)))
    spec = importlib.util.spec_from_file_location('review_environment_geometry', REPO / 'extensions/twinpulse.extension/twinpulse/extension/environment_geometry.py')
    author = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(author)
    derived = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(derived, '/World/TwinPulse').GetPrim().SetCustomDataByKey('twinpulseSiteSceneRevision', 'offline-review-only')
    UsdGeom.Xform.Define(derived, author.ROOT)
    author.author_environment(derived, environment)
    matched = author.matches_environment(derived, environment)
    collision = []
    for obj in environment['meshes']:
        geom = derived.GetPrimAtPath(author.ROOT + '/' + obj['id'] + '/geometry')
        collision.append(dict(id=obj['id'], source_path=obj['source_path'],
                              approximation=geom.GetAttribute('physics:approximation').Get()))
    navigation = navigation_cells(environment['meshes'])
    free = {(round(x, 5), round(y, 5)) for x, y, state, *_ in navigation['cells'] if state == 'free'}
    remaining = set(free)
    components = []
    while remaining:
        pending = [remaining.pop()]
        size = 0
        while pending:
            x, y = pending.pop()
            size += 1
            for dx, dy in ((.1, 0), (-.1, 0), (0, .1), (0, -.1)):
                key = (round(x+dx, 5), round(y+dy, 5))
                if key in remaining:
                    remaining.remove(key)
                    pending.append(key)
        components.append(size)
    result = dict(schema='roomplan-scanner-priority-offline-review-1.0',
                  status='PASS_SCOPED_OFFLINE_GEOMETRY_NOT_PHYSX_OR_NATIVE_UI',
                  checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  source=dict(path=str(SOURCE), bytes=SOURCE.stat().st_size, sha256=before,
                              unchanged=before == digest(SOURCE)),
                  default_prim=str(stage.GetDefaultPrim().GetPath()), usd_version=list(Usd.GetVersion()),
                  stage_authored_up_axis=stage.HasAuthoredMetadata('upAxis'), up_axis=str(UsdGeom.GetStageUpAxis(stage)),
                  stage_authored_meters_per_unit=stage.HasAuthoredMetadata('metersPerUnit'),
                  fallback_meters_per_unit=UsdGeom.GetStageMetersPerUnit(stage),
                  face_vertex_histogram=dict(faces), external_references=list(layer.GetExternalReferences()),
                  external_assets=list(layer.GetExternalAssetDependencies()), sublayers=list(layer.subLayerPaths),
                  structured_metadata_name_matches=metadata_names,
                  missing_units_original_rejected=unknown_units,
                  selected_meters=dict(mesh_count=len(environment['meshes']), units_basis=environment['units_basis'],
                                       floor_offset_m=environment['floor_offset_m'],
                                       max_normalized_original_vertex_error_m=expected_error,
                                       current_author_matches=matched, collision_meshes=collision),
                  navigation=dict(resolution_m=.1, cell_count=len(navigation['cells']), free_cells=len(free),
                                  four_neighbor_components=sorted(components, reverse=True),
                                  bound=navigation['bounds'], target_count=len(navigation['targets'])),
                  prims=prims,
                  code_sha256={name:digest(REPO / name) for name in (
                      'scripts/twinpulse_environment_worker.py', 'scripts/twinpulse_library_worker.py',
                      'extensions/twinpulse.extension/twinpulse/extension/environment_geometry.py',
                      'packages/twinpulse_core/src/twinpulse_core/environment_navigation.py')},
                  limitations=[
                      'In-memory USD Stage/schema/geometry only: no independent Kit visual or PhysX contact simulation.',
                      'World-space geometry is normalized; original nested hierarchy, arbitrary shaders and RoomPlan API confidence are not promised lossless.',
                      '0.1 m free-cell connectivity is not footprint-inflated robot reachability or proof that all doors are traversable.',
                      'Dimensions reflect an explicitly selected SIM scale, not surveyed physical accuracy.',
                      'No new real App journey, model request, scan, hardware motion or upload. Existing installed evidence is reviewed separately.',
                  ])
    assert before == digest(SOURCE) and matched and expected_error < 1e-9
    assert unknown_units == 'ENVIRONMENT_SELECT_UNITS'
    with (OUT / 'source-geometry-review.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k:result[k] for k in ('status', 'default_prim', 'stage_authored_meters_per_unit',
          'structured_metadata_name_matches', 'missing_units_original_rejected', 'navigation')}))
    print(json.dumps(dict(mesh_count=len(environment['meshes']), max_vertex_error_m=expected_error,
                          author_matches=matched, original_source_unchanged=result['source']['unchanged'])))


if __name__ == '__main__':
    main()
