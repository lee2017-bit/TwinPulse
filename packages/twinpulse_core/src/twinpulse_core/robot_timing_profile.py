# SPDX-License-Identifier: Apache-2.0
"""Per-robot engineering timing policy. Measurements are not a safety certificate.

One immutable session snapshot, original clocks and independent failure reasons.
No device, transport, file, or model execution is performed by this module.
"""
from copy import deepcopy
import hashlib
import json
import math

SCHEMA = 'robot-timing-profile-1.0'
# Milliseconds throughout the persisted/wire contract. Bounds are engineering
# configuration bounds, not measured braking limits or manufacturer guarantees.
FIELDS = {
    'input_ttl_ms': (100, 1000, 350, 'Original input lifetime'),
    'odom_interval_ms': (50, 1000, 300, 'Odometry source sample interval'),
    'odom_source_ms': (100, 1500, 350, 'Odometry source freshness'),
    'scan_source_ms': (100, 1500, 350, 'ROS scan source freshness'),
    'navigation_snapshot_ms': (50, 1000, 200, 'Navigation snapshot age'),
    'odom_scan_skew_ms': (10, 300, 50, 'Odometry / ROS scan time skew'),
    'sensor_source_ms': (50, 1000, 200, 'ROS SensorState source age'),
    'sensor_receipt_ms': (50, 1000, 200, 'ROS SensorState receipt age'),
    'guard_receipt_ms': (50, 1000, 200, 'Final guard status receipt age'),
    'wheel_interval_ms': (50, 1000, 200, 'Wheel observation sample interval'),
    'output_timeout_ms': (150, 2000, 400, 'Robot final output cutoff'),
    'operator_presence_ms': (200, 5000, 500, 'Operator presence lifetime'),
    'native_receipt_ms': (100, 1000, 350, 'Native LiDAR receipt age'),
    'tracking_result_ms': (100, 2000, 600, 'Tracking result age'),
    'icp_compute_ms': (20, 500, 80, 'Tracking computation budget'),
    'tracking_delivery_ms': (100, 2000, 500, 'Tracking process delivery wait'),
    'ros_service_ms': (100, 5000, 500, 'ROS service response wait'),
    'input_renewal_ms': (25, 200, 100, 'UI input renewal target'),
    'input_window_ms': (20, 100, 50, 'Robot input window target'),
}
DEFAULTS = {k: v[2] for k, v in FIELDS.items()}
# A sensor's age and its inter-sample gap are deliberately not interchangeable.
METRICS = {
    'input_ttl_ms': ('input_pressure_ms', 'input_age_ms', 'input_window_interval_ms', 'watch_roundtrip_ms'),
    'output_timeout_ms': ('output_pressure_ms',),
    'odom_interval_ms': ('odom_interval_ms',),
    'odom_source_ms': ('odom_source_ms',),
    'scan_source_ms': ('scan_source_ms',),
    'sensor_source_ms': ('sensor_source_ms',),
    'sensor_receipt_ms': ('sensor_receipt_ms',),
    'guard_receipt_ms': ('guard_receipt_ms',),
    'wheel_interval_ms': ('wheel_interval_ms',),
    'native_receipt_ms': ('native_receipt_ms', 'native_interval_ms'),
    'tracking_result_ms': ('tracking_result_ms',),
    'icp_compute_ms': ('icp_compute_ms',),
    'tracking_delivery_ms': ('tracking_delivery_ms',),
    'ros_service_ms': ('ros_service_ms',),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def checked_values(value):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError('TIMING_VALUES_SHAPE')
    for key, (low, high, _, _) in FIELDS.items():
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError('TIMING_RANGE_' + key.upper())
    if value['input_ttl_ms'] < 2 * max(value['input_renewal_ms'], value['input_window_ms']):
        raise ValueError('TIMING_INPUT_RENEWAL_MARGIN')
    # Final guard must leave a separate delivery/scheduling margin. This is not
    # a fresh timeout at receipt; the robot subtracts original command age.
    margin = max(50, value['input_window_ms'])
    if value['output_timeout_ms'] < value['input_ttl_ms'] + margin:
        raise ValueError('TIMING_OUTPUT_MARGIN')
    if value['operator_presence_ms'] < value['input_ttl_ms'] + value['input_renewal_ms']:
        raise ValueError('TIMING_PRESENCE_MARGIN')
    if value['odom_source_ms']<value['odom_interval_ms']+50:
        raise ValueError('TIMING_ODOM_FRESHNESS_MARGIN')
    if value['tracking_delivery_ms']<value['icp_compute_ms']+value['input_window_ms']:
        raise ValueError('TIMING_TRACKING_DELIVERY_MARGIN')
    return deepcopy(value)


def profile(robot_id, binding_sha256, *, values=None, mode='unmeasured', evidence=None):
    if mode not in {'unmeasured', 'measured_default', 'custom'}:
        raise ValueError('TIMING_MODE')
    result = dict(schema_version=SCHEMA, robot_id=robot_id, binding_sha256=binding_sha256,
        mode=mode, values=checked_values(DEFAULTS if values is None else values),
        evidence=deepcopy(evidence), adaptive=False,
        qualification='ENGINEERING_ONLY_NOT_BRAKING_OR_DRIVING_QUALIFICATION')
    return checked_profile(result, robot_id=robot_id, binding_sha256=binding_sha256)


def checked_profile(value, *, robot_id=None, binding_sha256=None):
    import re
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'robot_id', 'binding_sha256',
            'mode', 'values', 'evidence', 'adaptive', 'qualification'} or value['schema_version'] != SCHEMA
            or value['mode'] not in {'unmeasured', 'measured_default', 'custom'}
            or value['adaptive'] is not False
            or value['qualification'] != 'ENGINEERING_ONLY_NOT_BRAKING_OR_DRIVING_QUALIFICATION'
            or not isinstance(value['robot_id'], str) or not re.fullmatch('[a-f0-9]{32}', value['robot_id'])
            or not isinstance(value['binding_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['binding_sha256'])):
        raise ValueError('TIMING_PROFILE_SHAPE')
    if robot_id is not None and value['robot_id'] != robot_id: raise ValueError('TIMING_ROBOT_CHANGED')
    if binding_sha256 is not None and value['binding_sha256'] != binding_sha256: raise ValueError('TIMING_BINDING_CHANGED')
    checked_values(value['values'])
    if value['evidence'] is not None:
        e=value['evidence']
        if (not isinstance(e, dict) or set(e) != {'operation_id', 'measurement_sha256', 'algorithm', 'coverage'}
                or not isinstance(e['operation_id'], str) or not re.fullmatch('[a-f0-9]{32}', e['operation_id'])
                or not isinstance(e['measurement_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', e['measurement_sha256'])
                or e['algorithm'] != 'observed-tail-margin-1.0'
                or e['coverage'] not in {'PROVISIONAL', 'OBSERVED_LOADS'}):
            raise ValueError('TIMING_EVIDENCE_SHAPE')
    if value['mode'] == 'measured_default' and value['evidence'] is None:
        raise ValueError('TIMING_MEASUREMENT_REQUIRED')
    return deepcopy(value)


class TimingAccumulator:
    """O(1) ingestion; bounded 5ms histograms, no sorting/serialization in callbacks.

    Clock faults are counted, not converted to zero or discarded as 'outliers'.
    Histogram percentiles are descriptive upper-bin edges, never tail guarantees.
    """
    def __init__(self):
        self.groups={}; self.first=None; self.last=None

    def observe(self, name, ms, at, load='base'):
        if name not in {*METRICS, 'input_age_ms', 'input_pressure_ms', 'input_window_interval_ms', 'output_pressure_ms', 'native_interval_ms','watch_roundtrip_ms'}: return
        if load not in {'base', 'lidar', 'tracking_recording'}: raise ValueError('TIMING_LOAD')
        if type(at) not in (int, float) or not math.isfinite(at): raise ValueError('TIMING_CLOCK')
        if self.first is None: self.first=at
        self.last=max(at, self.last if self.last is not None else at)
        key=load+':'+name
        r=self.groups.setdefault(key,dict(n=0, invalid=0, mean_ms=0., m2=0., maximum_ms=0., bins={},first_s=at,last_s=at,observed_s=0.))
        delta=at-r['last_s']
        if 0<=delta<=1.:r['observed_s']+=delta
        r['last_s']=max(at,r['last_s'])
        if type(ms) not in (int, float) or not math.isfinite(ms) or ms<0 or ms>10000:
            r['invalid']+=1; return
        r['n']+=1; d=ms-r['mean_ms']; r['mean_ms']+=d/r['n']; r['m2']+=d*(ms-r['mean_ms'])
        r['maximum_ms']=max(r['maximum_ms'], ms)
        b=int(math.ceil(ms/5))*5; r['bins'][b]=r['bins'].get(b,0)+1

    def snapshot(self):
        rows={}
        for key,r in self.groups.items():
            s={k:r[k] for k in ('n','invalid','mean_ms','maximum_ms')}
            s['duration_s']=r['observed_s']
            s['span_s']=max(0.,r['last_s']-r['first_s'])
            s['sample_std_ms']=math.sqrt(max(0.,r['m2'])/(r['n']-1)) if r['n']>1 else None
            target=math.ceil(r['n']*.99); cumulative=0; s['p99_upper_ms']=None
            for b,n in sorted(r['bins'].items()):
                cumulative+=n
                if cumulative>=target: s['p99_upper_ms']=b; break
            rows[key]=s
        return dict(schema_version='robot-timing-measurement-1.0', duration_s=max(0.,(self.last or 0)-(self.first or 0)),
            metrics=rows, histogram_resolution_ms=5, independent_samples=False,
            scope='OBSERVED_SOFTWARE_TIMING_NOT_BRAKING_OR_NETWORK_RTT')


def checked_measurement(measurement):
    """Validate observations without calculating a new parameter recommendation."""
    if (not isinstance(measurement, dict) or measurement.get('schema_version')!='robot-timing-measurement-1.0'
            or not isinstance(measurement.get('metrics'), dict) or not 1<=len(measurement['metrics'])<=100
            or type(measurement.get('duration_s')) not in (int,float) or not math.isfinite(measurement['duration_s'])
            or not 0<=measurement['duration_s']<=86400):
        raise ValueError('TIMING_MEASUREMENT_SHAPE')
    if len(json.dumps(measurement,allow_nan=False).encode())>65536:raise ValueError('TIMING_MEASUREMENT_SIZE')
    metrics={name for names in METRICS.values() for name in names}
    for key,row in measurement['metrics'].items():
        load,_,name=key.partition(':')
        if load not in {'base','lidar','tracking_recording'} or name not in metrics:continue
        if (not isinstance(row,dict) or type(row.get('n')) is not int or row['n']<0
                or type(row.get('invalid')) is not int or row['invalid']<0):raise ValueError('TIMING_METRIC_SHAPE')
        if not row['n']:continue
        for member in ('maximum_ms','mean_ms','p99_upper_ms'):
            if type(row.get(member)) not in (int,float) or not math.isfinite(row[member]) or not 0<=row[member]<=10000:
                raise ValueError('TIMING_METRIC_VALUE')
    return deepcopy(measurement)


def recommendation(measurement, robot_id, binding_sha256, operation_id):
    measurement=checked_measurement(measurement)
    values=deepcopy(DEFAULTS); reasons={}; capped=[]; invalid_metrics=[]; loads=set()
    for field,metrics in METRICS.items():
        candidates=[]; rows=[]
        for key,row in measurement['metrics'].items():
            load,_,name=key.partition(':')
            if load not in {'base','lidar','tracking_recording'} or name not in metrics:continue
            if (not isinstance(row,dict) or type(row.get('n')) is not int or row['n']<0
                    or type(row.get('invalid')) is not int or row['invalid']<0):raise ValueError('TIMING_METRIC_SHAPE')
            if row['invalid']:invalid_metrics.append(key)
            if not row['n']:continue
            for member in ('maximum_ms','mean_ms','p99_upper_ms'):
                if type(row.get(member)) not in (int,float) or not math.isfinite(row[member]) or not 0<=row[member]<=10000:
                    raise ValueError('TIMING_METRIC_VALUE')
            tail=max(row['maximum_ms'],row['p99_upper_ms'])
            # Explicit engineering headroom, NOT mean+sigma/99% confidence.
            candidate=int(math.ceil((tail+max(25.,.25*tail))/25)*25)
            candidates.append(candidate); rows.append(dict(load=load,**deepcopy(row)))
            if row['n']>=200 and not row['invalid'] and row.get('duration_s',0)>=30:loads.add(load)
        if candidates:
            proposed=max(values[field],*candidates)
            if proposed>FIELDS[field][1]:capped.append(field)
            values[field]=min(proposed,FIELDS[field][1])
            reasons[field]=dict(formula='ceil25(max(observed_max,p99_bin_upper)+max(25ms,25%tail)); preset floor', samples=rows)
        else:reasons[field]=dict(reason='NOT_MEASURED_PRESET_RETAINED')
    values['output_timeout_ms']=max(values['output_timeout_ms'],values['input_ttl_ms']+max(100,values['input_window_ms']*2))
    values['operator_presence_ms']=max(values['operator_presence_ms'],values['input_ttl_ms']+values['input_renewal_ms']+50)
    values['odom_source_ms']=max(values['odom_source_ms'],values['odom_interval_ms']+50)
    values['tracking_delivery_ms']=max(values['tracking_delivery_ms'],values['icp_compute_ms']+values['input_window_ms'])
    coverage=('OBSERVED_LOADS' if loads=={'base','lidar','tracking_recording'}
        and measurement.get('duration_s',0)>=90 and not capped and not invalid_metrics else 'PROVISIONAL')
    evidence=dict(operation_id=operation_id,measurement_sha256=digest(measurement),algorithm='observed-tail-margin-1.0',coverage=coverage)
    return dict(profile=profile(robot_id,binding_sha256,values=values,mode='measured_default',evidence=evidence),
        reasons=reasons,capped_fields=capped,invalid_metrics=sorted(set(invalid_metrics)),coverage=coverage,
        warning='Descriptive observed tail plus engineering margin; not a false-stop probability or physical qualification.')


def values_of(value=None):
    return checked_values(DEFAULTS if value is None else value['values'] if 'values' in value else value)


def seconds(value, key):
    return value[key]/1000


def runtime_policy(value):
    """Never log legacy global defaults as the active per-instance policy."""
    v=values_of(value)
    names={'ros_receipt':'sensor_receipt_ms','ros_source':'sensor_source_ms','guard_receipt':'guard_receipt_ms',
        'original_input':'input_ttl_ms','odom_sample_interval':'odom_interval_ms','odom_source':'odom_source_ms',
        'scan_source':'scan_source_ms','wheel_sample_interval':'wheel_interval_ms','operator_presence':'operator_presence_ms',
        'native_receipt':'native_receipt_ms','icp_compute':'icp_compute_ms','tracking_result':'tracking_result_ms',
        'tracking_delivery':'tracking_delivery_ms','ros_service':'ros_service_ms','cpp_output_guard':'output_timeout_ms'}
    return dict(schema='robot-control-timing-2.0',revision='per-robot-profile-1.0',adaptive=False,
        basis='PINNED_CONFIGURED_VALUES_NOT_PHYSICAL_QUALIFICATION',values_ms=v,
        limits={name:dict(seconds=v[key]/1000,parameter=key) for name,key in names.items()})
