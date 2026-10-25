# SPDX-License-Identifier: Apache-2.0
"""Read-only capability/scoring probe. No model, device, Apply or package change."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_core.room_items import expand_room_item,room_item_risk
from twinpulse_core.room_item_catalog import room_item_catalog_version
from twinpulse_core.site_tools import SiteToolPlan,validate_site_tool_plan
from twinpulse_core.scene_tools import SceneToolCall
from twinpulse_core.room_localization import RoomMatcher,compose,segment_distance
from twinpulse_core.environment_section import matching_outline
from twinpulse_app.scan_fit_diagnostics import uniform_ring

SOURCE=ROOT/'outputs/roomplan-lidar-review-20261024-02'
OUT=ROOT/'outputs/roomplan-hybrid-method-review-20261024-01'
names=('environment.json','review.json','height-section.json')
raw={name:(SOURCE/name).read_bytes() for name in names}
environment=json.loads(raw['environment.json']);review=json.loads(raw['review.json'])
section=json.loads(raw['height-section.json']);catalog=[]
for kind in ('floor_fan','basket','bag','clothing_pile','cable_bundle'):
    args=dict(id='Probe_'+kind,kind=kind,label=kind,catalog_version=room_item_catalog_version(kind),
        position_m=[0.,0.,.25],dimensions_m=[.4,.4,.5],yaw_deg=0.,observation_time_utc=None)
    # Deliberate synthetic dimensions, not photo-derived estimates/measurements.
    objects=expand_room_item(args)
    catalog.append(dict(kind=kind,risk=room_item_risk(args),objects=len(objects),
        colliders=sum(o.collision for o in objects),has_keepout=any(o.id.endswith('_keepout') for o in objects)))
base=SceneToolCall('imported_space','import_environment',dict(id='imported_space',environment=environment))
args=dict(id='Probe_basket',kind='basket',label='basket',catalog_version=room_item_catalog_version('basket'),
    position_m=[0.,0.,.25],dimensions_m=[.4,.4,.5],yaw_deg=0.,observation_time_utc=None)
imported=SiteToolPlan('HybridProbe','Read-only probe','No photo inference',(base,),plan_version='2.4')
validate_site_tool_plan(imported)
try:
    validate_site_tool_plan(SiteToolPlan('HybridProbe','Read-only probe','No photo inference',
        (base,SceneToolCall('probe_basket','place_room_item',args)),plan_version='2.4'))
    mixed='UNEXPECTED_ACCEPTANCE'
except ValueError as error:mixed=str(error)
outline=matching_outline(environment,review['sensor_height_m'])
matcher=RoomMatcher(outline);points=uniform_ring(review['points_sensor_local'],120)
pose=review['match']['pose'];score,inliers=matcher.score(points,pose)
projected=[compose(pose,[*p,0])[:2] for p in points]
segments=[s for s in section['segments'] if s['category'] in
    {'wall','door','chair','table','sofa','storage','refrigerator'}]
counts={'within_5cm':0,'5_to_15cm':0,'over_15cm':0};category={}
for point in projected:
    distance,surface=min((segment_distance(point,s['ends_m']),i) for i,s in enumerate(segments))
    key='within_5cm' if distance<=.05 else '5_to_15cm' if distance<=.15 else 'over_15cm'
    counts[key]+=1;name=segments[surface]['category'];category[name]=category.get(name,0)+1
result=dict(schema='roomplan-photo-hybrid-method-review-1.0',scope='READ_ONLY_SAVED_DATA_AND_CATALOG_NOT_PRODUCT_OR_BODY_ACCEPTANCE',
    source_sha256={name:hashlib.sha256(value).hexdigest() for name,value in raw.items()},
    source_usd_sha256=environment['source_sha256'],original_operation_id=review['operation_id'],
    catalog_expansion=catalog,synthetic_dimensions_not_photo_inference=True,
    environment_only_accepted=True,mixed_environment_and_existing_prop_result=mixed,
    frozen_existing_pose_no_new_search=True,
    recorded_score=review['match']['mean_error_m'],reproduced_grid_score=score,
    recorded_inlier_fraction=review['match']['inlier_fraction'],reproduced_inlier_fraction=inliers,
    exact_segment_distance_counts=counts,nearest_surface_category_counts=category,
    unmatched_identity='UNKNOWN_NOT_AUTOMATICALLY_CLUTTER_OR_BAD_POSE',
    conclusion='Existing props exist but the version2.4 import contract prohibits mixing. Whole-return score combines pose and model-coverage error.',
    product_modified=False,geometry_applied=False,motion_authorized=False,
    source_files_unchanged=all((SOURCE/name).read_bytes()==value for name,value in raw.items()))
assert mixed=='ENVIRONMENT_PLAN_INVALID' and abs(score-review['match']['mean_error_m'])<1e-12
assert result['source_files_unchanged']
OUT.mkdir(parents=True)
with (OUT/'probe.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
print(json.dumps(result,indent=2))
