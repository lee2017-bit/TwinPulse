# SPDX-License-Identifier: Apache-2.0
"""Local saved-data hypotheses. No Kit, devices, upload, Apply or source writes."""
import argparse
from collections import Counter
import hashlib
import html
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'packages/twinpulse_robot_safety')]
from twinpulse_core.environment_source import checked_environment,object_bounds
from twinpulse_core.environment_section import horizontal_section,matching_outline
from twinpulse_core.room_localization import RoomMatcher,compose
from twinpulse_app.physical_motion_analysis import read_archive,analyse,windows
from twinpulse_app.scan_fit_diagnostics import uniform_ring
from twinpulse_app.robot_geometry_evidence import load_geometry_evidence
from field_tests import register_pair


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--usd',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--project',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('REVIEW_OUTPUT_ALREADY_EXISTS')
    began=time.monotonic();before=hashlib.sha256(args.usd.read_bytes()).hexdigest()
    archive=read_archive(args.archive,args.archive.name,args.project,began+60)
    motion=analyse(archive,register_pair,began+60)
    # Existing CPython-compatible Isaac USD libraries only; never start Kit.
    usd=list(Path(r'C:\isaacsim\extscache').glob('omni.usd.libs-*.cp312'))
    if len(usd)!=1:raise ValueError('ONE_EXISTING_USD_RUNTIME_REQUIRED')
    handles=[os.add_dll_directory(str(usd[0]/'bin')),os.add_dll_directory(r'C:\isaacsim\kit')]
    sys.path.insert(0,str(usd[0]))
    from twinpulse_environment_worker import inspect_environment
    environment=checked_environment(inspect_environment(args.usd,'m'))
    geometry=load_geometry_evidence(ROOT)
    height=geometry['base_footprint_to_base_link_xyz_m'][2]+geometry['base_link_to_scan_xyz_m'][2]
    section=horizontal_section(environment,height);outline=matching_outline(environment,height)
    inventory=[]
    for mesh in environment['meshes']:
        lo,hi=object_bounds(mesh)
        inventory.append(dict(id=mesh['id'],label=mesh['label'],category=mesh['category'],bounds_m=[lo,hi],
            dimensions_m=[b-a for a,b in zip(lo,hi)],height_section_segments=sum(s['object_id']==mesh['id'] for s in section['segments'])))
    commands,_=windows(archive);start=commands[0]['start']
    frame=next(s for s in reversed(archive['scans']) if s['end']<=start)
    points=uniform_ring(frame['points_full'],120)
    # No wheel/anchor pose is supplied. Search parameters/quality criteria are
    # the existing RoomMatcher's, not tuned toward this file or encoder output.
    matched=RoomMatcher(outline).match(points)
    projected=[compose(matched['pose'],[*p,0])[:2] for p in frame['points_full']] if matched.get('pose') else []
    result=dict(schema='saved-roomplan-scan-review-1.0',scope='OFFLINE_HYPOTHESIS_NOT_LIVE_PRODUCT_ACCEPTANCE',
        source_sha256=before,source_bytes=args.usd.stat().st_size,source_unchanged=before==hashlib.sha256(args.usd.read_bytes()).hexdigest(),
        units_basis=environment['units_basis'],scale_calibrated=False,operation_id=args.archive.name,project_id=args.project,
        source_twin_context=archive['first']['source_twin_context'],
        source_association='CALLER_SELECTED_USD_HYPOTHESIS_NOT_PROVEN_AGAINST_RECORDED_SCENE_REVISION',
        input_receipt_sha256=archive['receipt_sha256'],input_segments=archive['receipt']['segments'],
        sensor_height_m=height,sensor_height_basis='PINNED_NOMINAL_URDF_NOT_AS_BUILT',model_revision=geometry['revision'],
        source_categories=dict(Counter(m['category'] for m in environment['meshes'])),inventory=inventory,
        scan={k:frame[k] for k in ('stream_id','frame_sequence','start','end','raw_sha256','input_point_count')},
        points_sensor_local=frame['points_full'],points_room_hypothesis=projected,match=matched,
        physical_motion_verified=False,world_registration_verified=False,authority_restored=False,
        geometry_changed=False,scene_applied=False,elapsed_s=time.monotonic()-began,
        code_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
            'scripts/review_saved_roomplan_scan_20261024.py','packages/twinpulse_app/src/twinpulse_app/scan_fit_diagnostics.py',
            'packages/twinpulse_app/src/twinpulse_app/physical_motion_analysis.py',
            'packages/twinpulse_core/src/twinpulse_core/environment_section.py',
            'packages/twinpulse_core/src/twinpulse_core/room_localization.py','packages/twinpulse_robot_safety/field_tests.py')},
        limits=['Global geometric hypothesis only. No live overlay/TF, calibrated scale/extrinsics, first-hit or held-out multi-view acceptance.',
            'Original command/receipt, invalid ring and stationary-baseline limitations remain in motion-review.json.',
            'The map is the immutable same source at explicitly selected meters; not a current scene-edit journal replay.',
            'A full revolution alone supplies overlapping local views, not additional height or a uniquely known world origin.',
            'Unmatched returns can be clutter, glass, sampling, registration or model errors; they are not auto-created furniture.'])
    assert result['source_unchanged']
    args.output.mkdir(parents=True)
    for name,value in [('environment.json',environment),('height-section.json',section),('motion-review.json',motion),('review.json',result)]:
        with (args.output/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)
    bounds=outline['bounds_m'];width=1000;height_px=700
    scale=min((width-80)/(bounds[1]-bounds[0]),(height_px-100)/(bounds[3]-bounds[2]))
    def xy(p):return (40+(p[0]-bounds[0])*scale,height_px-40-(p[1]-bounds[2])*scale)
    graphic=[]
    for segment in section['segments']:
        a,b=map(xy,segment['ends_m']);color='#a8b5c3' if segment['category']=='wall' else '#eab76b'
        graphic.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{color}" stroke-width="2"/>')
    for point in projected:
        x,y=xy(point);graphic.append(f'<circle cx="{x}" cy="{y}" r="2" fill="#26d9e4"/>')
    caption=html.escape('OFFLINE HYPOTHESIS · '+matched['status']+' · NOT CALIBRATED / NOT APPLIED')
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height_px}"><rect width="100%" height="100%" fill="#101d29"/><text x="30" y="28" fill="white" font-size="15">{caption}</text>{"".join(graphic)}</svg>'
    with (args.output/'overlay-hypothesis.svg').open('x',encoding='utf-8') as stream:stream.write(svg)
    print(json.dumps(dict(output=str(args.output),status=matched['status'],match=matched,nominal_height_m=result['sensor_height_m'],
        categories=result['source_categories'],motion=[dict(direction=w['direction'],chain=w['lidar'],diagnostics=w.get('diagnostics')) for w in motion['windows']]),allow_nan=False))


if __name__=='__main__':main()
