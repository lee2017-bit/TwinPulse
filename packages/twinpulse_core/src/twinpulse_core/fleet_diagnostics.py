# SPDX-License-Identifier: Apache-2.0
"""Bounded engine work/fault evidence, never control authority."""
from copy import deepcopy
import json
import math


def _checked_host(value):
    # Match UpdateProbe.finish and the engine-host envelope. Resource samples
    # describe the same APP.update; never substitute a later heartbeat's data.
    numbers={'app_update_s','previous_viewport_s','previous_tail_s','gc_pause_s',
        'thread_cpu_s','process_cpu_s','process_private_mib','process_working_set_mib',
        'available_ram_mib','page_fault_delta'}
    resources={'available_ram_mib','process_working_set_mib','process_private_mib'}
    if not isinstance(value,dict) or set(value)-numbers-{'before_resources'}:return False
    for key,n in value.items():
        if key=='before_resources':
            if not isinstance(n,dict) or set(n)-resources:return False
            if any(type(x) not in (int,float) or not 0<=x<=2**32 or not math.isfinite(x) for x in n.values()):return False
        elif type(n) not in (int,float) or not 0<=n<=2**32 or not math.isfinite(n):return False
    return True


def _checked_scan_diagnostic(value):
    if value is None:return True
    numbers={'sensor_pose_wall_s','sensor_pose_cpu_s','section_wall_s','section_cpu_s','height_key',
        'geometry_epoch','segments','triangles','prepared_monotonic_s','started_monotonic_s',
        'completed_monotonic_s','wall_s','cpu_s','captured_at_ms'}
    if not isinstance(value,dict) or set(value)-numbers-{'section_cache_hit','error','position_m'}:return False
    for key,n in value.items():
        if key in numbers:
            if type(n) not in (int,float) or not 0<=n<=2**53 or not math.isfinite(n):return False
            if key.endswith(('_wall_s','_cpu_s')) or key in {'wall_s','cpu_s'}:
                if n>86400:return False
        elif key=='section_cache_hit':
            if type(n) is not bool:return False
        elif key=='error':
            if n is not None and (not isinstance(n,str) or len(n)>120):return False
        elif key=='position_m':
            if not isinstance(n,list) or len(n)!=3 or any(type(x) not in (int,float) or not -1e6<=x<=1e6 or not math.isfinite(x) for x in n):return False
    return len(json.dumps(value,allow_nan=False))<=2048


def checked_work(value):
    required={'bounds_s','model_authoring_s','bounds_rebuilds'}
    optional={'scan_s','scan_error','update_s','navigation_s','host','scan_prepare_s','scan_prepare','scan_worker','scan_worker_worst'}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-required-optional:return None
    for key in required|{'scan_s','update_s','navigation_s','scan_prepare_s'}:
        if key not in value:continue
        n=value[key]
        if type(n) not in (int,float) or not 0<=n<=86400 or not math.isfinite(n):return None
    if type(value['bounds_rebuilds']) is not int:return None
    if value.get('scan_error') is not None and (not isinstance(value['scan_error'],str) or len(value['scan_error'])>160):return None
    host=value.get('host',{})
    if not _checked_host(host):return None
    if any(not _checked_scan_diagnostic(value.get(key)) for key in ('scan_prepare','scan_worker','scan_worker_worst')):return None
    return deepcopy(value)


def checked_fault(value):
    if value is None:return None
    if (not isinstance(value,dict) or set(value)!={'schema','reason','observed_monotonic_s','observed_at_ms',
            'elapsed_s','current_work','previous_work','motion_epoch','task_id'}
            or value['schema']!='fleet-first-fault-1.0'
            or not isinstance(value['reason'],str)
            or value['reason'] not in {'ISAAC_UPDATE_STALLED','ISAAC_TRANSPORT_STALE'}):return None
    for key in ('observed_monotonic_s','observed_at_ms','elapsed_s'):
        n=value[key]
        if type(n) not in (int,float) or not 0<=n<=2**53 or not math.isfinite(n):return None
    for key in ('motion_epoch','task_id'):
        if value[key] is not None and (not isinstance(value[key],str) or len(value[key])>100):return None
    if checked_work(value['current_work']) is None:return None
    if value['previous_work'] is not None and checked_work(value['previous_work']) is None:return None
    if len(json.dumps(value,allow_nan=False))>16384:return None
    return deepcopy(value)
