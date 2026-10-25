# SPDX-License-Identifier: Apache-2.0
"""Data-only robot task language. Models compose capabilities, never code.

These are host maxima, not model-adjustable safety settings. A valid proposal
is not execution authority, sensor evidence, or a certificate of room coverage.
"""
from copy import deepcopy
import math
import re

VERSION = 'robot-task-plan-1.0'
CAPABILITIES = ('observe', 'move_relative', 'navigate', 'survey', 'return_to_start', 'stop')
TARGETS = ('bed', 'chair', 'desk', 'sofa', 'table', 'wardrobe', 'storage', 'shelf')


def immediate_stop(text):
    value=text.strip().lower()
    return bool(re.search(r'^(?:please\s+)?(?:stop|cancel|abort|pause)\s+(?:the\s+)?(?:current\s+)?(?:task|mission|survey|exploration|robot)\b',value)
                or re.search(r'\b(?:stop|abort|pause)\s+(?:now|immediately)\b|즉시.*(?:정지|멈)|(?:탐색|수집|측정|작업|미션).*(?:중지|취소)(?:해줘|해|줘)?[.!?]*$',value))


def explicit_requirements(text):
    """Conservative omission vetoes, not a second planner or generated route.

    The model's prose cannot self-certify completion. Known explicit safety/
    return obligations must be present as executable capabilities. Ambiguous
    requests still need model clarification and human exact-plan review.
    """
    value=text.strip().lower();required=set()
    if re.search(r'돌아와|돌아오|복귀|왕복|\breturn\b|\bback\s+to\s+(?:the\s+)?start\b',value):required.add('return_to_start')
    if re.search(r'\b(?:survey|explore|inspect|patrol)\b|둘러|탐색|순찰|(?:room|방|공간).*(?:measure|측정|수집)|measure.*room',value):required.add('survey')
    if re.search(r'\bstop\b|정지|멈',value):required.add('stop')
    return required


def request_capabilities(text):
    """A survey is an adaptive capability, not permission to invent waypoints.

    Directional action phrases preserve requested compositions. A wall side,
    a total distance budget, or 'back to start' does not authorize extra moves.
    This constrains proposals; geometry/permission still belong to the host.
    """
    value=text.strip().lower()
    relative=bool(re.search(r'\b(?:forward|backward|backwards|reverse)\b|\b(?:turn|rotate)\s+(?:to\s+the\s+)?(?:left|right)\b|전진|후진|앞으로|뒤로|좌회전|우회전|(?:왼쪽|오른쪽)으로\s*(?:회전|돌)',value))
    return tuple(op for op in CAPABILITIES if op!='move_relative' or
                 'survey' not in explicit_requirements(value) or relative)


def without_in_place(value):
    """'in place'/'in-place' describes robot motion, not the scene verb 'place'."""
    return re.sub(r'\bin[\s-]+place\b', ' ', value)


def task_request(text,robot_kind=None):
    """Routing hint only; never interprets or authorizes a task.

    Keep geometry editing and simple emergency controls out of inference. The
    broad multi-action path deliberately precedes the old greedy unit parser.
    """
    value = text.strip().lower()
    if immediate_stop(value):return False
    if re.search(r'만들|생성|배치|옮겨|크기|\b(?:create|build|generate|place|resize|edit)\b', without_in_place(value)):
        return False
    if re.fullmatch(r'(?:정지|멈춰|stop|pause|all robots stop)[.!?]*', value):
        return False
    if (robot_kind=='physical' and re.search(r'\b(?:bed|chair|desk|sofa|table|wardrobe|storage|shelf)\b|침대|의자|책상|소파|식탁|수납|선반',value)
            and re.search(r'\b(?:go|navigate|approach|move)\b|가줘|가라|이동|접근',value)):return True
    return bool(re.search(r'둘러|탐색|돌아와|복귀|순찰|측정|수집|왕복|차례|반복|\b(?:survey|explore|inspect|patrol|collect|return|repeat)\b', value)
                or re.search(r'(?:하고|한\s*뒤|다음|후에|\bthen\b|\band\b).*(?:이동|전진|후진|회전|가줘|멈|돌아|move|forward|back|turn|go|stop)', value))


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def checked_plan(value,*,request_text=None):
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'mode', 'explanation', 'limits', 'steps'}
            or value['schema_version'] != VERSION or value['mode'] not in {'plan', 'clarify'}
            or not isinstance(value['explanation'], str) or not 1 <= len(value['explanation']) <= 800):
        raise ValueError('ROBOT_TASK_PLAN_SHAPE')
    limits = value['limits']
    if (not isinstance(limits, dict) or set(limits) != {'distance_m', 'duration_s', 'segments'}
            or not _number(limits['distance_m'], .1, 12) or not _number(limits['duration_s'], 5, 600)
            or type(limits['segments']) is not int or not 1 <= limits['segments'] <= 128):
        raise ValueError('ROBOT_TASK_PLAN_LIMITS')
    if not isinstance(value['steps'], list) or len(value['steps']) > 12:
        raise ValueError('ROBOT_TASK_PLAN_STEPS')
    if value['mode'] == 'clarify':
        if value['steps']:raise ValueError('ROBOT_TASK_CLARIFY_HAS_ACTIONS')
        return deepcopy(value)
    if not value['steps']:raise ValueError('ROBOT_TASK_EMPTY')
    explicit_distance = 0.
    for step in value['steps']:
        if not isinstance(step, dict) or step.get('op') not in CAPABILITIES:raise ValueError('ROBOT_TASK_CAPABILITY')
        op = step['op']
        fields = {'op', 'direction', 'amount'} if op == 'move_relative' else {'op', 'target_kind'} if op == 'navigate' else {'op'}
        if set(step) != fields:raise ValueError('ROBOT_TASK_STEP_FIELDS')
        if op == 'move_relative':
            direction = step['direction']
            if direction not in {'forward', 'backward', 'left', 'right'}:raise ValueError('ROBOT_TASK_DIRECTION')
            angular = direction in {'left', 'right'}
            if not _number(step['amount'], .01, 2*math.pi if angular else 2):raise ValueError('ROBOT_TASK_EXTENT')
            if not angular:explicit_distance += step['amount']
        if op == 'navigate' and step['target_kind'] not in TARGETS:raise ValueError('ROBOT_TASK_TARGET')
    if explicit_distance > limits['distance_m']:raise ValueError('ROBOT_TASK_DISTANCE_BUDGET')
    if request_text is not None:
        required=explicit_requirements(request_text);ops=[s['op'] for s in value['steps']]
        missing=required-set(ops)
        if missing:raise ValueError('ROBOT_TASK_REQUESTED_CAPABILITY_MISSING: '+','.join(sorted(missing)))
        if any(op not in request_capabilities(request_text) for op in ops):
            raise ValueError('ROBOT_TASK_SURVEY_FIXED_MOVES_NOT_REQUESTED')
        if 'return_to_start' in required:
            returning=max(i for i,op in enumerate(ops) if op=='return_to_start')
            if any(op in {'survey','navigate','move_relative'} for op in ops[returning+1:]):
                raise ValueError('ROBOT_TASK_REQUESTED_RETURN_NOT_FINAL')
        if 'stop' in required and ops[-1]!='stop':raise ValueError('ROBOT_TASK_REQUESTED_STOP_NOT_FINAL')
    return deepcopy(value)


def plan_schema(*,capabilities=CAPABILITIES):
    if not capabilities or any(op not in CAPABILITIES for op in capabilities):
        raise ValueError('ROBOT_TASK_SCHEMA_CAPABILITIES')
    steps = []
    for op in capabilities:
        props = {'op': {'const': op}}
        if op == 'move_relative':props.update(direction={'enum': ['forward', 'backward', 'left', 'right']}, amount={'type': 'number', 'minimum': .01, 'maximum': 2*math.pi})
        if op == 'navigate':props['target_kind'] = {'enum': list(TARGETS)}
        steps.append(dict(type='object', additionalProperties=False, properties=props, required=list(props)))
    limits = dict(distance_m=dict(type='number', minimum=.1, maximum=12), duration_s=dict(type='number', minimum=5, maximum=600), segments=dict(type='integer', minimum=1, maximum=128))
    props = dict(schema_version={'const': VERSION}, mode={'enum': ['plan', 'clarify']}, explanation=dict(type='string', minLength=1, maxLength=800),
                 limits=dict(type='object', additionalProperties=False, properties=limits, required=list(limits)),
                 steps=dict(type='array', maxItems=12, items={'anyOf': steps}))
    return dict(type='object', additionalProperties=False, properties=props, required=list(props))


def primitive_text(step):
    """Canonical host serialization, not execution of arbitrary model text."""
    if step['op'] == 'move_relative':
        return f"{step['direction']} {step['amount']:.9f} {'rad' if step['direction'] in {'left','right'} else 'm'}"
    if step['op'] == 'navigate':return 'Go to nearest '+step['target_kind']
    if step['op'] == 'stop':return 'stop'
    raise ValueError('ROBOT_TASK_NOT_PRIMITIVE')
