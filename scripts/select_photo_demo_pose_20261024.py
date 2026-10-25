# SPDX-License-Identifier: Apache-2.0
"""Offline SIM test placement, not photo-derived metric/world alignment."""
import hashlib,json,math,sys
from copy import deepcopy
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'packages/twinpulse_core/src'))
from twinpulse_core.environment_navigation import navigation_cells
from twinpulse_core.environment_overlays import add_overlay,remove_overlay
out=root/'outputs/environment-photo-live-20261024-01'
raw=(out/'adopt03/result.json').read_bytes();result=json.loads(raw)
env=result['preview']['operation']['tool_call']['arguments']['environment'];overlay=env['overlays'][0]
base=remove_overlay(env,overlay['item']['id'])
boxes=[];overhead=[]
for m in env['meshes']:
    if m['category']=='floor':continue
    p=[[q[i]+m['translation_m'][i] for i in range(3)] for q in m['points_m']]
    lo=[min(q[i] for q in p) for i in range(3)];hi=[max(q[i] for q in p) for i in range(3)]
    # Low geometry is covered by the unchanged triangle navigation cells.
    # A rotated wall's entire AABB is not an occupied room. Here only add the
    # separate overhead-visibility exclusion that the robot-height map lacks.
    if lo[2]>.3:boxes.append((lo,hi))
    if lo[0]<-4.15<hi[0] and lo[1]<-.45<hi[1]:overhead.append(dict(id=m['id'],category=m['category'],low=lo,high=hi))
cells=navigation_cells(env['meshes'])['cells']
blocked=[(a,b) for a,b,state,*_ in cells if state!='free']
def gap(x,y):return min([math.hypot(max(a[0]-x,0,x-b[0]),max(a[1]-y,0,y-b[1])) for a,b in boxes]+[math.hypot(x-a,y-b) for a,b in blocked])
free={(round(x,2),round(y,2)) for x,y,s,*_ in cells if s=='free'}
candidates=[]
for x,y in sorted(free):
    if any((round(x+dx,2),round(y+dy,2)) not in free for dx in (-.2,0,.2) for dy in (-.2,0,.2)):continue
    if (round(x+1,2),round(y,2)) not in free:continue
    clearance=min(gap(x,y),gap(x+1,y))
    if clearance<.6:continue
    candidate=deepcopy(overlay);candidate['item']['position_m']=[x+1,y,.2]
    try:add_overlay(base,candidate)
    except ValueError:continue
    candidates.append((clearance,x,y))
if not candidates:
    print(json.dumps(dict(free_cells=len(free),blocked_cells=len(blocked),overhead_boxes=len(boxes),best_free=sorted([(gap(x,y),x,y) for x,y in free],reverse=True)[:6])))
    raise ValueError('NO_OPEN_TEST_PAIR')
clearance,x,y=max(candidates)
value=dict(scope='OFFLINE_SIM_TEST_PLACEMENT_NOT_PHOTO_WORLD_MATCH',source_response_sha256=hashlib.sha256(raw).hexdigest(),
    original_overhead=overhead,robot_pose=[x,y,0],obstacle_xy=[x+1,y],minimum_all_height_bbox_clearance_m=clearance)
with (out/'open-test-pose.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
print(json.dumps(value))
