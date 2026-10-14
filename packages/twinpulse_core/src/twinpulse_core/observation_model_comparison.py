# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fixed-transform, multiframe photo-model diagnostics; never calibration.

Search seeds come from independent saved scans, not a prescribed route or old
pose. All usable playback keyframes evaluate each SAME transform. No room
editing, point trimming to convenient inliers, SLAM or movement authority.
"""
import math
from .room_localization import RoomMatcher, compose, inverse, scene_outline, segment_distance


def compare_observation_model(observation, objects, scan_height_m, *, matcher_factory=RoomMatcher):
    if observation.get('coordinate_frame') != 'SESSION_START_ODOM_LOCAL_NOT_ROOM_OR_MAP':
        raise ValueError('COMPARISON_OBSERVATION_FRAME_REQUIRED')
    if type(scan_height_m) not in (int, float) or not math.isfinite(scan_height_m) or not 0 < scan_height_m < 2:
        raise ValueError('COMPARISON_SENSOR_HEIGHT_INVALID')
    keys = observation['keyframes']
    if not 1 <= len(keys) <= 64 or len(objects) > 64:
        raise ValueError('COMPARISON_FRAME_OR_OBJECT_BUDGET')
    if any(len(k['points']) > 160 or len(k['sensor_pose']) != 3 or
           not all(math.isfinite(v) for v in k['sensor_pose']) or
           any(len(p) != 2 or not all(math.isfinite(v) and abs(v) <= 30 for v in p) for p in k['points']) for k in keys):
        raise ValueError('COMPARISON_POINT_BUDGET_OR_VALUE')
    outline = scene_outline(objects, scan_height_m)
    section = []
    owners = []
    for obj in objects:
        if obj['kind'] == 'floor': continue
        p, d = obj['transform']['position_m'], obj['shape']['dimensions_m']
        crosses = p[2]-d[2]/2 <= scan_height_m <= p[2]+d[2]/2
        item = {'object_id':obj['id'], 'kind':obj['kind'], 'vertical_extent_m':[p[2]-d[2]/2,p[2]+d[2]/2],
                'intersects_nominal_scan_plane':crosses,
                'sensor_section_basis':'AUTHORED_FULL_BOX_NOT_MEASURED_SURFACE',
                'review_priority':'FURNITURE_LOWER_SECTION_UNKNOWN' if obj['kind'] not in {'wall'} else 'PHOTO_WALL_DIMENSIONS_UNKNOWN'}
        section.append(item)
        if crosses: owners.extend([obj['id']]*4)
    matcher = matcher_factory(outline)
    valid = [k for k in keys if 24 <= len(k['points']) <= 160]
    seeds = []; searched = []
    chosen = sorted({round(i*(len(valid)-1)/max(1,min(4,len(valid))-1)) for i in range(min(4,len(valid)))})
    for index in chosen:
        key = valid[index]
        local = [compose(inverse(key['sensor_pose']), [*p,0])[:2] for p in key['points']]
        result = matcher.match(local)
        searched.append({'frame':key['frame'], 'status':result['status']})
        alternatives = result.get('alternatives', []) or ([result] if result.get('pose') else [])
        for alternative in alternatives[:4]:
            transform = compose(alternative['pose'], inverse(key['sensor_pose']))
            if any(math.dist(transform[:2],s['transform'][:2]) < .1 and
                   abs(math.atan2(math.sin(transform[2]-s['transform'][2]),math.cos(transform[2]-s['transform'][2]))) < .1 for s in seeds):
                continue
            seeds.append({'seed_frame':key['frame'], 'transform':transform})
    ranked = []
    for seed in seeds:
        rows = []; weighted = 0; hits = 0; supported = 0
        for key in valid:
            sensor = compose(seed['transform'], key['sensor_pose'])
            local = [compose(inverse(key['sensor_pose']), [*p,0])[:2] for p in key['points']]
            error, fraction = matcher.score(local, sensor)
            possible = matcher.possible(sensor)
            support = error <= .12 and fraction >= .70 and possible
            supported += support; weighted += error*len(local); hits += len(local)
            rows.append({'frame':key['frame'], 'elapsed_s':key['elapsed_s'], 'capped_mean_outline_error_m':error,
                         'within_15cm_fraction':fraction, 'sensor_pose_inside_model_open_area':possible,
                         'supports_same_transform':support})
        ranked.append({**seed, 'weighted_capped_mean_error_m':weighted/hits,
                       'supported_frames':supported, 'evaluated_frames':len(rows), 'frames':rows})
    ranked.sort(key=lambda s:s['weighted_capped_mean_error_m'])
    best = ranked[0] if ranked else None
    # Nearest authored surface labels are diagnostics, NOT object recognition.
    attribution = {s['object_id']:{'object_id':s['object_id'],'nearest_returns':0,'beyond_15cm_returns':0} for s in section}
    overlays = []
    if best:
        sampled = sorted({round(i*(len(valid)-1)/max(1,min(16,len(valid))-1)) for i in range(min(16,len(valid)))})
        for index in sampled:
            key = valid[index]; cloud = [compose(best['transform'],[*p,0])[:2] for p in key['points']]
            for point in cloud:
                distance, owner = min((segment_distance(point,s),owners[i]) for i,s in enumerate(outline['segments']))
                attribution[owner]['nearest_returns'] += 1
                attribution[owner]['beyond_15cm_returns'] += distance > .15
            overlays.append({'frame':key['frame'],'elapsed_s':key['elapsed_s'],'points':cloud,
                             'sensor_pose':compose(best['transform'],key['sensor_pose'])})
    return {'schema':'observation-photo-model-comparison-1.0',
            'status':'NO_SEARCH_HYPOTHESIS' if best is None else 'DIAGNOSTIC_SUPPORT_ONLY' if best['supported_frames'] == len(valid) else 'MODEL_OR_ODOM_INCONSISTENT',
            'scan_height_m_nominal':scan_height_m, 'outline':outline, 'sensor_sections':section,
            'searched_frames':searched,'evaluated_keyframes':len(valid), 'skipped_sparse_keyframes':len(keys)-len(valid),
            'best_diagnostic_hypothesis':best, 'alternatives':[dict(s,frames=None) for s in ranked[1:4]],
            'overlays':overlays, 'nearest_surface_diagnostics':list(attribution.values()),
            'surface_attribution_basis':'NEAREST_AUTHORED_SURFACE_NOT_OBJECT_IDENTITY',
            'score_basis':'ALL_SAMPLED_RETURNS_500MM_CAP_60MM_DISTANCE_FIELD_NOT_POSE_ERROR',
            'limitations':['PHOTO_BOX_SECTION_NOT_MEASURED','DECLARED_TIMING_UNVERIFIED','NOMINAL_MOUNT_NOT_AS_BUILT',
                           'ODOM_DRIFT_OR_EXTERIOR_RETURNS_NOT_SEPARATED','BOUNDED_SEED_SEARCH_NOT_GLOBAL_MULTIFRAME_OPTIMUM'],
            'geometry_changed':False,'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False}
