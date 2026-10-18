# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Independent, evaluator-only semantic/rubric scoring. No model calls.

Labels never enter journey packets or production repair feedback. Coordinates
are normalized ROOM XY, not image pixels or measured reconstruction accuracy.
Missing human/render evidence is NOT_EVALUATED, not a production-critic PASS.
"""
from copy import deepcopy
import math
from scripts.benchmark_protocol import canonical_sha, _digest

VERSION='independent-semantic-quality-1.0'
RUBRIC_FIELDS={'schema_version','entity_f1_min','hazard_recall_min','relation_accuracy_min',
               'match_distance_uv','relation_epsilon_uv','adjacent_distance_uv','size_relative_tolerance'}


def checked_rubric(value):
    if type(value) is not dict or set(value)!=RUBRIC_FIELDS or value['schema_version']!='benchmark-rubric-1.0':
        raise ValueError('BENCHMARK_RUBRIC_INVALID')
    for key in RUBRIC_FIELDS-{'schema_version'}:
        number=value[key]
        if type(number) not in (int,float) or not math.isfinite(number) or not 0<number<=1:
            raise ValueError('BENCHMARK_RUBRIC_RANGE_INVALID')
    return deepcopy(value)


def vector(value,length,*,positive=False,normalized=False):
    if type(value) is not list or len(value)!=length or any(type(n) not in (int,float)
            or not math.isfinite(n) or positive and n<=0 or normalized and abs(n)>.5 for n in value):
        raise ValueError('BENCHMARK_ANNOTATION_VECTOR_INVALID')


def checked_annotation(value,packet,rubric):
    fields={'schema_version','case_id','input_sha256','rubric_sha256','coordinate_frame',
            'coverage_complete','reviewers','entities','relations','room_size_m','room_size_authority'}
    if type(value) is not dict or set(value)!=fields or value['schema_version']!='benchmark-annotation-1.0':
        raise ValueError('BENCHMARK_ANNOTATION_INVALID')
    if (value['case_id']!=packet['case_id'] or value['input_sha256']!=canonical_sha(packet)
            or value['rubric_sha256']!=canonical_sha(rubric)):
        raise ValueError('BENCHMARK_ANNOTATION_BINDING_CHANGED')
    if value['coordinate_frame']!='room_xy_normalized_front_negative_y':
        raise ValueError('BENCHMARK_ANNOTATION_FRAME_UNSUPPORTED')
    if type(value['coverage_complete']) is not bool:raise ValueError('BENCHMARK_ANNOTATION_COVERAGE_INVALID')
    if value['room_size_authority'] not in ('unknown','explicit','measured','known_synthetic'):
        raise ValueError('BENCHMARK_SIZE_AUTHORITY_INVALID')
    if value['room_size_m'] is not None:vector(value['room_size_m'],2,positive=True)
    if (value['room_size_m'] is None)!=(value['room_size_authority']=='unknown'):
        raise ValueError('BENCHMARK_UNKNOWN_SIZE_MUST_NOT_BECOME_TRUTH')
    if (type(value['reviewers']) is not list or not 1<=len(value['reviewers'])<=10
            or any(type(r) is not str or not r.strip() for r in value['reviewers'])
            or len(set(value['reviewers']))!=len(value['reviewers'])):
        raise ValueError('BENCHMARK_HUMAN_REVIEWER_REQUIRED')
    if type(value['entities']) is not list or not 1<=len(value['entities'])<=64:
        raise ValueError('BENCHMARK_ANNOTATION_ENTITIES_INVALID')
    identities=set()
    for entity in value['entities']:
        if (type(entity) is not dict or set(entity)!={'label_id','kind','visibility','hazard',
                'centre_uv','size_m','size_authority','placement'} or type(entity['label_id']) is not str
                or not entity['label_id'] or entity['label_id'] in identities
                or type(entity['kind']) is not str or not entity['kind']
                or entity['visibility'] not in ('observable','occluded','unknown') or type(entity['hazard']) is not bool):
            raise ValueError('BENCHMARK_ANNOTATION_ENTITY_INVALID')
        identities.add(entity['label_id'])
        if entity['centre_uv'] is not None:vector(entity['centre_uv'],2,normalized=True)
        if entity['size_authority'] not in ('unknown','explicit','measured','known_synthetic'):
            raise ValueError('BENCHMARK_SIZE_AUTHORITY_INVALID')
        if entity['size_m'] is not None:vector(entity['size_m'],3,positive=True)
        if (entity['size_m'] is None)!=(entity['size_authority']=='unknown'):
            raise ValueError('BENCHMARK_UNKNOWN_SIZE_MUST_NOT_BECOME_TRUTH')
        placement=entity['placement']
        if placement is not None:
            if (type(placement) is not dict or set(placement)!={'relation','parent_label_id','part'}
                    or placement['relation'] not in ('floor','surface','drape','wall','ceiling')
                    or placement['parent_label_id'] is not None and type(placement['parent_label_id']) is not str
                    or placement['part'] is not None and type(placement['part']) is not str
                    or placement['relation'] in ('surface','drape') and (not placement['parent_label_id'] or not placement['part'])
                    or placement['relation'] not in ('surface','drape') and
                       (placement['parent_label_id'] is not None or placement['part'] is not None)):
                raise ValueError('BENCHMARK_SUPPORT_ANNOTATION_INVALID')
    for entity in value['entities']:
        placement=entity['placement']
        if placement and placement['relation'] in ('surface','drape') and placement['parent_label_id'] not in identities:
            raise ValueError('BENCHMARK_SUPPORT_LABEL_MISSING')
    if type(value['relations']) is not list or len(value['relations'])>512:
        raise ValueError('BENCHMARK_RELATION_ANNOTATION_INVALID')
    for relation in value['relations']:
        if (type(relation) is not dict or set(relation)!={'subject','relation','object','known'}
                or relation['subject'] not in identities or relation['object'] not in identities
                or relation['subject']==relation['object'] or type(relation['known']) is not bool
                or relation['relation'] not in ('left','right','front','rear','above','adjacent')):
            raise ValueError('BENCHMARK_RELATION_ANNOTATION_INVALID')
    return deepcopy(value)


def semantic_entities(plan,placement_contract=None):
    """One semantic tool entity, not one expanded visual/USD part."""
    from twinpulse_core import SiteToolPlan,execute_site_tool_plan
    from twinpulse_core.photo_placement import validate_placement_plan
    from twinpulse_core.furniture import expand_furniture,furniture_footprint
    plan=SiteToolPlan.from_dict(plan);digest=canonical_sha(plan.to_dict())
    execute_site_tool_plan(plan,source='photo',source_ref=digest)
    validate_placement_plan(plan,placement_contract)
    floors=[c.arguments for c in plan.calls if c.tool=='create_floor']
    if len(floors)!=1:raise ValueError('BENCHMARK_ROOM_FRAME_REQUIRED')
    floor=floors[0];fx,fy=floor['center_m'];width,length=floor['size_m']
    placements={row['id']:row for row in (placement_contract or {}).get('relations',[])}
    rows=[]
    for call in plan.calls:
        if call.tool not in ('place_furniture','place_room_item'):continue
        args=call.arguments;identity=args['id']
        if call.tool=='place_furniture':
            x,y=args['center_m'];parts=expand_furniture(args)
            top=max(p.transform.position_m[2]+p.shape.dimensions_m[2]/2 for p in parts)
            size=list(args.get('dimensions_m',[*furniture_footprint(args['kind']),top]));z=top/2
        else:
            x,y,z=args['position_m'];size=list(args['dimensions_m'])
        placement=placements.get(identity)
        if placement is None and call.tool=='place_furniture':
            placement=dict(relation='floor',parent_id=None,part=None)
        rows.append(dict(id=identity,kind=args['kind'],centre_uv=[(x-fx)/width,(y-fy)/length],
            centre_z_m=z,size_m=size,placement=deepcopy(placement)))
    return rows


def assignment(costs):
    """Rectangular minimum-cost Hungarian assignment, O(n²m), n<=m."""
    if not costs:return []
    n=len(costs);m=len(costs[0]);u=[0.]*(n+1);v=[0.]*(m+1);p=[0]*(m+1);way=[0]*(m+1)
    for i in range(1,n+1):
        p[0]=i;j0=0;minimum=[math.inf]*(m+1);used=[False]*(m+1)
        while True:
            used[j0]=True;i0=p[j0];delta=math.inf;j1=0
            for j in range(1,m+1):
                if used[j]:continue
                current=costs[i0-1][j-1]-u[i0]-v[j]
                if current<minimum[j]:minimum[j]=current;way[j]=j0
                if minimum[j]<delta:delta=minimum[j];j1=j
            for j in range(m+1):
                if used[j]:u[p[j]]+=delta;v[j]-=delta
                else:minimum[j]-=delta
            j0=j1
            if p[j0]==0:break
        while j0:
            j1=way[j0];p[j0]=p[j1];j0=j1
    result=[None]*n
    for j in range(1,m+1):
        if p[j]:result[p[j]-1]=j-1
    return result


def matching(labels,predictions,maximum):
    # Maximum-cardinality first, minimum spatial cost second. Dummy assignments
    # prevent matching wrong categories merely to boost recall. IDs are ignored.
    penalty=10*(len(labels)+1);costs=[]
    for label in labels:
        row=[]
        for predicted in predictions:
            distance=math.dist(label['centre_uv'],predicted['centre_uv']) if label['centre_uv'] is not None else 0.
            row.append(distance if label['kind']==predicted['kind'] and distance<=maximum else penalty*2)
        costs.append(row+[penalty]*len(labels))
    chosen=assignment(costs)
    return {label['label_id']:predictions[j] for i,(label,j) in enumerate(zip(labels,chosen))
            if j<len(predictions) and costs[i][j]<penalty}


def fraction(passed,total):return dict(passed=passed,denominator=total,value=passed/total if total else None)


def evaluate(annotation,packet,rubric,plan,placement_contract=None,*,render_review=None):
    rubric=checked_rubric(rubric);labels=checked_annotation(annotation,packet,rubric)
    plan_sha=canonical_sha(plan);geometry_error=None
    try:predictions=semantic_entities(plan,placement_contract)
    except ValueError as error:
        predictions=[];geometry_error=str(error).split(':',1)[0]
    observable=[e for e in labels['entities'] if e['visibility']=='observable']
    matched=matching(observable,predictions,rubric['match_distance_uv'])
    unobservable=[e for e in labels['entities'] if e['visibility']!='observable']
    visible_prediction_ids={p['id'] for p in matched.values()}
    unscored=matching(unobservable,[p for p in predictions if p['id'] not in visible_prediction_ids],rubric['match_distance_uv'])
    # An explicitly unobservable object is neither a true positive nor a false
    # positive. Visible entities are matched first; unknown cannot steal them.
    scored_count=len(predictions)-len(unscored)
    tp=len(matched);recall=fraction(tp,len(observable));precision=fraction(tp,scored_count)
    f1=2*tp/(len(observable)+scored_count) if observable or scored_count else None
    hazards=[e for e in observable if e['hazard']]
    hazard=fraction(sum(e['label_id'] in matched for e in hazards),len(hazards))
    spatial_pass=spatial_total=spatial_unknown=support_pass=support_total=support_unknown=size_pass=size_total=0
    ambiguous={e['label_id'] for e in observable if e['centre_uv'] is None
        and sum(other['kind']==e['kind'] for other in observable)>1}
    for relation in labels['relations']:
        if not relation['known']:spatial_unknown+=1;continue
        if relation['subject'] not in {e['label_id'] for e in observable} or relation['object'] not in {e['label_id'] for e in observable}:
            spatial_unknown+=1;continue
        a=matched.get(relation['subject']);b=matched.get(relation['object'])
        if relation['subject'] in ambiguous or relation['object'] in ambiguous:
            spatial_unknown+=1;continue
        spatial_total+=1
        if not a or not b:continue
        ax,ay=a['centre_uv'];bx,by=b['centre_uv'];epsilon=rubric['relation_epsilon_uv']
        verdict={'left':ax<bx-epsilon,'right':ax>bx+epsilon,'front':ay<by-epsilon,
            'rear':ay>by+epsilon,'adjacent':math.dist([ax,ay],[bx,by])<=rubric['adjacent_distance_uv'],
            'above':a['centre_z_m']>b['centre_z_m']}
        spatial_pass+=verdict[relation['relation']]
    for entity in observable:
        predicted=matched.get(entity['label_id']);support=entity['placement']
        if support:
            parent=matched.get(support['parent_label_id'])
            if entity['label_id'] in ambiguous or support['parent_label_id'] in ambiguous:
                support_unknown+=1
            else:
                support_total+=1;actual=(predicted or {}).get('placement') or {}
                parent_id=(parent or {}).get('id') if support['relation'] in ('surface','drape') else support['parent_label_id']
                support_pass+=bool(predicted and actual.get('relation')==support['relation']
                    and actual.get('parent_id')==parent_id and actual.get('part')==support['part'])
        if entity['size_authority']!='unknown':
            size_total+=1
            size_pass+=bool(predicted and all(abs(a-b)/b<=rubric['size_relative_tolerance']
                for a,b in zip(predicted['size_m'],entity['size_m'])))
    spatial=fraction(spatial_pass,spatial_total);support=fraction(support_pass,support_total)
    size=fraction(size_pass,size_total);visual='NOT_EVALUATED';render_sha=None
    room_size=fraction(0,0)
    if labels['room_size_authority']!='unknown':
        floors=[c['arguments']['size_m'] for c in plan.get('calls',[]) if c.get('tool')=='create_floor']
        room_size=fraction(int(len(floors)==1 and all(abs(a-b)/b<=rubric['size_relative_tolerance']
            for a,b in zip(floors[0],labels['room_size_m']))),1)
    if render_review is not None:
        required={'schema_version','case_id','input_sha256','plan_sha256','rubric_sha256',
                  'frame_sha256','reviewers','source','blinded','recognizable'}
        if (type(render_review) is not dict or set(render_review)!=required
                or render_review['schema_version']!='benchmark-visual-review-1.0'
                or render_review['case_id']!=packet['case_id'] or render_review['input_sha256']!=canonical_sha(packet)
                or render_review['plan_sha256']!=plan_sha or render_review['rubric_sha256']!=canonical_sha(rubric)
                or render_review['source']!='independent_human' or render_review['blinded'] is not True
                or type(render_review['recognizable']) is not bool
                or type(render_review['reviewers']) is not list or not render_review['reviewers']
                or any(type(r) is not str or r not in labels['reviewers'] for r in render_review['reviewers'])
                or len(set(render_review['reviewers']))!=len(render_review['reviewers'])):
            raise ValueError('BENCHMARK_INDEPENDENT_VISUAL_REVIEW_BINDING_INVALID')
        _digest(render_review['frame_sha256']);render_sha=render_review['frame_sha256']
        visual='PASS' if render_review['recognizable'] else 'FAIL'
    failed=(geometry_error is not None or f1 is not None and f1<rubric['entity_f1_min']
        or hazard['value'] is not None and hazard['value']<rubric['hazard_recall_min']
        or spatial['value'] is not None and spatial['value']<rubric['relation_accuracy_min']
        or support['value'] is not None and support['value']<rubric['relation_accuracy_min']
        or size_total>size_pass or room_size['value']==0 or visual=='FAIL')
    incomplete=(not labels['coverage_complete'] or not observable or ambiguous
        or spatial_unknown or support_unknown or visual=='NOT_EVALUATED')
    status='FAIL' if failed else 'NOT_EVALUATED' if incomplete else 'PASS'
    return dict(schema_version=VERSION,status=status,case_id=packet['case_id'],input_sha256=canonical_sha(packet),
        annotation_sha256=canonical_sha(annotation),rubric_sha256=canonical_sha(rubric),plan_sha256=plan_sha,
        placement_sha256=canonical_sha(placement_contract),frame_sha256=render_sha,
        entity_precision=precision,entity_recall=recall,entity_f1=f1,hazard_recall=hazard,
        spatial_accuracy=spatial,support_accuracy=support,size_compliance=size,room_size_compliance=room_size,
        unknown_relations=spatial_unknown+support_unknown,ambiguous_entities=len(ambiguous),
        geometry_contradictions=int(geometry_error is not None),geometry_error_code=geometry_error,
        visual_recognizability=visual,human_reviewers=len(labels['reviewers']),
        matched_entities=tp,predicted_entities=len(predictions),observable_entities=len(observable),
        excluded_unobservable_predictions=len(unscored),
        excluded_unobservable=sum(e['visibility']!='observable' for e in labels['entities']),
        scope='INDEPENDENT_APPROXIMATE_SEMANTIC_QUALITY_NOT_METRIC_RECONSTRUCTION_OR_ROBOT_ACCEPTANCE',
        physical_authority=False)
