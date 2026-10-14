# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded offline navigation language, not an LLM or physical localization.

Targets refer to current scene IDs. Furniture targets use reachable exterior
approaches; a route is only a candidate on the approximate SIM geometry.
"""
import math
import re

from .site_simulation import geometry, make_plan, xy
from .bounded_grid_plan import NoBoundedPath


_PATH_REJECTIONS = frozenset({
    'GRID_BUDGET_EXCEEDED', 'SEGMENT_CHECK_BUDGET_EXCEEDED',
    'START_OR_GOAL_BLOCKED', 'REVIEWED_ROUTE_BLOCKED', 'SNAPPED_ENDPOINT_BLOCKED',
    'SEARCH_BUDGET_EXCEEDED', 'NO_PATH', 'GRID_EDGE_BLOCKED', 'WAYPOINT_BUDGET_EXCEEDED',
})
_POINT_REJECTIONS = frozenset({'SIM_GOAL_TOO_CLOSE', 'GOAL_PREVIEW_GOAL_TOO_CLOSE',
                              'GOAL_PREVIEW_OUTSIDE_ROOM'})


class GoalApproachError(ValueError):
    """No accepted bounded candidate, not a global infeasibility proof."""
    def __init__(self, diagnostic):
        super().__init__('SIM_TARGET_NO_REACHABLE_APPROACH')
        self.goal_diagnostic = diagnostic


def preview_review(scene, inventory):
    """Choose an illustrative SIM spawn and short route, never a physical pose.

    Search the complete fixed, finite candidate lattice. Every candidate uses the same
    footprint/path checks as explicit goals. No free corridor means rejection,
    not a guessed origin or an unchecked motion.
    """
    bounds, boxes, discs, _ = geometry(scene)
    xmin, xmax, ymin, ymax = bounds
    starts = [(xmin+(xmax-xmin)*i/10, ymin+(ymax-ymin)*j/10)
              for i in range(1, 10) for j in range(1, 10)]
    center = ((xmin+xmax)/2, (ymin+ymax)/2)
    starts.sort(key=lambda p: (math.dist(p, center), p))
    distances = (.4, .25)
    directions = ((0, 1), (1, 0), (0, -1), (-1, 0))
    candidate_budget = len(starts)*len(distances)*len(directions)
    attempts = 0
    path_error = None
    for start in starts:
        for distance in distances:
            for dx, dy in directions:
                attempts += 1
                if attempts > candidate_budget:
                    if path_error == 'GRID_BUDGET_EXCEEDED':
                        raise NoBoundedPath(path_error)
                    raise ValueError('SIM_PREVIEW_SEARCH_BUDGET_EXCEEDED')
                goal = (start[0]+dx*distance, start[1]+dy*distance)
                try:
                    plan = make_plan(scene, start, goal, inventory, yaw_rad=math.atan2(dy, dx))
                except NoBoundedPath as error:
                    if str(error) == 'GRID_BUDGET_EXCEEDED':
                        path_error = str(error)
                    continue
                return {'plan': plan, 'target': None, 'choices': [],
                        'drawing': {'bounds': list(bounds), 'boxes': [list(b) for b in boxes],
                                    'discs': [list(d) for d in discs]}}
    if path_error:
        raise NoBoundedPath(path_error)
    raise ValueError('SIM_PREVIEW_NO_REACHABLE_ROUTE')


def is_navigation_request(text):
    return bool(re.match(r'^(?:please\s+)?(?:go\b|navigate\b|drive\b|move\s+(?:to|toward|the robot|burger)\b|(?:show|plan)\s+(?:a\s+|the\s+)?route\b)', text.strip(), re.I)
                or re.search(r'(?:가줘|이동해|경로.*보여)', text))


def coordinates(text):
    # Both axes, in order; malformed/duplicate axes are never partially accepted.
    values = re.findall(r'\b([xy])\s*=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))(?=\s|[,;)]|$)', text, re.I)
    axes = re.findall(r'\b([xy])\s*=', text, re.I)
    if not axes:
        return None, None
    if len(values) != len(axes) or [a.lower() for a, _ in values] not in (['x', 'y'], ['x', 'y', 'x', 'y']):
        raise ValueError('SIM_GOAL_COORDINATES_REQUIRE_X_Y_PAIRS')
    points = [list(xy([float(values[i][1]), float(values[i+1][1])])) for i in range(0, len(values), 2)]
    if len(points) == 2:
        if not re.search(r'\bfrom\b', text, re.I) or not re.search(r'\bto\b', text, re.I):
            raise ValueError('SIM_GOAL_USE_FROM_X_Y_TO_X_Y')
        return points[0], points[1]
    if re.search(r'\bfrom\b', text, re.I):
        if not re.search(r'\bto\b', text, re.I):
            raise ValueError('SIM_GOAL_USE_FROM_X_Y_TO_OBJECT')
        return points[0], None
    return None, points[0]


def scene_targets(scene, furniture=None):
    groups = {}
    furniture = furniture or {}
    for obj in scene.objects:
        if obj.kind in {'floor', 'wall'} or not obj.collision:
            continue
        key = obj.id if obj.id in furniture else next((key for key in sorted(furniture, key=len, reverse=True) if obj.id.startswith(key + '_')), obj.id)
        group = groups.setdefault(key, {'id': key, 'label': furniture.get(key, key).replace('_', ' '), 'object_ids': [], 'bounds': [math.inf, -math.inf, math.inf, -math.inf]})
        x, y = obj.transform.position_m[:2]
        if obj.shape.type == 'box':
            dx, dy = obj.shape.dimensions_m[:2]
            a = math.radians(obj.transform.rotation_rpy_deg[2])
            hx, hy = (abs(math.cos(a))*dx+abs(math.sin(a))*dy)/2, (abs(math.sin(a))*dx+abs(math.cos(a))*dy)/2
        else:
            hx = hy = obj.shape.dimensions_m[0]
        b = group['bounds']
        group['bounds'] = [min(b[0], x-hx), max(b[1], x+hx), min(b[2], y-hy), max(b[3], y+hy)]
        group['object_ids'].append(obj.id)
    return list(groups.values())


def target_label_matches(label, text):
    # A library type such as dining_table/storage_shelf is also addressable
    # by its head noun. Word boundaries avoid table matching tabletop/stable;
    # all matching current targets remain choices, never a nearest guess.
    label=label.replace('_',' ').strip()
    terms={label,label.rsplit(' ',1)[-1]}
    # The reusable storage recipe serves cabinets and open shelving. Keep all
    # such matches ambiguous; this is not inferred furniture identity/quality.
    if label == 'storage':
        terms.update({'cabinet','shelf','bookshelf'})
    aliases={'bed':'침대','chair':'의자','desk':'책상','wardrobe':'옷장','sofa':'소파',
             'table':'테이블','shelf':'선반','bookshelf':'책장','box':'상자','pallet':'팔레트'}
    return any(re.search(r'(?<![\w])'+re.escape(term)+r'(?![\w])',text,re.I)
               or aliases.get(term,'\0') in text for term in terms if term)


def _approach_envelope(target, targets, placement_contract):
    """Approach the selected object's checked support assembly keepout.

    This does not retarget the parent, infer a relationship from names, or
    remove any collision proxy. Only the saved, checked placement sidecar may
    expand the exterior candidate envelope; legacy targets stay unchanged.
    """
    bounds = list(target['bounds']); parents = []; object_ids = list(target['object_ids'])
    if placement_contract is None:
        return bounds, parents, object_ids
    from .photo_placement import checked_placement_contract
    contract = checked_placement_contract(placement_contract)
    relations = {row['id']: row for row in contract['relations']}
    groups = {row['id']: row for row in targets}
    assembly = {target['id']}
    row = relations.get(target['id'])
    while row and row['relation'] in {'surface', 'drape'}:
        parent_id = row['parent_id']; parent = groups.get(parent_id)
        if parent is None:
            raise ValueError('SIM_TARGET_SUPPORT_PARENT_NOT_IN_CURRENT_SCENE')
        parents.append(parent_id); object_ids.extend(parent['object_ids'])
        assembly.add(parent_id)
        other = parent['bounds']
        bounds = [min(bounds[0], other[0]), max(bounds[1], other[1]),
                  min(bounds[2], other[2]), max(bounds[3], other[3])]
        row = relations.get(parent_id)
    # A floor-standing parent also owns the actual collision/keepout of its
    # typed supported descendants. Include rotated scene bounds, not a guessed
    # symmetric footprint or a name-prefix relationship. Noncolliding visual
    # parts add no geometry, and all original scene collision proxies remain.
    for _ in range(len(relations)):
        descendants = {identity for identity, item in relations.items()
            if item['relation'] in {'surface', 'drape'} and item['parent_id'] in assembly}
        additions = descendants - assembly
        if not additions:break
        assembly.update(additions)
        for identity in sorted(additions):
            child = groups.get(identity)
            if child is None:continue
            other = child['bounds']; object_ids.extend(child['object_ids'])
            bounds = [min(bounds[0], other[0]), max(bounds[1], other[1]),
                      min(bounds[2], other[2]), max(bounds[3], other[3])]
    return bounds, parents, list(dict.fromkeys(object_ids))


def goal_review(scene, text, start, inventory, *, yaw=0., furniture=None, selection=None,
                planner=None, approach_margin=.30, planner_context=None, placement_contract=None):
    explicit_start, explicit_goal = coordinates(text)
    start = xy(start if start is not None else explicit_start) if start is not None or explicit_start is not None else None
    if start is None:
        raise ValueError('SIM_START_REQUIRED: provide from x=... y=... to x=... y=...; no current simulated pose or saved placement exists')
    # A registered current-observation planner can reuse semantic resolution,
    # without inheriting the SIM footprint, start or execution authority.
    default_planner = planner is None
    planner = planner or (lambda point: make_plan(scene, start, point, inventory, yaw_rad=yaw))
    if type(approach_margin) not in (int,float) or not math.isfinite(approach_margin) or not .30<=approach_margin<=1.1:
        raise ValueError('TARGET_APPROACH_MARGIN_INVALID')
    targets = scene_targets(scene, furniture)
    bounds, boxes, discs, _ = geometry(scene)
    drawing = {'bounds': list(bounds), 'boxes': [list(b) for b in boxes], 'discs': [list(d) for d in discs]}
    if explicit_goal is not None:
        if selection is not None:
            raise ValueError('SIM_GOAL_SELECTION_NOT_APPLICABLE')
        return {'plan': planner(explicit_goal), 'target': None, 'choices': [], 'drawing': drawing}
    named = [t for t in targets if re.search(r'(?<![\w])'+re.escape(t['id'])+r'(?![\w])', text, re.I)]
    labelled = [t for t in targets if target_label_matches(t['label'],text)]
    # A relation suffix in an ID (box_on_pallet) is not that object's kind.
    # Use ID head-noun fallback only when no current semantic label matches.
    id_labelled = [] if labelled else [t for t in targets if target_label_matches(t['id'],text)]
    # A generic kind which happens to equal one ID is still ambiguous. An
    # explicit id=... or a distinguishing full ID selects exactly that object.
    exact_id = [t for t in named if re.search(r'\bid\s*=\s*'+re.escape(t['id'])+r'(?![\w])', text, re.I)]
    matches = exact_id or (named if any(t['id'].replace('_',' ') != t['label'] for t in named) else labelled or id_labelled or named)
    if selection:
        matches = [t for t in matches if t['id'] == selection]
    if not matches:
        raise ValueError('SIM_TARGET_NOT_FOUND: specify a saved object ID or x=... y=...')
    if len(matches) > 1:
        if len(matches) > 32:
            raise ValueError('SIM_TARGET_CHOICE_BUDGET_EXCEEDED')
        return {'plan': None, 'target': None, 'choices': matches, 'drawing': drawing}
    target = matches[0]
    envelope, support_parents, approach_objects = _approach_envelope(target, targets, placement_contract)
    xmin, xmax, ymin, ymax = envelope
    # Sixteen bounded exterior candidates, with clearance beyond the .22m planner footprint.
    points = []
    for fraction in (.15, .38, .62, .85):
        points.extend([(xmin-approach_margin, ymin+(ymax-ymin)*fraction), (xmax+approach_margin, ymin+(ymax-ymin)*fraction),
                       (xmin+(xmax-xmin)*fraction, ymin-approach_margin), (xmin+(xmax-xmin)*fraction, ymax+approach_margin)])
    diagnostic = dict(schema_version='goal-approach-diagnostic-1.0',
        scene_revision=scene.revision, start=list(start), yaw_rad=yaw,
        target_id=target['id'], target_object_ids=list(target['object_ids']),
        approach_bounds_xy_m=envelope, support_parent_ids=support_parents,
        approach_object_ids=approach_objects,
        approach_margin_m=approach_margin, candidate_limit=len(points),
        scope='BOUNDED_EXTERIOR_CANDIDATES_NOT_GLOBAL_INFEASIBILITY_PROOF',
        planner_context=(dict(mode='SIM', resolution_m=.10, clearance_m=.22)
                         if default_planner else dict(planner_context or {'mode':'CUSTOM_UNDECLARED'})),
        attempts=[], reason_counts={}, physical_authority=False)
    feasible = []
    for point in points:
        try:
            plan = planner(point)
        except ValueError as error:
            code = str(error)
            bounded_rejection = ((isinstance(error, NoBoundedPath) and code in _PATH_REJECTIONS)
                                 or (not isinstance(error, NoBoundedPath) and code in _POINT_REJECTIONS))
            diagnostic['attempts'].append(dict(point=list(point), accepted=False,
                code=code[:160], category='BOUNDED_CANDIDATE_REJECTION' if bounded_rejection
                else 'PLANNER_INPUT_OR_INTERNAL_ERROR'))
            diagnostic['reason_counts'][code[:160]] = diagnostic['reason_counts'].get(code[:160],0)+1
            if not bounded_rejection:
                diagnostic['termination_code']='PLANNER_INPUT_OR_INTERNAL_ERROR'
                error.goal_diagnostic=diagnostic
                raise
            continue
        length = sum(math.dist(a, b) for a, b in zip([start]+plan['route'], plan['route']))
        diagnostic['attempts'].append(dict(point=list(point), accepted=True, route_length_m=length))
        feasible.append((length, tuple(point), plan))
    if not feasible:
        diagnostic['termination_code']=('PLANNER_BUDGET_EXHAUSTED' if any(
            code.endswith('BUDGET_EXCEEDED') for code in diagnostic['reason_counts'])
            else 'NO_ACCEPTED_EXTERIOR_CANDIDATE')
        raise GoalApproachError(diagnostic)
    selected = min(feasible, key=lambda item: (item[0], item[1]))
    diagnostic.update(termination_code='FOUND', accepted_count=len(feasible), selected_point=list(selected[1]))
    return {'plan': selected[2], 'target': target, 'choices': [], 'drawing': drawing,
            'approach_diagnostic': diagnostic}
