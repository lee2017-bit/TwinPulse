# SPDX-License-Identifier: Apache-2.0
"""Bounded engine work/fault evidence, never control authority."""
from copy import deepcopy
import json
import math


def checked_work(value):
    required={'bounds_s','model_authoring_s','bounds_rebuilds'}
    optional={'scan_s','scan_error','update_s','navigation_s','host'}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-required-optional:return None
    for key in required|{'scan_s','update_s','navigation_s'}:
        if key not in value:continue
        n=value[key]
        if type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=86400:return None
    if type(value['bounds_rebuilds']) is not int:return None
    if value.get('scan_error') is not None and (not isinstance(value['scan_error'],str) or len(value['scan_error'])>160):return None
    host=value.get('host',{})
    if not isinstance(host,dict) or set(host)-{'app_update_s','previous_viewport_s','previous_tail_s','gc_pause_s',
            'process_private_mib','available_ram_mib','page_fault_delta'}:return None
    if any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=2**32 for n in host.values()):return None
    return deepcopy(value)


def checked_fault(value):
    if value is None:return None
    if (not isinstance(value,dict) or set(value)!={'schema','reason','observed_monotonic_s','observed_at_ms',
            'elapsed_s','current_work','previous_work','motion_epoch','task_id'}
            or value['schema']!='fleet-first-fault-1.0'
            or value['reason'] not in {'ISAAC_UPDATE_STALLED','ISAAC_TRANSPORT_STALE'}):return None
    for key in ('observed_monotonic_s','observed_at_ms','elapsed_s'):
        n=value[key]
        if type(n) not in (int,float) or not math.isfinite(n) or n<0:return None
    for key in ('motion_epoch','task_id'):
        if value[key] is not None and (not isinstance(value[key],str) or len(value[key])>100):return None
    if checked_work(value['current_work']) is None:return None
    if value['previous_work'] is not None and checked_work(value['previous_work']) is None:return None
    if len(json.dumps(value,allow_nan=False))>4096:return None
    return deepcopy(value)
