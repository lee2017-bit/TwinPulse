# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Standalone field configuration contract shared by PC and robot workers.

Only standard-library imports: validating an offline setting never imports
tracking, multiprocessing, ROS, devices, or timing-worker dependencies.
"""
from copy import deepcopy
import hashlib
import json
import math
import re

SCHEMA='supervised-field-test-1.0'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def checked_config(value,*,robot_id=None,binding_sha256=None):
    bounds=dict(footprint_radius_m=(.08,.6),sensor_x_m=(-.6,.6),sensor_y_m=(-.6,.6),
        sensor_yaw_rad=(-math.pi,math.pi),wheel_metres_per_tick=(.000001,.01),wheel_separation_m=(.08,.8))
    keys={'schema','robot_id','binding_sha256','provenance','axes_reviewed','angle_sign',*bounds}
    if not isinstance(value,dict) or set(value)!=keys or value['schema']!=SCHEMA:raise ValueError('FIELD_CONFIG_SHAPE')
    if (not isinstance(value['robot_id'],str) or not re.fullmatch('[a-f0-9]{32}',value['robot_id'])
            or not isinstance(value['binding_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',value['binding_sha256'])
            or robot_id is not None and value['robot_id']!=robot_id
            or binding_sha256 is not None and value['binding_sha256']!=binding_sha256):raise ValueError('FIELD_CONFIG_ROBOT_BINDING')
    if (value['provenance'] not in {'reference','operator_reviewed','operator_measured'} or value['axes_reviewed'] is not True
            or type(value['angle_sign']) is not int or value['angle_sign'] not in {-1,1}):raise ValueError('FIELD_AXES_AND_PROVENANCE_REVIEW_REQUIRED')
    for key,(low,high) in bounds.items():
        if type(value[key]) not in (int,float) or not math.isfinite(value[key]) or not low<=value[key]<=high:raise ValueError('FIELD_VALUE_OUTSIDE_RANGE_'+key.upper())
    return deepcopy(value)
