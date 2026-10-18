# SPDX-License-Identifier: Apache-2.0
"""ROBOTIS TB3 voltage display, not coulomb-counted state of charge.

Public OpenCR ROS2 update_battery_status maps 3*3.5V to 0% and
3*4.1V to 100%. This is distinct from the nominal 11.1V pack label,
the pack's charging specification and independent low-voltage protection.
https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3.cpp
"""
import math
from copy import deepcopy
import hashlib
import json

ESTIMATE_METHOD='robotis_opencr_voltage_10_5_to_12_3_v1'
RESERVE_PERCENT=20
LOW_VOLTAGE_GUARD_V=11.1  # Existing TwinPulse source guard, NOT a 20% equivalent.
DISPLAY_SCHEMA='robot-battery-display-1.0'
ROBOTIS_SOURCE='https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3.cpp'


def battery_display_config(mode='voltage_only'):
    if mode not in {'voltage_only','robotis_opencr','custom'}:
        raise ValueError('ROBOT_BATTERY_MODE_INVALID')
    return dict(schema_version=DISPLAY_SCHEMA,mode=mode,
        label='ROBOTIS OpenCR reference' if mode=='robotis_opencr' else '',
        source=ROBOTIS_SOURCE if mode=='robotis_opencr' else '',
        points=[dict(voltage_v=10.5,percent=0.),dict(voltage_v=12.3,percent=100.)] if mode=='robotis_opencr' else [])


def checked_battery_display(value):
    """Data-only display settings. Never consumed by motion/firmware guards."""
    if (not isinstance(value,dict) or set(value)!={'schema_version','mode','label','source','points'}
            or value['schema_version']!=DISPLAY_SCHEMA or not isinstance(value['mode'],str)
            or value['mode'] not in {'voltage_only','robotis_opencr','custom'}):
        raise ValueError('ROBOT_BATTERY_CONFIG_INVALID')
    for key,limit in (('label',120),('source',500)):
        if not isinstance(value[key],str) or len(value[key])>limit or any(ord(c)<32 for c in value[key]):
            raise ValueError('ROBOT_BATTERY_CONFIG_INVALID')
    if value['mode']!='custom':
        # A named official preset cannot silently carry user-altered points.
        if value!=battery_display_config(value['mode']):raise ValueError('ROBOT_BATTERY_PRESET_CHANGED')
        return deepcopy(value)
    points=value['points']
    if not isinstance(points,list) or not 2<=len(points)<=32:raise ValueError('ROBOT_BATTERY_POINTS_INVALID')
    previous=(0.,-1.)
    for point in points:
        if not isinstance(point,dict) or set(point)!={'voltage_v','percent'}:raise ValueError('ROBOT_BATTERY_POINTS_INVALID')
        v,p=point['voltage_v'],point['percent']
        if (type(v) not in (int,float) or type(p) not in (int,float) or not math.isfinite(v) or not math.isfinite(p)
                or not 0<v<=1000 or not 0<=p<=100 or v<=previous[0] or p<=previous[1]):
            raise ValueError('ROBOT_BATTERY_POINTS_INVALID')
        previous=(v,p)
    if points[0]['percent']!=0 or points[-1]['percent']!=100:raise ValueError('ROBOT_BATTERY_ENDPOINTS_INVALID')
    return deepcopy(value)


def battery_display_estimate(voltage,config):
    config=checked_battery_display(config)
    identity=battery_display_sha256(config)
    points=config['points'];percent=None
    if (config['mode']!='voltage_only' and type(voltage) in (int,float) and math.isfinite(voltage) and 0<voltage<=1000
            and (config['mode']!='robotis_opencr' or 3.5<=voltage<=13)):
        if voltage<=points[0]['voltage_v']:percent=0.
        elif voltage>=points[-1]['voltage_v']:percent=100.
        else:
            for a,b in zip(points,points[1:]):
                if a['voltage_v']<=voltage<=b['voltage_v']:
                    percent=a['percent']+(voltage-a['voltage_v'])/(b['voltage_v']-a['voltage_v'])*(b['percent']-a['percent']);break
        percent=round(percent,1)
    return dict(estimated_percent=percent,estimate_method=ESTIMATE_METHOD if config['mode']=='robotis_opencr' else
        'custom_voltage_table_v1' if config['mode']=='custom' else 'voltage_only',capacity_measured=False,
        display_mode=config['mode'],display_label=config['label'],display_source=config['source'],display_config_sha256=identity)


def battery_display_sha256(config):
    return hashlib.sha256(json.dumps(checked_battery_display(config),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def battery_estimate(voltage):
    valid=type(voltage) in (int,float) and math.isfinite(voltage) and 3.5<=voltage<=13.
    percent=round(max(0.,min(100.,(voltage-10.5)/1.8*100)),1) if valid else None
    return dict(estimated_percent=percent,estimate_method=ESTIMATE_METHOD,
        capacity_measured=False,reserve_threshold_percent=RESERVE_PERCENT,
        reserve_state='UNKNOWN' if percent is None else 'AT_OR_BELOW_RESERVE' if percent<=RESERVE_PERCENT else 'ABOVE_RESERVE',
        voltage_protection='UNKNOWN' if not valid else 'LOW_VOLTAGE_GUARD' if voltage<=LOW_VOLTAGE_GUARD_V else 'CLEAR',
        low_voltage_guard_v=LOW_VOLTAGE_GUARD_V)
