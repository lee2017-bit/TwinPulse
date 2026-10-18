# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure, request-local geometry diagnostics. No provider, I/O or authority."""
from copy import deepcopy
import math
import re

from .revisions import canonical_sha256

GEOMETRY_DIAGNOSTIC_REVISION = 'geometry-diagnostic-1.0'


def geometry_issue(code, identity, *, path=None, actual=None, expected=None,
                   related_ids=(), violation=None, repairable=True):
    targets = [identity] if identity else []
    path = path or ('$.objects.'+identity+'.placement' if identity else '$')
    related = sorted(set(str(i) for i in related_ids if i))
    key = dict(code=code, path=path, target_ids=targets, related_ids=related)
    return dict(**key, issue_id=canonical_sha256(key), stage='geometry',
                severity='error', check_status='failed', repairable=repairable,
                actual=deepcopy(actual), expected=deepcopy(expected),
                **({'violation_m': float(violation)} if violation is not None else {}))


def geometry_report(issues, blocked=()):
    return dict(schema_version=GEOMETRY_DIAGNOSTIC_REVISION,
                issues=deepcopy(issues[:64]), issue_count=len(issues),
                issues_truncated=len(issues)>64, blocked_checks=deepcopy(list(blocked)),
                physical_authority=False)


class GeometryValidationError(ValueError):
    def __init__(self, issues, blocked=()):
        self.contract_report = geometry_report(issues, blocked)
        self.code = issues[0]['code'] if issues else 'GEOMETRY_INVALID'
        self.repairable = bool(issues) and all(i.get('repairable', False) for i in issues)
        super().__init__('; '.join(i['code']+': '+
            ((i.get('expected') or {}).get('reason','')+': ' if isinstance(i.get('expected'),dict)
             and (i.get('expected') or {}).get('reason') else '')+','.join(i['target_ids']) for i in issues[:4]))


def validate_model_relations(rows, height, reviewed_supports, quality_constraints=None):
    """Collect independent relation errors before packing; do not fabricate poses."""
    from .model_library import library_models, validate_furniture_parameters
    from .furniture import furniture_kinds
    from .warehouse_models import WAREHOUSE_KINDS, warehouse_parts, support_parts
    registry = {m['kind']: m for m in library_models()}
    by_id = {i['id']: i for i in rows}
    relations, issues, blocked = {}, [], []
    identifier = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')
    for item in rows:
        identity, size, relation = item['id'], item['dimensions_m'], item['placement']
        model = registry.get(item['kind'])
        recipe=item.get('model_recipe_snapshot')
        if recipe:
            from .model_recipe import checked_recipe,recipe_model_id,checked_parameters,compiled_parts,recipe_manifest,checked_assembly
            try:
                checked_recipe(recipe,sample=False)
                params=checked_parameters(recipe,item.get('recipe_parameters'))
                checked_assembly(compiled_parts(recipe,params,already_checked=True),params)
                if (recipe['kind']!=item['kind'] or recipe_model_id(recipe)!=item['model_id']
                        or list(size)!=[params[k] for k in ('width','depth','height')]):
                    raise ValueError('MODEL_RECIPE_BINDING_MISMATCH')
                model=recipe_manifest(recipe)
            except ValueError as error:
                issues.append(geometry_issue(str(error).split(':')[0],identity,
                    actual=item,expected={'detail':str(error)}))
                blocked.append(dict(check='relation:'+identity,blocked_by=issues[-1]['issue_id']))
                continue
        parent = relation.get('parent_id') if isinstance(relation, dict) else None
        def add(code, *, field='placement', actual=None, expected=None, violation=None):
            issues.append(geometry_issue(code, identity, path='$.objects.'+identity+'.'+field,
                actual=actual if actual is not None else relation, expected=expected,
                related_ids=(parent, '$room'), violation=violation))
        if (model is None or item['model_id'] != model['model_id']
                or item['variant'] not in model['variants'] or item['finish'] not in model['finishes']
                or not isinstance(size, list) or len(size) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0<v<=10 for v in size)):
            add('PHOTO_MODEL_PARAMETERS_INVALID', field='dimensions_m', actual=item,
                expected={'model': model, 'finite_positive_dimensions_m': True})
            blocked.append(dict(check='relation:'+identity, blocked_by=issues[-1]['issue_id']))
            continue
        if item['kind'] in furniture_kinds() and not recipe:
            try:
                validate_furniture_parameters(item)
            except ValueError as error:
                add(str(error).split(':')[0], field='dimensions_m', actual=item,
                    expected={'library_model': model, 'detail': str(error)})
                blocked.append(dict(check='relation:'+identity, blocked_by=issues[-1]['issue_id']))
                continue
        if item['kind'] in WAREHOUSE_KINDS and not recipe:
            try:
                parts = warehouse_parts(item)
            except ValueError as error:
                add(str(error).split(':')[0], field='warehouse_parameters', actual=item,
                    expected={'library_model':model,'detail':str(error)})
                blocked.append(dict(check='relation:'+identity,blocked_by=issues[-1]['issue_id']))
                continue
            top=max(p.transform.position_m[2]+p.shape.dimensions_m[2]/2 for p in parts)
            if top > height:
                add('PHOTO_MODEL_EXCEEDS_ROOM_HEIGHT',field='dimensions_m[2]',actual=top,
                    expected={'max_m':height,'nominal_height_m':size[2],'basis':'expanded_factory_geometry'},violation=top-height)
        if (not isinstance(relation, dict) or set(relation) != {'relation','parent_id','part','anchor','elevation_m'}
                or not isinstance(relation['relation'],str) or relation['relation'] not in {'floor','surface','drape','wall','ceiling'}
                or not isinstance(relation['anchor'],str) or relation['anchor'] not in {'centre','front','left','right','rear'}
                or any(v is not None and (not isinstance(v,str) or not identifier.fullmatch(v))
                       for v in (relation['parent_id'],relation['part']))
                or relation['elevation_m'] is not None and (type(relation['elevation_m']) not in (int,float)
                    or not math.isfinite(relation['elevation_m']) or not 0<=relation['elevation_m']<=height)):
            add('PHOTO_RELATION_INVALID', expected={'relations':['floor','surface','drape','wall','ceiling'],
                'elevation_range_m':[0,height]})
            blocked.append(dict(check='parent_graph:'+identity, blocked_by=issues[-1]['issue_id']))
            continue
        kind, part = relation['relation'], relation['part']
        from .room_item_catalog import REQUIRED_ROOM_RELATIONS
        required=REQUIRED_ROOM_RELATIONS.get(item['kind'])
        if required and kind!=required:
            add('PHOTO_MODEL_RELATION_MISMATCH',expected={'relation':required,'kind':item['kind']})
        if size[2]>height:
            add('PHOTO_MODEL_EXCEEDS_ROOM_HEIGHT', field='dimensions_m[2]', actual=size[2],
                expected={'max_m':height,'depends_on':['$.room.height_m']}, violation=size[2]-height)
        if (recipe or item['kind'] in (*furniture_kinds(), 'pallet', *WAREHOUSE_KINDS)) and kind!='floor':
            add('PHOTO_RELATION_UNSUPPORTED', expected={'relation':'floor','reason':'furniture must be floor-standing'})
        if kind=='floor':
            if parent is not None or part is not None or relation['anchor']!='centre' or relation['elevation_m'] is not None:
                add('PHOTO_RELATION_FLOOR_INVALID', expected={'parent_id':None,'part':None,
                    'anchor':'centre','elevation_m':None})
        elif kind in {'surface','drape'}:
            if parent not in by_id or parent==identity:
                add('PHOTO_RELATION_PARENT_MISSING_OR_SELF', expected={'parent_ids':[i for i in by_id if i!=identity]})
                blocked.append(dict(check='support:'+identity, blocked_by=issues[-1]['issue_id']))
            else:
                allowed=sorted(support_parts(by_id[parent]['kind'],kind,by_id[parent].get('warehouse_parameters')))
                if by_id[parent].get('model_recipe_snapshot'):
                    from .model_recipe import recipe_support_parts
                    allowed=(recipe_support_parts(by_id[parent]['model_recipe_snapshot'],by_id[parent]['recipe_parameters'])
                        if kind=='surface' else [])
                if part not in allowed or relation['elevation_m'] is not None:
                    add('PHOTO_RELATION_PART_UNSUPPORTED', expected={'parts':allowed,'elevation_m':None})
            if kind=='surface' and relation['anchor']!='centre':
                add('PHOTO_RELATION_SURFACE_ANCHOR_INVALID', expected={'anchor':'centre'})
            if kind=='drape' and (item['kind'] not in {'hanging_clothes','bedding_overhang','clothing_pile'}
                    or relation['anchor']=='centre'):
                add('PHOTO_RELATION_DRAPE_UNSUPPORTED', expected={'kinds':['hanging_clothes','bedding_overhang','clothing_pile'],
                    'anchors':['front','rear','left','right']})
        elif kind=='wall':
            from .room_item_catalog import WALL_ITEMS
            if (item['kind'] not in WALL_ITEMS or parent not in {'left_wall','right_wall','rear_wall'}
                    or part is not None or relation['anchor']!='centre' or relation['elevation_m'] is None):
                add('PHOTO_RELATION_WALL_UNSUPPORTED', expected={'kinds':list(WALL_ITEMS),
                    'parents':['left_wall','right_wall','rear_wall'],'part':None,'anchor':'centre'})
            else:
                lower, upper = size[2]/2, height-size[2]/2
                center = relation['elevation_m']
                if not lower<=center<=upper:
                    add('PHOTO_RELATION_WALL_HEIGHT_INVALID', field='placement.elevation_m', actual=center,
                        expected={'min_m':lower,'max_m':upper,'unit':'m',
                            'depends_on':['$.objects.'+identity+'.dimensions_m[2]','$.room.height_m'],
                            'constraint':'object_height/2 <= centre_height <= room_height-object_height/2'},
                        violation=max(lower-center,center-upper,0))
        elif kind=='ceiling':
            from .room_item_catalog import CEILING_ITEMS
            if (item['kind'] not in CEILING_ITEMS or parent!='ceiling' or part is not None
                    or relation['anchor']!='centre' or relation['elevation_m'] is not None):
                add('PHOTO_RELATION_CEILING_UNSUPPORTED', expected={'kinds':list(CEILING_ITEMS),'parent_id':'ceiling',
                    'part':None,'anchor':'centre','elevation_m':None})
        if identity in reviewed_supports and (kind!='surface' or (parent,part)!=reviewed_supports[identity]):
            add('PHOTO_RELATION_REVIEWED_SUPPORT_CHANGED', expected={'relation':'surface',
                'parent_part':list(reviewed_supports[identity]),'basis':'reviewed'})
        if quality_constraints:
            if identity in quality_constraints.floor_items and kind!='floor':
                add('PHOTO_FLOOR_SEMANTIC_MISMATCH', expected={'relation':'floor','basis':'reviewed'})
            attachments=dict(quality_constraints.attachments)
            if identity in attachments and (kind!='drape' or (parent,part) not in attachments[identity]):
                add('PHOTO_ATTACHMENT_SEMANTIC_MISMATCH', expected={'relation':'drape',
                    'parent_parts':[list(pair) for pair in attachments[identity]],'basis':'reviewed'})
        relations[identity]=deepcopy(relation)
    for identity, relation in relations.items():
        seen={identity}; parent=relation['parent_id']
        while parent in relations:
            if parent in seen:
                issues.append(geometry_issue('PHOTO_RELATION_CYCLE',identity,actual=relation,
                    expected={'acyclic_parent_graph':True},related_ids=seen))
                break
            seen.add(parent); parent=relations[parent]['parent_id']
        parent=relation['parent_id']
        if parent in relations and relations[parent]['relation']!='floor':
            # Only a checked surface-on-surface DAG is a new nested path.
            # Drape/wall/ceiling chains keep their original restrictions.
            if relation['relation']!='surface' or relations[parent]['relation']!='surface':
                issues.append(geometry_issue('PHOTO_RELATION_NESTED_PARENT_UNSUPPORTED',identity,
                    actual=relation,expected={'parent_relation':'floor or checked surface DAG','basis':'library_support'},related_ids=[parent]))
    if issues:
        blocked.extend([{'check':'packing','blocked_by':issues[0]['issue_id']},
                        {'check':'placement','blocked_by':issues[0]['issue_id']}])
        raise GeometryValidationError(issues, blocked)
    return relations
