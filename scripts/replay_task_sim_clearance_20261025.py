# SPDX-License-Identifier: Apache-2.0
"""Replay the original failed SIM primitive against its exact saved geometry."""
import argparse,hashlib,json,math,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.robot_survey import checked_motion_segment,route_to,task_clearance
from scripts.twinpulse_fleet_runtime import integrate_motion
parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
out=ROOT/'outputs/physical-task-preparation-20261025-01'/('clearance-replay'+args.attempt);out.mkdir(exist_ok=False)
path=ROOT/'outputs/physical-task-preparation-20261025-01/survey02/result.json'
original=json.loads(path.read_bytes());job=original['final_task']
event=[e for e in job['events'] if e['kind']=='child_started'][-1]
source=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects'/job['project_id']/'robot-tasks'/job['task_id']/('navigation-'+event['navigation_sha256']+'.json')
raw=source.read_bytes();scene=json.loads(raw)
assert canonical_sha256(scene)==event['navigation_sha256']
(out/source.name).write_bytes(raw)
pose=event['checked_pose'];amount=.4;g=scene['geometry'];cells=scene.get('observed_cells')
# Imported rooms guard the union of all non-free .1m cells, not only the
# semantic obstacle AABBs (which are empty for this original imported room).
# Per-cell rectangles preserve the same union as the runtime's merged runs.
boxes=list(g['obstacles'])+[[x-.05,y-.05,x+.05,y+.05] for x,y,state,*_ in (cells or []) if state!='free']
old=checked_motion_segment(pose,'forward',amount,g,observed_cells=cells)
def execute(p,d,amount):
    p=list(p);travel=0.;reason=None
    while travel<amount-1e-9:
        p,delta,reason,_=integrate_motion(p,d,.1,boxes,amount-travel)
        travel+=delta
        if reason:break
    return p,reason
failed,reason=execute(pose,'forward',amount)
try:checked_motion_segment(pose,'forward',amount,g,observed_cells=cells,clearance_m=task_clearance('sim'));veto=False
except ValueError:veto=True
route=route_to(pose,original['start']['pose']['position_m'][:2],g,observed_cells=cells,clearance_m=task_clearance('sim',planning=True))
current=list(pose);reasons=[]
for goal in route:
    dx,dy=goal[0]-current[0],goal[1]-current[1];distance=math.hypot(dx,dy)
    if distance<1e-9:continue
    error=math.atan2(math.sin(math.atan2(dy,dx)-current[2]),math.cos(math.atan2(dy,dx)-current[2]))
    current,r=execute(current,'left' if error>=0 else 'right',abs(error));reasons.append(r)
    current,r=execute(current,'forward',distance);reasons.append(r)
checks=dict(original_failure_retained=job['state']=='FAILED' and job['reason']=='ROBOT_TASK_CHILD_FAILED: OBSTACLE_STOP',
    old_15cm_preflight_passed=old==event['predicted_endpoint_m'],same_executor_reproduced_stop=reason=='OBSTACLE_STOP',
    effective_preflight_rejects=veto,replanned_route_preserves_executor=all(r is None for r in reasons),
    replanned_return_xy=math.dist(current[:2],original['start']['pose']['position_m'][:2])<1e-6)
value=dict(status='PASS' if all(checks.values()) else 'FAIL',scope='ORIGINAL_SIM_GEOMETRY_PURE_REPLAY_NOT_INSTALLED_UI_OR_PHYSICAL',checks=checks,
    source=dict(path=str(source),sha256=hashlib.sha256(raw).hexdigest(),task_id=job['task_id'],navigation_sha256=event['navigation_sha256']),
    original_result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),original_pose=pose,original_runtime_stop_pose=failed,
    requested_minimum_m=.15,effective_sim_reference_m=task_clearance('sim'),sim_planning_m=task_clearance('sim',planning=True),route=route,
    collision_geometry_basis='SAME_ORIGINAL_NONFREE_CELL_UNION_AS_RUNTIME_MERGED_MANUAL_BOXES',
    unchanged_stop_protection=True,model_calls=0,physical_actions=0)
(out/'result.json').write_text(json.dumps(value,indent=2),encoding='utf-8');print(json.dumps(value));sys.exit(0 if value['status']=='PASS' else 1)
