# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local reusable model discovery. Metadata/options, never a scene or authority.

Families are tags, not copies: common assets may serve home and warehouse scenes.
No downloads, provider execution, or measurement claims occur in this registry.
"""
from copy import deepcopy

LIBRARY_VERSION = 'environment-model-library-1.2'
PARAMETRIC_FURNITURE_VERSION = 'furniture-parametric-1.0'
FINISHES = ('natural', 'white', 'dark')
# kind: default xyz, per-axis min/max, variants, environments
FURNITURE_MODELS = {
    'bed': ((1.4, 2., .9), (.75, 1.5, .4), (2.5, 2.6, 1.6), ('standard','single','double'), ('home',)),
    'wardrobe': ((1.2, .645, 1.9), (.4, .3, .6), (3., 1.2, 3.), ('standard','open','closed'), ('home',)),
    'desk': ((1.2, .6, .74), (.4, .35, .45), (3., 1.5, 1.3), ('standard','wood','metal'), ('home','warehouse')),
    'chair': ((.46, .44, .93), (.35, .35, .65), (.9, .9, 1.5), ('standard','upholstered','office'), ('home','warehouse')),
    'sofa': ((1.6, .8, .85), (.8, .55, .5), (3.5, 1.3, 1.5), ('standard','two_seat','three_seat'), ('home',)),
    'dining_table': ((1.4, .8, .77), (.5, .4, .45), (3., 1.6, 1.3), ('standard','wood','metal'), ('home',)),
    'storage': ((.8, .445, .9), (.3, .25, .3), (3., 1.2, 2.5), ('standard','open','closed'), ('home','warehouse')),
}


def library_models(environment=None):
    """Fresh JSON-safe manifest. Unknown families fail, ambiguous requests use all."""
    if environment not in (None, 'home', 'warehouse', 'common'):
        raise ValueError('MODEL_LIBRARY_ENVIRONMENT_INVALID')
    from .room_item_catalog import ROOM_ITEM_KINDS, room_item_catalog_version
    entries = []
    for kind, (default, lower, upper, variants, envs) in FURNITURE_MODELS.items():
        family = 'common' if len(envs)>1 else 'home'
        entries.append(dict(model_id=family+'.'+kind, kind=kind, family=family,
            environments=list(envs), tool='place_furniture', catalog_version=PARAMETRIC_FURNITURE_VERSION,
            dimensions_m=dict(default=list(default), minimum=list(lower), maximum=list(upper),
                              axes=['width_x','depth_y','height_z']),
            variants=list(variants), finishes=list(FINISHES), size_policy='regenerate_parts_fixed_thickness'))
    home_only = {'clothes_rack','bedding_overhang','clothing_pile','hanging_clothes','window_blind'}
    for kind in ROOM_ITEM_KINDS:
        envs = ['warehouse'] if kind=='pallet' else ['home'] if kind in home_only else ['home','warehouse']
        family = 'warehouse' if kind=='pallet' else 'home' if kind in home_only else 'common'
        entries.append(dict(model_id=family+'.'+kind, kind=kind, family=family,
            environments=envs, tool='place_room_item', catalog_version=room_item_catalog_version(kind),
            dimensions_m=dict(minimum_exclusive=0., maximum=10., axes=['width_x','depth_y','height_z']),
            variants=['standard'], finishes=['catalog_default'], size_policy='bounded_prop_recipe'))
    entries.extend([
        dict(model_id='warehouse.rack', kind='rack', family='warehouse', environments=['warehouse'],
             tool='create_rack_row', dimensions_m=dict(width_x=[.8,12.],depth_y=[.35,2.5],height_z=[.5,6.]),
             parameters=dict(bay_count=[1,8],level_count=[1,5]), variants=['standard'], finishes=['catalog_default'],
             yaw_deg=[0], semantic_dimension_maximum_m=[10.,2.5,6.],
             support_parts=['shelf_'+str(i) for i in range(1,6)],
             dimension_basis='nominal factory dimensions; expanded posts and shelves checked separately',
             size_policy='regenerate_bays_and_levels'),
        dict(model_id='warehouse.pallet_stack', kind='pallet_stack', family='warehouse', environments=['warehouse'],
             tool='place_pallet_stack', dimensions_m=dict(width_x=[0.,2.5],depth_y=[0.,2.5],height_z=[.15,3.]),
             parameters=dict(stack_levels=[1,4]), variants=['standard'], finishes=['catalog_default'], yaw_deg=[0],
             support_parts=['stack_top'], dimension_basis='stack height above 0.12m base; not total height',
             size_policy='regenerate_stack'),
    ])
    return deepcopy([entry for entry in entries if environment is None or
                     (entry['family']=='common' if environment=='common' else environment in entry['environments'])])


def library_for_request(text):
    """Bounded deterministic discovery used to ground the planner's allowed options.

    Mixed/unknown descriptions retain all options rather than banning user objects.
    This does not claim semantic understanding or select any actual scene objects.
    """
    if not isinstance(text,str) or len(text)>32000:
        raise ValueError('MODEL_LIBRARY_QUERY_INVALID')
    query=text.casefold()
    home=any(term in query for term in ('home','house','bedroom','apartment','living room','가정','집','방','아파트'))
    warehouse=any(term in query for term in ('warehouse','factory','pallet','industrial','창고','공장','물류'))
    environment=('home' if home else 'warehouse') if home != warehouse else None
    models=library_models(environment)
    aliases={'bed':('침대',),'wardrobe':('옷장',),'sofa':('소파',),'dining_table':('식탁',),
             'clothes_rack':('행거','옷걸이'),'rack':('랙',),'pallet_stack':('팔레트',)}
    for entry in library_models():
        if (entry['kind'].replace('_',' ') in query or any(term in query for term in aliases.get(entry['kind'],()))) and \
                entry['model_id'] not in {item['model_id'] for item in models}:
            models.append(entry)
    return dict(library_version=LIBRARY_VERSION, environment=environment or 'mixed_or_unspecified',
                models=models, boundary='Available options only; no measurement or motion authority.')


def validate_furniture_parameters(arguments):
    from .scene_tools import SceneToolPlanError, _positive_vector
    kind=arguments.get('kind')
    if kind not in FURNITURE_MODELS:
        raise SceneToolPlanError('parametric furniture kind is unsupported')
    default,lower,upper,variants,_=FURNITURE_MODELS[kind]
    size=_positive_vector(arguments.get('dimensions_m'),3,'dimensions_m',maximum=10.)
    if any(not lower[i]<=size[i]<=upper[i] for i in range(3)):
        raise SceneToolPlanError(f'parametric furniture dimensions out of range for {kind}: min={lower}, max={upper}')
    if arguments.get('variant') not in variants or arguments.get('finish') not in FINISHES:
        raise SceneToolPlanError('parametric furniture variant or finish is unsupported')
    return size


def parametric_parts(arguments):
    """Rebuild parts in metres, keeping panels/legs bounded in absolute thickness.

    Collider parts remain conservative; open doors do not authorize entry into a
    cupboard. Appearance is separate. Origin = XY footprint centre, floor z=0.
    """
    w,d,h=validate_furniture_parameters(arguments)
    kind=arguments['kind']; panel=.025; leg=.055
    if kind=='bed':
        base=min(.28,h*.32); mattress=min(.18,h*.22)
        return (('base',0,0,0,w,d-panel,base),
                ('mattress',0,0,base,w-.04,d-.08,mattress),
                ('headboard',0,d/2-panel/2,0,w,panel,h))
    if kind in {'wardrobe','storage'}:
        door=h-.08
        return (('body',0,panel/2,0,w,d-panel,h),
                ('door_left' if kind=='wardrobe' else 'left_door',-w/4,-d/2+panel/2,.04,w/2-.01,panel,door),
                ('door_right' if kind=='wardrobe' else 'right_door',w/4,-d/2+panel/2,.04,w/2-.01,panel,door))
    if kind in {'desk','dining_table'}:
        top=.06
        return (('top',0,0,h-top,w,d,top), *tuple(
            (name,x*(w/2-leg/2-.025),y*(d/2-leg/2-.025),0,leg,leg,h-top)
            for name,x,y in (('leg_fl',-1,-1),('leg_fr',1,-1),('leg_bl',-1,1),('leg_br',1,1))))
    if kind=='chair':
        seat=min(.48,h*.5)
        return (('seat',0,0,seat,w,d-.06,.06),('back',0,d/2-.03,seat+.06,w,.06,h-seat-.06),*tuple(
            (name,x*(w/2-.045),y*(d/2-.075),0,.045,.045,seat)
            for name,x,y in (('leg_fl',-1,-1),('leg_fr',1,-1),('leg_bl',-1,1),('leg_br',1,1))))
    if kind=='sofa':
        base=min(.32,h*.38); seat=.12; arm=.07
        return (('seat',0,-.07,base,w-2*arm,d-.14,seat),
                ('back',0,d/2-.06,base,w,.12,h-base),
                ('left_arm',-w/2+arm/2,0,base,arm,d,h*.65-base),
                ('right_arm',w/2-arm/2,0,base,arm,d,h*.65-base),
                ('base',0,0,0,w,d,base))
    raise ValueError('PARAMETRIC_RECIPE_MISSING')
