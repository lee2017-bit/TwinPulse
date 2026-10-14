# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Request-local grounding and bounded scene diagnostics. No photo lookup or I/O."""
from copy import deepcopy
from typing import Mapping
from twinpulse_core import canonical_sha256
from .errors import InvalidProviderResponseError

GROUNDING_REVISION = 'photo-layout-1.3'
PROPOSAL_REVISION = 'site-proposal-1.0'
ROLES = ('object', 'structure', 'opening', 'free_space', 'robot', 'unknown')


class SceneContractError(InvalidProviderResponseError):
    def __init__(self, report):
        self.contract_report = report
        errors = [i for i in report['issues'] if i['severity'] == 'error']
        self.code = errors[0]['code'] if errors else 'SCENE_CONTRACT_INVALID'
        super().__init__('; '.join(i['code'] + ':' + i.get('path', '') for i in errors[:4]))


def report(issues=(), blocked=()):
    return dict(schema_version='scene-contract-diagnostic-1.0', issues=list(issues)[:64],
        issues_truncated=len(issues)>64, blocked_checks=list(blocked), physical_authority=False)


def issue(code, path, **detail):
    return dict(code=code, path=path, severity='error', **detail)


def require_valid(value):
    if any(i['severity']=='error' for i in value['issues']):
        raise SceneContractError(value)


def role_of(entity):
    if 'role' in entity:
        return entity['role']
    kind=entity['kind']
    if kind in {'floor','wall'}: return 'structure'
    if kind in {'free_space','aisle','marking'}: return 'free_space'
    if kind in {'agv','robot_candidate'}: return 'robot'
    return 'unknown' if kind=='unknown' else 'object'


def source_schema(observation):
    identifiers=[e['id'] for e in observation.entities
                 if role_of(e) in {'object','unknown'}]
    refs={'type':'array','minItems':1,'maxItems':3,
          'items':{'type':'string','enum':identifiers}} if identifiers else None
    def branch(basis, references, quote):
        return dict(type='object',additionalProperties=False,
            required=['basis','observation_ids','user_quote'],properties=dict(
                basis={'const':basis},observation_ids=references,user_quote=quote))
    branches=[branch('user',dict(type='array',maxItems=0,items={'type':'string'}),
                     dict(type='string',minLength=1,maxLength=256)),
              branch('inferred',dict(type='array',maxItems=0,items={'type':'string'}),{'type':'null'})]
    if refs:
        branches += [branch(b,deepcopy(refs),{'type':'null'}) for b in ('visual','inferred')]
    return {'anyOf':branches}


def _source_issues(source, observation, prompt, path, kind=None):
    issues=[]; entities={e['id']:e for e in observation.entities}
    if (not isinstance(source,Mapping) or set(source)!={'basis','observation_ids','user_quote'}
            or not isinstance(source['basis'],str) or source['basis'] not in {'visual','user','inferred'}
            or not isinstance(source['observation_ids'],list)
            or any(not isinstance(i,str) for i in source['observation_ids'])):
        return [issue('SOURCE_SHAPE_INVALID',path)]
    refs=source['observation_ids']; basis=source['basis'];quote=source['user_quote']
    if len(refs)>3 or len(refs)!=len(set(refs)):
        issues.append(issue('SOURCE_REFERENCES_INVALID',path+'.observation_ids'))
    if basis=='user':
        if refs:issues.append(issue('USER_SOURCE_HAS_VISUAL_REFERENCES',path+'.observation_ids'))
        if not isinstance(quote,str) or not 1<=len(quote.strip())<=256 or quote not in prompt:
            issues.append(issue('USER_SOURCE_QUOTE_NOT_IN_REQUEST',path+'.user_quote'))
    else:
        if not refs and basis != 'inferred':issues.append(issue('PHOTO_LAYOUT_OBJECT_WITHOUT_EVIDENCE',path+'.observation_ids',allowed_ids=list(entities)))
        if quote is not None:issues.append(issue('VISUAL_SOURCE_HAS_USER_QUOTE',path+'.user_quote'))
    valid=[entities[r] for r in refs if r in entities]
    invalid=[r for r in refs if r not in entities]
    if invalid:issues.append(issue('SOURCE_UNOBSERVED_REFERENCES',path+'.observation_ids',invalid_ids=invalid))
    for e in valid:
        if role_of(e) not in {'object','unknown'}:
            issues.append(issue('SCENE_ROLE_IS_NOT_OBJECT',path,observed_id=e['id'],role=role_of(e)))
        if basis=='visual' and (e['kind']=='unknown' or role_of(e)=='unknown'):
            issues.append(issue('UNKNOWN_OBSERVATION_REQUIRES_INFERRED_BASIS',path,observed_id=e['id']))
    categories={e.get('category') for e in valid}-{None,'unknown'}
    if len(refs) > 1:
        issues.append(issue('SOURCE_MULTI_OBJECT_BINDING', path+'.observation_ids', invalid_ids=refs))
    if kind and categories and any(kind != category for category in categories):
        issues.append(issue('SOURCE_OBJECT_CATEGORY_MISMATCH',path,proposed_kind=kind,observed_categories=sorted(categories)))
    return issues


def ground_layout(value, observation, request):
    """Validate explicit sources before lowering to the existing parametric compiler."""
    if not isinstance(value,Mapping) or value.get('layout_version')!=GROUNDING_REVISION:
        return value, {}, None
    issues=[];sources={};represented=set();bound_objects={};normalized=deepcopy(value)
    objects=value.get('objects')
    if not isinstance(objects,list):raise SceneContractError(report([issue('PHOTO_LAYOUT_OBJECTS_INVALID','$.objects')]))
    for n,item in enumerate(objects):
        path=f'$.objects[{n}]'
        if not isinstance(item,Mapping) or not isinstance(item.get('id'),str):
            issues.append(issue('PHOTO_LAYOUT_OBJECT_INVALID',path));continue
        if item['id'] in sources:issues.append(issue('DUPLICATE_OBJECT_ID',path+'.id'))
        source=item.get('source'); source_issues=_source_issues(source,observation,request.prompt,path+'.source',item.get('kind'))
        issues.extend(source_issues)
        if isinstance(source,Mapping) and isinstance(source.get('observation_ids'),list):
            if not source_issues:
                for ref in source['observation_ids']:
                    if ref in bound_objects:
                        issues.append(issue('SOURCE_OBSERVATION_DUPLICATED', path+'.source.observation_ids',
                            observed_id=ref, first_object_id=bound_objects[ref], object_id=item['id']))
                    else:
                        bound_objects[ref] = item['id']
                        represented.add(ref)
            sources[item['id']]=deepcopy(source)
            normalized['objects'][n].pop('source',None)
            normalized['objects'][n]['observation_ids']=deepcopy(source['observation_ids'])
    required={e['id'] for e in observation.entities if role_of(e) in {'object','unknown'}}
    missing=required-represented
    if missing:issues.append(issue('PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING','$.objects',missing_ids=sorted(missing)))
    result=report(issues, ['packing','support','photo_relations'] if issues else [])
    require_valid(result)
    normalized['layout_version']='photo-layout-1.2'
    result.update(source_contract=GROUNDING_REVISION,
        sources=sources, source_layout_sha256=canonical_sha256(value),
        unmeasured=True, text_semantic_validation='EXACT_QUOTE_ONLY_NOT_FULL_NLU',
        category_validation='TYPED_OBSERVATION' if observation.schema_version in {'1.1','1.3'} else 'UNVERIFIED_LEGACY_OBSERVATION',
        shell_observations=[e['id'] for e in observation.entities if role_of(e)=='structure'],
        unresolved_openings=[e['id'] for e in observation.entities if role_of(e)=='opening'])
    result['hypotheses'] = [identity for identity, source in sources.items()
        if source['basis'] == 'inferred' and not source['observation_ids']]
    return normalized,sources,result


def preflight_legacy_layout(value, observation):
    """Audit immutable old candidates; old wire versions are not silently upgraded."""
    if not isinstance(value,Mapping) or value.get('layout_version')==GROUNDING_REVISION:
        return report()
    objects=value.get('objects');issues=[];represented=set();observed={e['id'] for e in observation.entities}
    if not isinstance(objects,list):return report()
    for n,item in enumerate(objects):
        if not isinstance(item,Mapping) or not isinstance(item.get('observation_ids'),list):continue
        refs=item['observation_ids'];path=f'$.objects[{n}].observation_ids'
        if not refs:issues.append(issue('PHOTO_LAYOUT_OBJECT_WITHOUT_EVIDENCE',path,object_id=item.get('id'),allowed_ids=sorted(observed)))
        invalid=[r for r in refs if not isinstance(r,str) or r not in observed]
        if invalid:issues.append(issue('PHOTO_LAYOUT_UNOBSERVED_REFERENCES',path,invalid_ids=invalid))
        represented.update(r for r in refs if isinstance(r,str))
    missing={e['id'] for e in observation.entities if role_of(e) in {'object','unknown'}}-represented
    if missing:issues.append(issue('PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING','$.objects',missing_ids=sorted(missing)))
    return report(issues,['packing','support','photo_relations'] if issues else [])


def lower_proposal(value):
    """Only lower a declared proposal; never insert a floor into old responses."""
    if not isinstance(value,Mapping) or value.get('proposal_version')!=PROPOSAL_REVISION:
        return value, None
    expected={'proposal_version','coordinate_frame','plan_version','scene_id','summary',
              'image_observations','floor_call','floor_evidence','scene_calls','call_evidence'}
    if set(value)!=expected or not isinstance(value['scene_calls'],list) or not isinstance(value['call_evidence'],list):
        raise SceneContractError(report([issue('SITE_PROPOSAL_SHAPE_INVALID','$')],['geometry','photo_relations']))
    if not isinstance(value['floor_call'],Mapping) or value['floor_call'].get('tool')!='create_floor':
        raise SceneContractError(report([issue('REQUIRED_TOOL_COUNT','$.floor_call',tool='create_floor',expected=1,actual=0)],['geometry']))
    if any(not isinstance(c,Mapping) or c.get('tool')=='create_floor' for c in value['scene_calls']):
        raise SceneContractError(report([issue('EXTRA_FLOOR_IN_SCENE_CALLS','$.scene_calls')],['geometry']))
    if not isinstance(value['coordinate_frame'],str) or value['coordinate_frame'] not in {'photo_view_right_rear','local_xy'}:
        raise SceneContractError(report([issue('SCENE_COORDINATE_FRAME_INVALID','$.coordinate_frame')]))
    result={k:deepcopy(value[k]) for k in ('plan_version','scene_id','summary','image_observations')}
    result['calls']=[deepcopy(value['floor_call']),*deepcopy(value['scene_calls'])]
    raw_evidence=[value['floor_evidence'],*value['call_evidence']]
    if any(not isinstance(e,Mapping) or 'user_quote' not in e for e in raw_evidence):
        raise SceneContractError(report([issue('PROPOSAL_EVIDENCE_SHAPE_INVALID','$.call_evidence')]))
    result['call_evidence']=[{k:deepcopy(v) for k,v in e.items() if k!='user_quote'} for e in raw_evidence]
    return result, dict(coordinate_frame=value['coordinate_frame'],sources=deepcopy(raw_evidence),
                       proposal_sha256=canonical_sha256(value))


def preflight_site(value, observation, request, proposal=None):
    """Collect independent defects. Geometry is checked by the unchanged executor."""
    issues=[];calls=value.get('calls',[]) if isinstance(value,Mapping) else []
    evidence=value.get('call_evidence',[]) if isinstance(value,Mapping) else []
    if not isinstance(calls,list) or not isinstance(evidence,list):
        return report([issue('SITE_COLLECTION_INVALID','$')],['bounds','overlap','support','photo_relations'])
    counts={};by_call={};observed={e['id']:e for e in observation.entities};represented=set()
    if proposal and proposal['coordinate_frame']!=('photo_view_right_rear' if request.images else 'local_xy'):
        issues.append(issue('SCENE_COORDINATE_FRAME_INVALID','$.coordinate_frame'))
    for n,c in enumerate(calls):
        if not isinstance(c,Mapping):issues.append(issue('SITE_CALL_SHAPE_INVALID',f'$.calls[{n}]'));continue
        tool=c.get('tool');identity=c.get('call_id')
        if not isinstance(tool,str) or not isinstance(identity,str):
            issues.append(issue('SITE_CALL_SHAPE_INVALID',f'$.calls[{n}]'));continue
        counts[tool]=counts.get(tool,0)+1
        if identity in by_call:issues.append(issue('DUPLICATE_CALL_ID',f'$.calls[{n}].call_id'))
        by_call[identity]=c
    for tool,minimum,maximum in [('create_floor',1,1),('place_predefined_agv',0,1),('create_navigation_task',0,1)]:
        actual=counts.get(tool,0)
        if not minimum<=actual<=maximum:issues.append(issue('REQUIRED_TOOL_COUNT','$.calls',tool=tool,actual=actual,minimum=minimum,maximum=maximum))
    quotes={e.get('call_id'):e.get('user_quote') for e in proposal['sources'] if isinstance(e.get('call_id'),str)} if proposal else {}
    cited_calls=set()
    for n,e in enumerate(evidence):
        path=f'$.call_evidence[{n}]'
        if not isinstance(e,Mapping) or not isinstance(e.get('observation_ids'),list):
            issues.append(issue('SITE_EVIDENCE_SHAPE_INVALID',path));continue
        refs=e['observation_ids'];basis=e.get('basis');identity=e.get('call_id')
        if not isinstance(identity,str):issues.append(issue('SITE_EVIDENCE_SHAPE_INVALID',path));continue
        call=by_call.get(identity)
        if identity in cited_calls:issues.append(issue('DUPLICATE_CALL_EVIDENCE',path))
        cited_calls.add(identity)
        if basis not in ('visual','user','inferred','trusted_measurement'):
            issues.append(issue('SOURCE_BASIS_INVALID',path+'.basis'))
        if call is None:issues.append(issue('EVIDENCE_CALL_MISSING',path));continue
        represented.update(r for r in refs if isinstance(r,str))
        unknown=[r for r in refs if not isinstance(r,str) or r not in observed]
        if unknown:issues.append(issue('SOURCE_UNOBSERVED_REFERENCES',path,invalid_ids=unknown))
        if basis=='visual' and not refs:issues.append(issue('VISUAL_SOURCE_WITHOUT_REFERENCES',path))
        if basis=='user' and refs:issues.append(issue('USER_SOURCE_HAS_VISUAL_REFERENCES',path))
        if proposal and basis=='user':
            quote=quotes.get(e.get('call_id'))
            if not isinstance(quote,str) or not quote.strip() or quote not in request.prompt:
                issues.append(issue('USER_SOURCE_QUOTE_NOT_IN_REQUEST',path+'.user_quote'))
        elif proposal and quotes.get(identity) is not None:
            issues.append(issue('VISUAL_SOURCE_HAS_USER_QUOTE',path+'.user_quote'))
        args=call.get('arguments',{}); kind=args.get('kind') if isinstance(args,Mapping) else None
        category={'create_rack_row':'rack','place_pallet_stack':'pallet','create_floor':'floor','create_wall':'wall'}.get(call.get('tool'),kind)
        for ref in refs:
            entity=observed.get(ref) if isinstance(ref,str) else None
            if entity is None:continue
            target_role=role_of(entity)
            if basis=='visual' and target_role=='unknown':
                issues.append(issue('UNKNOWN_OBSERVATION_REQUIRES_INFERRED_BASIS',path,observed_id=ref))
            if target_role in {'free_space','opening'} and call.get('tool') not in {'create_aisle_marking'}:
                issues.append(issue('SCENE_ROLE_MISMATCH',path,observed_id=ref,role=target_role))
            if target_role=='structure' and call.get('tool') not in {'create_floor','create_wall'}:
                issues.append(issue('SCENE_ROLE_MISMATCH',path,observed_id=ref,role=target_role))
            expected=entity.get('category')
            if category and expected not in (None,'unknown') and category!=expected:
                issues.append(issue('SOURCE_OBJECT_CATEGORY_MISMATCH',path,observed_id=ref,proposed_kind=category,expected=expected))
    required={e['id'] for e in observation.entities if role_of(e) in {'object','unknown'}}
    if set(by_call)-cited_calls:issues.append(issue('CALL_EVIDENCE_MISSING','$.call_evidence',missing_ids=sorted(set(by_call)-cited_calls)))
    if required-represented:issues.append(issue('PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING','$.call_evidence',missing_ids=sorted(required-represented)))
    checked=report(issues,['bounds','overlap','support'] if counts.get('create_floor')!=1 else [])
    checked['category_validation']='TYPED_OBSERVATION' if observation.schema_version in {'1.1','1.3'} else 'UNVERIFIED_LEGACY_OBSERVATION'
    return checked


def review_photo_relations(value, observation, frame):
    """Photo-view ordering only. Nearness, metric accuracy and occlusion stay unknown."""
    checks=[];uncovered=[];issues=[];centres={}
    calls={c['call_id']:c for c in value['calls']}
    for e in value.get('call_evidence',[]):
        c=calls.get(e['call_id']);args=c.get('arguments',{}) if c else {}
        point=args.get('center_m',args.get('position_m'))
        if isinstance(point,list) and len(point)>=2 and all(type(p) in (int,float) for p in point[:2]):
            for ref in e['observation_ids']:centres.setdefault(ref,[]).append(point[:2])
    entities={e['id']:e for e in observation.entities}
    for relation in observation.relations:
        a,b=relation['subject_id'],relation['object_id'];kind=relation['relation']
        axis=0 if kind in {'left_of','right_of'} else 1 if kind in {'in_front_of','behind'} else None
        reason=None
        if frame!='photo_view_right_rear':reason='COORDINATE_FRAME_UNVERIFIED'
        elif axis is None:reason='RELATION_NOT_METRICALLY_VERIFIABLE'
        elif a not in centres or b not in centres or len(centres[a])!=1 or len(centres[b])!=1:reason='ENTITY_GEOMETRY_AMBIGUOUS_OR_MISSING'
        elif min(entities[a].get('spatial_confidence',0),entities[b].get('spatial_confidence',0))<.8:reason='LOW_SPATIAL_CONFIDENCE'
        if reason:uncovered.append(dict(**relation,reason=reason));continue
        delta=centres[a][0][axis]-centres[b][0][axis]
        expected=-1 if kind in {'left_of','in_front_of'} else 1
        contradiction=delta*expected<-.05
        status='CONTRADICTION' if contradiction else 'CONSISTENT' if delta*expected>.05 else 'AMBIGUOUS'
        checks.append(dict(**relation,status=status,estimated_delta_m=round(delta,5)))
        if contradiction:issues.append(issue('PHOTO_RELATIVE_ORDER_CONTRADICTION','$.calls',**relation,
            violation_m=round(-delta*expected-.05,5)))
    floor=next((c['arguments'] for c in value['calls'] if c['tool']=='create_floor'),None)
    region_checks=[];uncovered_regions=[]
    for identity,entity in entities.items():
        region=entity.get('region','unknown')
        if role_of(entity) not in {'object','unknown'}:continue
        reason=None
        if frame!='photo_view_right_rear':reason='COORDINATE_FRAME_UNVERIFIED'
        elif region=='unknown':reason='REGION_UNKNOWN'
        elif entity.get('spatial_confidence',0)<.8:reason='LOW_SPATIAL_CONFIDENCE'
        elif identity not in centres or len(centres[identity])!=1 or floor is None:reason='ENTITY_GEOMETRY_AMBIGUOUS_OR_MISSING'
        if reason:uncovered_regions.append(dict(observed_id=identity,reason=reason));continue
        row,col=region.split('_');x,y=centres[identity][0];fx,fy=floor['center_m'];width,length=floor['size_m']
        x-=fx;y-=fy
        # These are estimated photo-view half-plane constraints, not a new
        # measured position. Include the COMPILED point: an attached item's
        # declared region does not control its position independently of parent.
        xb=([-width/2,.05] if col=='left' else [-.05,width/2] if col=='right'
            else [-width/6-.05,width/6+.05])
        yb=([-length/2,.05] if row=='front' else [-.05,length/2] if row=='rear'
            else [-length/6-.05,length/6+.05])
        dx=max(xb[0]-x,0,x-xb[1]);dy=max(yb[0]-y,0,y-yb[1])
        mismatch=dx>0 or dy>0
        violation=round((dx*dx+dy*dy)**.5,5)
        detail=dict(observed_id=identity,region=region,
            estimated_position_m=[round(x,5),round(y,5)],
            expected_photo_view_bounds_m={'x':xb,'y':yb},violation_m=violation)
        region_checks.append(dict(**detail,status='CONTRADICTION' if mismatch else 'CONSISTENT'))
        if mismatch:issues.append(issue('PHOTO_OBSERVED_REGION_CONTRADICTION','$.calls',**detail))
    return dict(schema_version='observed-photo-relations-1.0',status='NEEDS_REPAIR' if issues else 'PARTIAL' if checks or region_checks else 'UNVERIFIED',
                issues=issues,checks=checks,region_checks=region_checks,uncovered_regions=uncovered_regions,
                uncovered_relations=uncovered,metric_scale_validation='UNVERIFIED',physical_authority=False)
