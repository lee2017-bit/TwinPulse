# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only USD surface sections for display-only SIM scans; no motion policy."""
import math
from twinpulse_core.lidar_geometry import SectionIndex,slice_triangle


def mesh_triangles(prim):
    from pxr import UsdGeom,Gf
    if prim.IsA(UsdGeom.Mesh):
        mesh=UsdGeom.Mesh(prim);vertices=mesh.GetPointsAttr().Get() or []
        counts=mesh.GetFaceVertexCountsAttr().Get() or [];indices=mesh.GetFaceVertexIndicesAttr().Get() or []
        holes=set(mesh.GetHoleIndicesAttr().Get() or []);faces=[];cursor=0
        for face,count in enumerate(counts):
            ids=indices[cursor:cursor+count];cursor+=count
            if face not in holes:faces.extend((ids[0],ids[i],ids[i+1]) for i in range(1,count-1))
    elif prim.IsA(UsdGeom.Cube):
        half=float(UsdGeom.Cube(prim).GetSizeAttr().Get())/2
        vertices=[(x*half,y*half,z*half) for z in (-1,1) for y in (-1,1) for x in (-1,1)]
        quads=((0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3))
        faces=[t for a,b,c,d in quads for t in ((a,b,c),(a,c,d))]
    elif prim.IsA(UsdGeom.Cylinder):
        cylinder=UsdGeom.Cylinder(prim);radius=float(cylinder.GetRadiusAttr().Get());half=float(cylinder.GetHeightAttr().Get())/2
        axis=cylinder.GetAxisAttr().Get();vertices=[]
        for z in (-half,half):
            for i in range(32):
                x,y=radius*math.cos(i*math.tau/32),radius*math.sin(i*math.tau/32)
                vertices.append((z,x,y) if axis=='X' else (y,z,x) if axis=='Y' else (x,y,z))
        faces=[t for i in range(32) for t in ((i,(i+1)%32,i+32),((i+1)%32,(i+1)%32+32,i+32))]
        faces.extend((ring,ring+i,ring+i+1) for ring in (0,32) for i in range(1,31))
    else:return []
    if len(faces)>200000:raise ValueError('LIDAR_MESH_BUDGET')
    matrix=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0)
    points=[tuple(matrix.Transform(Gf.Vec3d(*v))) for v in vertices]
    if any(not math.isfinite(v) for p in points for v in p):raise ValueError('LIDAR_GEOMETRY_NONFINITE')
    return [(points[a],points[b],points[c]) for a,b,c in faces]


def scene_section(stage,height):
    """Use displayed furniture surfaces, not its hidden filled collision proxy.

    Keep authoritative motion collision proxies unchanged. Decorative parts are
    included because this is the geometric sensing/display path, not navigation.
    """
    from pxr import Usd
    environment=stage.GetPrimAtPath('/World/TwinPulse/Environment')
    presentation=stage.GetPrimAtPath('/World/TwinPulse/Presentation/RoomModels')
    # SIM-world test obstacles: visible to the SIM LiDAR like any surface, but never part of the Twin model.
    sim_obstacles=stage.GetPrimAtPath('/World/TwinPulse/Fleet/SimObstacles')
    replaced=set()
    if presentation:
        for group in presentation.GetChildren():replaced.update(group.GetCustomDataByKey('currentGeometryIds') or [])
    segments=[];surfaces=[];triangles=0
    for root in (environment,presentation,sim_obstacles):
        if not root:continue
        for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
            # Uncertainty/entanglement keepouts are deliberate safety geometry,
            # not visible surfaces or fabricated range measurements.
            if prim.GetCustomDataByKey('syntheticKeepout'):continue
            if root==environment:
                relative=str(prim.GetPath()).removeprefix(str(root.GetPath())+'/').split('/')[0]
                if relative in replaced:continue
            sliced=[]
            for triangle in mesh_triangles(prim):
                triangles+=1
                if triangles>250000:raise ValueError('LIDAR_SCENE_BUDGET')
                sliced.extend(slice_triangle(triangle,height))
            if sliced:surfaces.append(str(prim.GetPath()));segments.extend(sliced)
    return SectionIndex(segments),dict(height_m=height,segments=len(segments),triangles=triangles,surfaces=surfaces,
        source='usd_display_surfaces_horizontal_section',collision_policy_changed=False)


def sensor_pose(stage,robot_path):
    from pxr import UsdGeom
    # The reviewed Burger USD reference exposes this frame; do not substitute a
    # guessed height if an incompatible model/frame is loaded.
    path=robot_path+'/Model/Geometry/base_footprint/base_link/base_scan'
    prim=stage.GetPrimAtPath(path)
    if not prim:raise ValueError('LIDAR_MODEL_SCAN_FRAME_MISSING')
    matrix=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0)
    origin=matrix.ExtractTranslation();x=matrix.ExtractRotationMatrix().GetRow(0)
    z=matrix.ExtractRotationMatrix().GetRow(2)
    if abs(x[2])>1e-6 or z[2]<1-1e-6:raise ValueError('LIDAR_HORIZONTAL_MODEL_REQUIRED')
    return [float(origin[0]),float(origin[1]),math.atan2(float(x[1]),float(x[0]))],float(origin[2]),path
