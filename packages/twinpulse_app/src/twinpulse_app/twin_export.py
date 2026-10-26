# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Export a generated (photo/text) Twin as a self-contained USDA so it can be imported as a robot workspace.

Generated scenes are approximate box objects (floor, walls, rack posts and shelves, pallets, boxes). The
declared-route loop (survey, LiDAR candidates, Twin edits with Undo) runs on *imported* environments, which
carry a navigation grid and the overlay edit layer; a generated project cannot be converted in place because
an existing scene is never overwritten. This exporter writes the same boxes as triangle meshes whose prim
names carry the import categories the inspection worker understands (``floor``, ``wall<n>``, ``storage<n>``
for racks, ``unknown<n>`` for the rest), so New chat → Import space reproduces the factory as an imported Twin.
Dimensions stay the generator's estimates; nothing here is measured.
"""
import math

EXPORT_SCHEMA='twinpulse-generated-twin-usda-1.0'
_SKIP_KINDS={'robot','agv','vehicle'}
_CATEGORY_BY_KIND={'floor':'floor','wall':'wall','rack':'storage'}
_COLOR_BY_KIND={'floor':(.72,.72,.70),'wall':(.86,.87,.88),'rack':(.16,.44,.72),'box':(.76,.58,.36),'equipment':(.55,.42,.28)}


def _box_vertices(position,dimensions,yaw_deg):
    x,y,z=position;w,d,h=dimensions;yaw=math.radians(yaw_deg);c,s=math.cos(yaw),math.sin(yaw)
    out=[]
    for sz in (-1,1):
        for sy in (-1,1):
            for sx in (-1,1):
                lx,ly,lz=sx*w/2,sy*d/2,sz*h/2
                out.append((x+c*lx-s*ly,y+s*lx+c*ly,z+lz))
    return out


# Outward-facing triangles of the unit box above (index order: x fastest, then y, then z).
_TRIANGLES=((0,2,1),(1,2,3),(4,5,6),(5,7,6),(0,1,4),(1,5,4),(2,6,3),(3,6,7),(0,4,2),(2,4,6),(1,3,5),(3,7,5))


def generated_twin_usda(objects,*,scene_id='generated_twin'):
    """USDA text (metres, Z up) for the box objects of a generated scene; raises ValueError without a floor."""
    counters={};prims=[];floor_seen=False
    for obj in objects:
        kind=str(getattr(obj,'kind','') or '')
        shape=getattr(obj,'shape',None);transform=getattr(obj,'transform',None)
        if kind in _SKIP_KINDS or shape is None or transform is None or getattr(shape,'type','')!='box':continue
        identity=str(getattr(obj,'id',''))
        if identity.endswith('_keepout'):continue  # synthetic keepouts are not visible geometry
        dims=tuple(float(v) for v in shape.dimensions_m)
        if len(dims)!=3 or any(not math.isfinite(v) or v<=0 for v in dims):continue
        position=tuple(float(v) for v in transform.position_m);yaw=float(transform.rotation_rpy_deg[2]) if transform.rotation_rpy_deg else 0.
        category=_CATEGORY_BY_KIND.get(kind,'unknown')
        if category=='floor':
            if floor_seen:continue
            name='floor';floor_seen=True
            # Imported floors are the top face at z=0: keep the generated slab below the floor plane.
            position=(position[0],position[1],-dims[2]/2)
        else:
            counters[category]=counters.get(category,0)+1;name='%s%d'%(category,counters[category])
        color=_COLOR_BY_KIND.get(kind,(.6,.6,.62))
        points=_box_vertices(position,dims,yaw)
        prims.append('    def Mesh "%s" (\n        customData = { string twinpulseGeneratedId = "%s" string twinpulseGeneratedKind = "%s" }\n    )\n    {\n'
            '        int[] faceVertexCounts = [%s]\n        int[] faceVertexIndices = [%s]\n        point3f[] points = [%s]\n'
            '        color3f[] primvars:displayColor = [(%.3f, %.3f, %.3f)]\n        uniform token subdivisionScheme = "none"\n    }\n'
            %(name,identity.replace('"',''),kind.replace('"',''),', '.join('3' for _ in _TRIANGLES),', '.join(str(i) for t in _TRIANGLES for i in t),
              ', '.join('(%.4f, %.4f, %.4f)'%p for p in points),*color))
    if not floor_seen:raise ValueError('GENERATED_TWIN_FLOOR_REQUIRED')
    header=('#usda 1.0\n(\n    defaultPrim = "World"\n    metersPerUnit = 1\n    upAxis = "Z"\n    doc = "TwinPulse generated Twin export %s; approximate boxes from a photo/text generation, not measured"\n)\n\n'
            'def Xform "World" (\n    customData = { string twinpulseExport = "%s" string twinpulseSceneId = "%s" }\n)\n{\n'%(EXPORT_SCHEMA,EXPORT_SCHEMA,str(scene_id).replace('"','')))
    return header+''.join(prims)+'}\n'


__all__=['generated_twin_usda','EXPORT_SCHEMA']


def generated_twin_environment(objects,usda_bytes,*,source_name,scene_id='generated_twin'):
    """The same boxes as a validated imported-environment contract (what the inspection worker would produce).

    Prim names carry the categories (floor, wall, storage for racks, unknown otherwise); colours follow the kind.
    The USDA bytes are the archived source, so provenance stays checkable.
    """
    import hashlib
    from twinpulse_core.environment_source import SCHEMA, checked_environment
    counters={};meshes=[];floor_seen=False
    for obj in objects:
        kind=str(getattr(obj,'kind','') or '');shape=getattr(obj,'shape',None);transform=getattr(obj,'transform',None)
        if kind in _SKIP_KINDS or shape is None or transform is None or getattr(shape,'type','')!='box':continue
        identity=str(getattr(obj,'id',''))
        if identity.endswith('_keepout'):continue
        dims=tuple(float(v) for v in shape.dimensions_m)
        if len(dims)!=3 or any(not math.isfinite(v) or v<=0 for v in dims):continue
        position=tuple(float(v) for v in transform.position_m);yaw=float(transform.rotation_rpy_deg[2]) if transform.rotation_rpy_deg else 0.
        category=_CATEGORY_BY_KIND.get(kind,'unknown')
        if category=='floor':
            if floor_seen:continue
            name='floor';floor_seen=True;position=(position[0],position[1],-dims[2]/2)
        else:
            counters[category]=counters.get(category,0)+1;name='%s%d'%(category,counters[category])
        path='/World/'+name
        meshes.append(dict(id='Env_'+hashlib.sha256(path.encode()).hexdigest()[:20],source_path=path,category=category,label=name,
            points_m=[[round(v,4) for v in p] for p in _box_vertices(position,dims,yaw)],triangles=[list(t) for t in _TRIANGLES],
            color_rgb=[float(c) for c in _COLOR_BY_KIND.get(kind,(.6,.6,.62))],translation_m=[0.,0.,0.]))
    if not floor_seen:raise ValueError('GENERATED_TWIN_FLOOR_REQUIRED')
    return checked_environment(dict(schema_version=SCHEMA,source_name=source_name,source_sha256=hashlib.sha256(usda_bytes).hexdigest(),
        source_up_axis='Z',source_meters_per_unit=1.,meters_per_unit=1.,units_basis='authored',floor_offset_m=0.,meshes=meshes))


__all__.append('generated_twin_environment')
