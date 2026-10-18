# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read fixed saved model/scan bytes. No device access, TF or calibration creation."""
import hashlib
import itertools
import json
import math
import struct
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.revisions import canonical_sha256

from .runtime_paths import resource_root
ROOT=resource_root()
MODEL='artifacts/robot-models/turtlebot3-source/turtlebot3_description'
URDF_SHA='7b0cdc0f9241efa8a4f316f54f81f081aea79d29393fde81867185d07ca57572'
COMMIT='90a68bd2e3c61c12966779da89d8eeaec82730e9'
MESH_HASHES={
    'meshes/bases/burger_base.stl':'7d7f3329a437b43bbcbbec59f9a2d1df1d88b59c3882c543d979baf73670f025',
    'meshes/wheels/left_tire.stl':'578c9452ee51c2f71e5e6723b503d784e58a6ac317fa53ee308e645f204c8d6a',
    'meshes/wheels/right_tire.stl':'407aaf271ba7051c6186b220e1dc36b2a6eca688fced66a3347f49747b684596',
    'meshes/sensors/lds.stl':'98f0bd7046159f83caab9509293112ef13534368535669124b91b5114c3132f6'}
CAPTURE='artifacts/lidar-capture-20260927-1214/lidar-20260927T031354Z-323c99a6'


def origin(element):
    o=element.find('origin')
    xyz=[float(v) for v in (o.get('xyz','0 0 0') if o is not None else '0 0 0').split()]
    r,p,y=[float(v) for v in (o.get('rpy','0 0 0') if o is not None else '0 0 0').split()]
    cr,sr,cp,sp,cy,sy=math.cos(r),math.sin(r),math.cos(p),math.sin(p),math.cos(y),math.sin(y)
    return xyz,((cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr),
                (sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr),(-sp,cp*sr,cp*cr))


def transformed(point,chain):
    for t,r in reversed(chain):point=[t[i]+sum(r[i][j]*point[j] for j in range(3)) for i in range(3)]
    return point


@lru_cache(maxsize=4)
def mesh_points(data,scale,chain):
    # Cache only calculations keyed by immutable, freshly read source bytes.
    # File hashes are still checked on every evidence/goal request.
    count=struct.unpack_from('<I',data,80)[0]
    if len(data)!=84+50*count or count>1000000:raise ValueError('BINARY_STL_SHAPE')
    points=[]
    for index in range(count):
        values=struct.unpack_from('<9f',data,84+index*50+12)
        for offset in (0,3,6):
            point=transformed([values[offset+i]*scale[i] for i in range(3)],chain)
            if any(not math.isfinite(v) or abs(v)>2 for v in point):raise ValueError('MODEL_VERTEX_INVALID')
            points.append(tuple(point))
    return tuple(points)


@lru_cache(maxsize=1)
def scan_summary(data):
    bundle=NativeScanBundle.from_text(data.decode()).to_dict()
    return bundle['source']['raw_sha256'],bundle['source']['nodes_sha256'],bundle['source']['timestamp_basis'],len(bundle['frames'])


def load_geometry_evidence(root=ROOT):
    root=Path(root).resolve();sources={}
    def read(relative):
        path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('EVIDENCE_PATH_OUTSIDE_ROOT')
        raw=path.read_bytes();sources[relative]=hashlib.sha256(raw).hexdigest();return raw
    metadata=json.loads(read('artifacts/robot-models/burger-prepared/source.json'))
    raw=read(MODEL+'/urdf/turtlebot3_burger.urdf')
    if hashlib.sha256(raw).hexdigest()!=URDF_SHA or metadata['commit']!=COMMIT:
        raise ValueError('PINNED_MODEL_CHANGED')
    tree=ET.fromstring(raw.decode().replace('${namespace}',''))
    joints={j.find('child').get('link'):j for j in tree.findall('joint')}
    def chain(link):
        if link=='base_link':return []
        if link not in joints:raise ValueError('MODEL_CHAIN_MISSING')
        j=joints[link];return chain(j.find('parent').get('link'))+[origin(j)]
    collision=[];visual=[]
    for link in tree.findall('link'):
        name=link.get('name')
        if name=='base_footprint':continue
        link_chain=chain(name)
        for item in link.findall('collision'):
            geometry=item.find('geometry');box=geometry.find('box');cylinder=geometry.find('cylinder')
            if box is not None:half=[float(v)/2 for v in box.get('size').split()]
            elif cylinder is not None:half=[float(cylinder.get('radius'))]*2+[float(cylinder.get('length'))/2]
            else:raise ValueError('UNSUPPORTED_COLLISION_PRIMITIVE')
            # Cylinder local AABB transformed conservatively, includes rounded 1.57 URDF rotations.
            collision.extend(transformed(corner,link_chain+[origin(item)])
                for corner in itertools.product(*[(-v,v) for v in half]))
        for item in link.findall('visual'):
            mesh=item.find('geometry/mesh')
            if mesh is None:continue
            relative=mesh.get('filename').replace('package://turtlebot3_description/',MODEL+'/')
            data=read(relative);key=relative[len(MODEL)+1:].replace('/','\\')
            if sources[relative]!=metadata['mesh_sha256'][key] or sources[relative]!=MESH_HASHES[relative[len(MODEL)+1:]]:
                raise ValueError('MODEL_MESH_CHANGED')
            scale=tuple(float(v) for v in mesh.get('scale','1 1 1').split())
            mesh_chain=tuple((tuple(t),r) for t,r in link_chain+[origin(item)])
            visual.extend(mesh_points(data,scale,mesh_chain))
    def bounds(points):return [[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)]
    collision_bounds=bounds(collision);visual_bounds=bounds(visual)
    nominal_radius=max(math.hypot(p[0],p[1]) for p in collision+visual)
    scan_paths=('artifacts/photo-scan-review-20260927/native-scan-bundle.json',
                CAPTURE+'/report.json',CAPTURE+'/raw.bin','artifacts/lidar-capture-20260927-1214/nodes.ndjson')
    presence=[(root/p).exists() for p in scan_paths]
    if any(presence) and not all(presence):raise ValueError('SAVED_SCAN_EVIDENCE_INCOMPLETE')
    if all(presence):
        raw_hash,nodes_hash,time_basis,frame_count=scan_summary(read(scan_paths[0]))
        report=json.loads(read(scan_paths[1]));raw=read(scan_paths[2]);nodes=read(scan_paths[3])
        if (hashlib.sha256(raw).hexdigest()!=report['raw_sha256'] or report['raw_sha256']!=raw_hash
            or hashlib.sha256(nodes).hexdigest()!=nodes_hash):raise ValueError('SAVED_SCAN_SOURCE_CHANGED')
        saved_scan={'boot_id':report['boot_id'],'raw_sha256':report['raw_sha256'],
            'frames':frame_count,'basis':time_basis,
            'odom_pose':None,'sensor_to_base_tf':None,'native_angle_convention_verified':False}
    else:
        # Generic installs do not contain a user's historic room captures.
        # Nominal dimensions can be inspected independently; this grants no
        # measured TF, scan availability, physical match or motion authority.
        saved_scan={'status':'NOT_PROVIDED','boot_id':None,'raw_sha256':None,'frames':0,
            'basis':'NO_SAVED_SCAN_INPUT','odom_pose':None,'sensor_to_base_tf':None,
            'native_angle_convention_verified':False}
    base=origin(joints['base_link'])[0];scan=origin(joints['base_scan'])[0]
    result={'schema':'robot-geometry-evidence-1.0',
        'basis':'PINNED_NOMINAL_MODEL_AND_SAVED_RAW_SCAN' if all(presence) else 'PINNED_NOMINAL_MODEL_ONLY',
        'model_commit':COMMIT,'base_footprint_to_base_link_xyz_m':base,'base_link_to_scan_xyz_m':scan,
        'base_link_to_scan_rpy_rad':[0.,0.,0.],
        'wheel_separation_m':abs(origin(joints['wheel_left_link'])[0][1]-origin(joints['wheel_right_link'])[0][1]),
        'wheel_radius_m':float(tree.find("link[@name='wheel_left_link']/collision/geometry/cylinder").get('radius')),
        'collision_aabb_base_link_m':collision_bounds,'visual_aabb_base_link_m':visual_bounds,
        'nominal_envelope_radius_m':nominal_radius,'retained_guard_radius_m':max(.18,nominal_radius),
        'size_basis':'NOMINAL_URDF_COLLISIONS_AND_MESH_VERTICES_AT_ZERO_JOINT_POSE_NOT_AS_BUILT',
        'saved_scan':saved_scan,
        'physical_robot_match':'UNVERIFIED','alignment_verified':False,'motion_authorized':False,
        'missing':['AS_BUILT_SENSOR_POSE_AND_FOOTPRINT','NATIVE_ANGLE_TO_ROS_SCAN_CONVENTION',
            'SAME_TIME_ODOM_AND_TF','METRIC_TWIN_ODOM_CORRESPONDENCES','CURRENT_BOOT_AND_DEPLOYMENT'],
        'source_sha256':sources}
    if not any(presence):result['missing'].append('SAVED_RAW_SCAN_NOT_PROVIDED')
    return {**result,'revision':canonical_sha256(result)}
