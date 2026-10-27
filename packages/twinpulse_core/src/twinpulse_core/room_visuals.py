# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Illustrative, bounded display meshes. Never collision or photo measurements.

Typed catalog calls select appearance; CURRENT scene geometry selects placement.
The pinned collision catalogs and scene/plan serialization are not modified.
"""
from math import cos, sin, radians, pi, sqrt, isfinite

from .furniture import expand_furniture
from .room_items import expand_room_item
from .room_item_catalog import PARTS
from .model_library import PARAMETRIC_FURNITURE_VERSION, library_models
from .scene_tools import SceneToolRegistry

VISUAL_VERSION = 'room-display-meshes-1.0'
COLORS = dict(wood=(.55, .32, .14), white=(.85, .87, .85), linen=(.57, .65, .70),
              dark=(.025, .035, .045), metal=(.27, .30, .33), blue=(.05, .19, .31),
              cloth=(.24, .29, .27), screen=(.015, .035, .05), cream=(.72, .68, .56))


def visual_bindings(scene, plan):
    """Reject stale/nonuniform geometry rather than drawing old poses over edits.

    Uniform group translation/yaw (including lifted groups) is supported. Missing,
    resized or individually edited parts retain visible conservative proxies.
    """
    objects = {o.id: o for o in scene.objects}
    bindings, skipped = [], []
    for call in plan.calls:
        if call.tool not in {'place_furniture', 'place_room_item','create_rack_row','place_pallet_stack','place_model_recipe'}:
            continue
        args = call.arguments
        warehouse=call.tool in {'create_rack_row','place_pallet_stack'}
        recipe=call.tool=='place_model_recipe'
        expected = (tuple(SceneToolRegistry().execute_static_tool(call.tool,args)) if warehouse or recipe else
                    expand_furniture(args) if call.tool == 'place_furniture' else expand_room_item(dict(args)))
        current = [objects.get(o.id) for o in expected]
        if any(o is None for o in current):
            skipped.append(dict(id=args['id'], reason='MISSING_CURRENT_MEMBER'))
            continue
        first, original = current[0], expected[0]
        yaw = first.transform.rotation_rpy_deg[2]
        delta = radians(yaw - original.transform.rotation_rpy_deg[2])
        c, s = cos(delta), sin(delta)
        def moved(p):
            dx, dy, dz = [p[i] - original.transform.position_m[i] for i in range(3)]
            anchor = first.transform.position_m
            return (anchor[0]+dx*c-dy*s, anchor[1]+dx*s+dy*c, anchor[2]+dz)
        valid = all(o.shape == e.shape and o.collision == e.collision
                    and not o.dynamic and o.kind == e.kind
                    and max(abs(a-b) for a,b in zip(o.transform.position_m, moved(e.transform.position_m))) < 1e-6
                    and abs((o.transform.rotation_rpy_deg[2]-yaw+180)%360-180) < 1e-6
                    and o.transform.rotation_rpy_deg[:2] == (0., 0.)
                    for o,e in zip(current, expected))
        if not valid:
            skipped.append(dict(id=args['id'], reason='NONUNIFORM_CURRENT_GEOMETRY'))
            continue
        if warehouse:
            origin=moved((*args['center_m'],0.))
            ox,oy=args['center_m']
            bounds=[max(abs(o.transform.position_m[i]-(ox,oy,0)[i])+o.shape.dimensions_m[i]/2 for o in expected)
                    for i in range(2)]
            size=(bounds[0]*2,bounds[1]*2,max(o.transform.position_m[2]+o.shape.dimensions_m[2]/2 for o in expected))
        elif call.tool == 'place_furniture' or recipe:
            origin = moved((*args['center_m'], 0.))
            sx, sy = first.shape.dimensions_m[:2]
            height = max(o.transform.position_m[2]+o.shape.dimensions_m[2]/2-origin[2] for o in current)
            size = (sx, sy, height)
            if recipe:
                size=tuple(args['parameters'][k] for k in ('width','depth','height'))
            elif args.get('catalog_version') == PARAMETRIC_FURNITURE_VERSION:
                size = tuple(args['dimensions_m'])
        else:
            size = tuple(args['dimensions_m'])
            origin = moved((args['position_m'][0], args['position_m'][1], args['position_m'][2]-size[2]/2))
        kind=('warehouse_rack' if call.tool=='create_rack_row' else 'pallet_stack') if warehouse else args['kind']
        binding=dict(id=args['id'], kind=kind, origin=origin, size=size, yaw_deg=yaw,
                     members=tuple(o.id for o in current))
        if warehouse:
            binding['model_id']='warehouse.rack' if call.tool=='create_rack_row' else 'warehouse.pallet_stack'
            binding['parameters']=dict(variant='standard',finish='catalog_default',warehouse_parts=[
                dict(name=o.id[len(args['id'])+1:],center=(o.transform.position_m[0]-ox,o.transform.position_m[1]-oy,o.transform.position_m[2]),
                     size=o.shape.dimensions_m) for o in expected])
        if args.get('catalog_version') == PARAMETRIC_FURNITURE_VERSION:
            binding['parameters'] = dict(args)
            binding['model_id'] = next(item['model_id'] for item in library_models() if
                                       item['kind']==args['kind'] and item['tool']=='place_furniture')
        if recipe:
            binding['parameters']=dict(args)
            binding['model_id']=args['model_id']
        bindings.append(binding)
    return bindings, skipped


class Meshes:
    """Fixed tessellation; coordinates are local metres, triangle winding outward."""
    def __init__(self, size):
        if len(size) != 3 or any(not isfinite(v) or not 0 < v <= 10 for v in size):
            raise ValueError('ROOM_VISUAL_SIZE_INVALID')
        self.size, self.parts = size, []

    def add(self, name, points, faces, color):
        if len(self.parts) >= 160 or len(points) > 4096 or any(not isfinite(v) for p in points for v in p):
            raise ValueError('ROOM_VISUAL_MESH_BOUND')
        self.parts.append(dict(name=name, points=points, faces=faces, color=COLORS[color], material=color))

    def box(self, name, center, size, color, radius=.02):
        # Rounded surface sampled on six cube faces, not a visible collider cube.
        center = [center[i]*self.size[i] for i in range(3)]
        half = [size[i]*self.size[i]/2 for i in range(3)]
        r = min(radius, min(half)*.45)
        inner = [v-r for v in half]
        pts, faces = [], []
        n = 4
        for axis in range(3):
            u, v = (axis+1)%3, (axis+2)%3
            for sign in (-1, 1):
                start = len(pts)
                for j in range(n+1):
                    for i in range(n+1):
                        p = [0.,0.,0.]; p[axis] = sign*half[axis]
                        p[u] = (2*i/n-1)*half[u]; p[v] = (2*j/n-1)*half[v]
                        q = [max(-inner[k], min(inner[k], p[k])) for k in range(3)]
                        d = [p[k]-q[k] for k in range(3)]; length = sqrt(sum(a*a for a in d))
                        pts.append(tuple(center[k]+q[k]+r*d[k]/length for k in range(3)))
                for j in range(n):
                    for i in range(n):
                        a=start+j*(n+1)+i; b=a+1; d=a+n+1; e=d+1
                        faces.extend([(a,b,e),(a,e,d)] if sign > 0 else [(a,e,b),(a,d,e)])
        self.add(name, pts, faces, color)

    def tube(self, name, start, end, radius, color, sides=12):
        a = [start[i]*self.size[i] for i in range(3)]
        b = [end[i]*self.size[i] for i in range(3)]
        direction = [b[i]-a[i] for i in range(3)]; length = sqrt(sum(v*v for v in direction))
        if length < 1e-8: raise ValueError('ROOM_VISUAL_ZERO_TUBE')
        z = [v/length for v in direction]
        # Do not let fixed decorative wire/wheel radii protrude outside a
        # shallow or tiny CURRENT prop envelope (e.g. edited small chair).
        for k in range(3):
            radial = sqrt(max(0.,1-z[k]*z[k]))
            if radial > 1e-6:
                lower = -self.size[k]/2 if k<2 else 0.
                upper = self.size[k]/2 if k<2 else self.size[k]
                margin = min(p[k]-lower for p in (a,b))
                margin = min(margin,*(upper-p[k] for p in (a,b)))
                radius = min(radius,max(0.,margin*.99/radial))
        reference = (0,0,1) if abs(z[2]) < .9 else (0,1,0)
        x = [z[1]*reference[2]-z[2]*reference[1], z[2]*reference[0]-z[0]*reference[2], z[0]*reference[1]-z[1]*reference[0]]
        norm=sqrt(sum(v*v for v in x)); x=[v/norm for v in x]
        y=[z[1]*x[2]-z[2]*x[1], z[2]*x[0]-z[0]*x[2], z[0]*x[1]-z[1]*x[0]]
        pts=[tuple(p[k]+radius*(cos(2*pi*j/sides)*x[k]+sin(2*pi*j/sides)*y[k]) for k in range(3))
             for p in (a,b) for j in range(sides)]
        pts += [tuple(a),tuple(b)]
        faces=[]
        for j in range(sides):
            k=(j+1)%sides
            faces.extend([(j,k,k+sides),(j,k+sides,j+sides),(2*sides,k,j),(2*sides+1,j+sides,k+sides)])
        self.add(name,pts,faces,color)

    def cloth(self, name, center, size, color):
        nx, ny = 16, 20
        pts=[]; faces=[]
        for j in range(ny+1):
            for i in range(nx+1):
                x=(i/nx-.5)*size[0]; y=(j/ny-.5)*size[1]
                # Bounded wrinkles; approximation, not cloth simulation.
                z=center[2]+size[2]*(.55+.18*sin(i*.9+j*.4)+.13*cos(j*.8-i*.3))
                pts.append(((center[0]+x)*self.size[0],(center[1]+y)*self.size[1],z*self.size[2]))
        for j in range(ny):
            for i in range(nx):
                a=j*(nx+1)+i; faces.extend([(a,a+1,a+nx+2),(a,a+nx+2,a+nx+1)])
        self.add(name,pts,faces,color)


def _parametric_display(kind,size,parameters):
    """Furniture assembled in metres, not an anisotropic scale of one mesh."""
    from .model_library import parametric_parts
    if parameters.get('kind') != kind or tuple(parameters.get('dimensions_m',())) != tuple(size):
        raise ValueError('ROOM_VISUAL_PARAMETER_MISMATCH')
    parts=parametric_parts(parameters); m=Meshes(size); w,d,h=size
    finish=parameters['finish']; variant=parameters['variant']
    wood={'natural':'wood','white':'white','dark':'dark'}[finish]
    def box(name,center,extent,color=wood,radius=.01):
        m.box(name,tuple(center[i]/size[i] for i in range(3)),
              tuple(extent[i]/size[i] for i in range(3)),color,radius)
    def rod(name,start,end,r=.012,color='metal'):
        m.tube(name,tuple(start[i]/size[i] for i in range(3)),
               tuple(end[i]/size[i] for i in range(3)),r,color)
    def part_box(part,color=wood,radius=.01):
        name,x,y,bottom,sx,sy,height=part
        box(name,(x,y,bottom+height/2),(sx,sy,height),color,radius)
    if kind=='bed':
        for part in parts:part_box(part,'white' if part[0]=='mattress' else wood,.045 if part[0]=='mattress' else .012)
        _,_,_,base,_,_,mh=parts[1]; surface=base+mh
        count=1 if variant=='single' else 2
        for n in range(count):
            x=0 if count==1 else (-w*.24 if n==0 else w*.24)
            box('pillow_'+str(n),(x,d*.31,surface+.045),(w*(.7 if count==1 else .40),min(.45,d*.22),.09),'white',.04)
        m.cloth('quilt',(0,-.14,surface/h),(.96,.64,min(.055,(h-surface)*.4)/h),'linen')
    elif kind in {'desk','dining_table'}:
        for part in parts:part_box(part,'metal' if part[0].startswith('leg') and variant!='wood' else wood,.006)
        rod('rear_brace',(-w/2+.055,d/2-.055,.25),(w/2-.055,d/2-.055,.25))
    elif kind in {'wardrobe','storage'}:
        t=.025
        panel_color=wood if finish!='natural' else 'white'
        for name,x in (('left_panel',-w/2+t/2),('right_panel',w/2-t/2)):
            box(name,(x,0,h/2),(t,d,h),panel_color,.003)
        box('back_panel',(0,d/2-t/2,h/2),(w,t,h),panel_color,.003)
        for n,z in enumerate((t/2,h*.20,h-t/2)):
            box('shelf_'+str(n),(0,0,z),(w,d,t),panel_color,.003)
        box('divider',(-w*.06,0,h*.58),(t,d-.05,h*.77),panel_color,.003)
        for n,x in enumerate((-w/4,w/4)):
            if variant=='open' or (variant=='standard' and n==1):continue
            box('door_'+str(n),(x,-d/2+t/2,h/2),(w/2-.01,t,h-.04),panel_color,.003)
            rod('handle_'+str(n),(x+w*.12,-d/2+.001,h*.43),(x+w*.12,-d/2+.001,h*.57),.009)
        if variant!='closed':
            rod('clothes_rail',(w*.03,0,h*.84),(w*.43,0,h*.84),.01)
            for n,x in enumerate((w*.10,w*.24,w*.38)):
                half=w*.06; z=h*.82
                rod('hanger_left_'+str(n),(x-half,0,z-.04),(x,0,z),.004)
                rod('hanger_right_'+str(n),(x,0,z),(x+half,0,z-.04),.004)
                box('garment_'+str(n),(x,0,z-h*.28),(w*.12,min(.06,d*.15),h*.5),('dark','blue','cloth')[n],.01)
            box('folded_linen',(w*.21,0,h*.245),(w*.38,d*.60,min(.05,h*.04)),'linen')
    elif kind=='chair' and variant=='office':
        # The office variant shares a bounded recipe with the existing prop.
        office=display_meshes('office_chair',size)
        for part in office:
            if part['name'].startswith(('padded_','armrest_')):
                material='dark' if finish=='natural' else wood
                part.update(material=material,color=COLORS[material])
        return office
    elif kind=='chair':
        for part in parts:part_box(part,'cloth' if part[0] in {'seat','back'} else wood,.02 if part[0] in {'seat','back'} else .004)
    elif kind=='sofa':
        for part in parts:part_box(part,wood if part[0]=='base' else 'blue',.025)
        count=3 if variant=='three_seat' else 2
        base=parts[0][3]; cushion=(w-.16)/count
        for n in range(count):
            box('cushion_'+str(n),(-w/2+.08+cushion*(n+.5),-.07,base+.075),
                (cushion-.015,d-.16,.15),'linen',.035)
    else:raise ValueError('ROOM_VISUAL_PARAMETRIC_KIND_INVALID')
    return m.parts


def display_meshes(kind, size, parameters=None):
    """Recognizable catalog silhouettes; not a reconstruction of a specific SKU."""
    if parameters is not None and 'recipe' in parameters:
        from .model_recipe import recipe_display_meshes
        return recipe_display_meshes(parameters)
    if kind in {'warehouse_rack','pallet_stack'} and parameters is not None:
        m=Meshes((1.,1.,1.))
        for part in parameters['warehouse_parts']:
            name=part['name']; color='blue' if kind=='warehouse_rack' and name.startswith('post') else 'metal' if kind=='warehouse_rack' else 'wood' if name=='pallet' else 'cream'
            if name=='pallet':
                x,y,z=part['center'];w,d,h=part['size']
                for n in range(5):
                    m.box('deck_slat_'+str(n),(x-w*.4+n*w*.2,y,z+h*.3),(w*.16,d,h*.3),'wood',.004)
                for n in (-1,0,1):m.box('runner_'+str(n+1),(x+n*w*.34,y,z-h*.15),(w*.12,d,h*.6),'wood',.004)
            else:m.box(name,part['center'],part['size'],color,.006)
        return m.parts
    if parameters is not None:
        return _parametric_display(kind, size, parameters)
    m=Meshes(size)
    def bar(name,a,b,r=.012,color='metal',sides=12): m.tube(name,a,b,r,color,sides)
    def garment(name,x,y,z,width=.18,length=.40,color='cloth'):
        bar(name+'_hanger_l',(x-width/2,y,z-.04),(x,y,z),.006)
        bar(name+'_hanger_r',(x,y,z),(x+width/2,y,z-.04),.006)
        m.box(name+'_body',(x,y,z-length/2-.04),(width,.07,length),color,.025)
        m.box(name+'_sleeve_l',(x-width*.62,y,z-.13),(width*.35,.065,.18),color)
        m.box(name+'_sleeve_r',(x+width*.62,y,z-.13),(width*.35,.065,.18),color)
    if kind == 'bed':
        m.box('wood_frame',(0,0,.14),(.98,.98,.28),'wood')
        m.box('headboard',(0,.47,.49),(1,.05,.98),'wood')
        m.box('mattress',(0,-.01,.41),(.97,.94,.23),'white',.08)
        for n,x in enumerate((-.23,.23)):
            m.box('pillow_'+str(n),(x,.31,.57),(.40,.22,.10),'white',.07)
        m.cloth('quilt',(0,-.14,.54),(.96,.64,.075),'linen')
        for n in range(7):
            y=-.41+n*.086
            bar('quilt_seam_'+str(n),(-.46,y,.584),(.46,y,.584),.002,'white')
    elif kind in {'wardrobe','storage'}:
        for name,x in [('left',-.48),('right',.48)]:
            m.box(name+'_panel',(x,0,.5),(.04,1,1),'white',.005)
        m.box('back_panel',(0,.47,.5),(1,.04,1),'cream',.005)
        for n,z in enumerate((.025,.20,.975)):
            m.box('shelf_'+str(n),(0,0,z),(1,1,.04),'white',.005)
        m.box('divider',(-.06,0,.58),(.025,.96,.77),'white',.003)
        # Catalog half-closed, half-open cabinet: illustrative, not measured door angle.
        m.box('closed_left_door',(-.275,-.47,.5),(.44,.03,.94),'white',.004)
        bar('door_handle',(-.12,-.49,.46),(-.12,-.49,.60),.01,'metal')
        bar('clothes_rail',(.02,0,.84),(.43,0,.84),.01)
        for n,x in enumerate((.10,.24,.38)):
            garment('hanging_garment_'+str(n),x,-.05,.82,.12,.53,('dark','blue','cloth')[n])
        m.box('folded_linen',(.21,0,.245),(.38,.60,.05),'linen')
    elif kind in {'desk','dining_table'}:
        m.box('wood_desktop',(0,0,.96),(1,1,.075),'wood',.012)
        for n,(x,y) in enumerate(((-.44,-.40),(.44,-.40),(-.44,.40),(.44,.40))):
            bar('leg_'+str(n),(x,y,.02),(x,y,.94),.025)
        bar('rear_brace',(-.44,.40,.25),(.44,.40,.25),.015)
    elif kind in {'office_chair','chair'}:
        m.box('padded_seat',(0,-.04,.50),(.75,.70,.10),'dark',.06)
        m.box('padded_back',(0,.32,.76),(.72,.12,.46),'dark',.07)
        bar('seat_stem',(0,0,.10),(0,0,.47),.035)
        for n in range(5):
            a=2*pi*n/5; x=.42*cos(a); y=.42*sin(a)
            bar('spoke_'+str(n),(0,0,.14),(x,y,.10),.018)
            bar('wheel_'+str(n),(x-.035,y,.07),(x+.035,y,.07),.04,'dark')
        for n,x in enumerate((-.39,.39)):
            bar('arm_post_'+str(n),(x,0,.50),(x,0,.66),.01)
            m.box('armrest_'+str(n),(x,0,.67),(.09,.44,.04),'dark')
    elif kind == 'sofa':
        m.box('base',(0,0,.20),(1,1,.35),'wood')
        m.box('back',(0,.40,.65),(1,.18,.67),'blue',.06)
        for n,x in enumerate((-.47,.47)): m.box('arm_'+str(n),(x,0,.55),(.06,.95,.50),'blue',.04)
        for n,x in enumerate((-.25,.25)): m.box('cushion_'+str(n),(x,-.04,.48),(.46,.72,.19),'linen',.06)
    elif kind == 'clothes_rack':
        for n,x in enumerate((-.44,.44)):
            bar('wood_post_'+str(n),(x,0,.02),(x,0,.98),.035,'wood')
            bar('foot_'+str(n),(x,-.4,.04),(x,.4,.04),.035,'wood')
        bar('hanging_rail',(-.44,0,.93),(.44,0,.93),.022,'wood')
        for n,x in enumerate((-.24,0,.24)): garment('coat_'+str(n),x,0,.90,.22,.52,('cream','blue','cloth')[n])
    elif kind == 'floor_fan':
        bar('base',(0,0,.025),(0,0,.07),min(size[:2])*.42,'blue',24)
        bar('stand',(0,0,.07),(0,0,.72),.02,'blue')
        # Circular wire grille in XZ plane; the motor/blades are inset behind it.
        for n,r in enumerate((.10,.20,.30,.42)):
            for j in range(24):
                a=2*pi*j/24; b=2*pi*(j+1)/24
                bar('grille_'+str(n)+'_'+str(j),(r*cos(a),-.12,.76+r*.50*sin(a)),
                    (r*cos(b),-.12,.76+r*.50*sin(b)),.0025)
        for n in range(8):
            a=2*pi*n/8
            bar('radial_'+str(n),(0,-.12,.76),(.42*cos(a),-.12,.76+.21*sin(a)),.002)
        bar('fan_hub',(0,-.14,.76),(0,.10,.76),.035,'blue')
        for n in range(3):
            a=2*pi*n/3
            bar('blade_'+str(n),(0,0,.76),(.30*cos(a),0,.76+.15*sin(a)),.024,'white')
    elif kind == 'floor_lamp':  # 2026-10-27: tall slim lamp (catalog base/pole/shade), not a small cube
        bar('base_disc',(0,0,.005),(0,0,.04),min(size[:2])*.45,'dark',24)
        bar('pole',(0,0,.04),(0,0,.84),.012,'metal')
        bar('shade',(0,0,.84),(0,0,1.),min(size[:2])*.48,'cream',24)
    elif kind == 'pallet':
        for n in range(5):
            m.box('deck_slat_'+str(n),(-.4+n*.2,0,.85),(.16,1,.3),'wood',.004)
        for n in (-1,0,1):
            m.box('runner_'+str(n+1),(n*.34,0,.35),(.12,1,.7),'wood',.004)
    elif kind in {'bag','basket'}:
        if kind == 'bag':
            m.box('soft_bag',(0,0,.43),(.94,.86,.80),'dark',.07)
            for n,y in enumerate((-.27,.27)):
                for j in range(12):
                    a=pi*j/12; b=pi*(j+1)/12
                    bar('handle_'+str(n)+'_'+str(j),(.28*cos(a),y,.79+.18*sin(a)),(.28*cos(b),y,.79+.18*sin(b)),.008,'cloth')
            bar('zipper',(-.36,-.03,.84),(.36,-.03,.84),.003,'metal')
        else:
            m.box('bottom',(0,0,.04),(.96,.94,.08),'cream')
            for n,x in enumerate([-.45+i*.09 for i in range(11)]):
                for side,y in enumerate((-.45,.45)):bar('weave_x_'+str(n)+'_'+str(side),(x,y,.08),(x,y,.88),.007,'cream')
            for n,z in enumerate([.12+i*.12 for i in range(7)]):
                for side,y in enumerate((-.45,.45)):bar('rim_'+str(n)+'_'+str(side),(-.45,y,z),(.45,y,z),.008,'cream')
                for side,x in enumerate((-.45,.45)):bar('side_'+str(n)+'_'+str(side),(x,-.45,z),(x,.45,z),.008,'cream')
    elif kind == 'hanging_clothes':
        garment('coat',0,0,.95,.58,.72,'cream')
    elif kind=='surface_covering':
        m.cloth('supported_textile_layer',(0,0,.2),(.98,.98,.8),'linen')
    elif kind in {'bedding_overhang','clothing_pile'}:
        m.cloth('wrinkled_fabric',(0,0,.15),(.98,.98,.60),'linen' if kind=='bedding_overhang' else 'cloth')
        m.box('folded_edge',(.05,.07,.18),(.65,.60,.20),'white' if kind=='bedding_overhang' else 'cream',.03)
    elif kind == 'cable_bundle':
        for n in range(3):
            for j in range(32):
                a=2*pi*j/32; b=2*pi*(j+1)/32; r=.20+n*.09
                bar('cord_'+str(n)+'_'+str(j),(r*cos(a),r*sin(a),.12+n*.08),(r*cos(b),r*sin(b),.12+n*.08),.003,'dark')
        bar('loose_end',(-.43,-.40,.20),(.40,.32,.20),.003,'dark')
    elif kind == 'monitor':
        m.box('bezel',(0,.06,.63),(.98,.18,.74),'dark',.012)
        m.box('screen',(0,-.043,.63),(.91,.01,.63),'screen',.001)
        bar('support',(0,.06,.06),(0,.06,.34),.018)
        m.box('stand',(0,0,.045),(.65,.74,.07),'metal')
    elif kind == 'window_blind':
        for n in range(16):m.box('slat_'+str(n),(0,0,.025+n*.061),(1,.70,.046),'linen',.002)
        bar('left_guide',(-.44,0,.02),(-.44,0,.98),.002,'white')
        bar('right_guide',(.44,0,.02),(.44,0,.98),.002,'white')
    elif kind == 'ceiling_light':
        bar('round_fixture',(0,0,.15),(0,0,.85),min(size[:2])*.46,'white',32)
    elif kind == 'floor_covering':
        m.cloth('woven_covering',(0,0,.1),(.98,.98,.70),'cloth')
        for n in range(8):
            m.box('weave_'+str(n),(0,-.43+n*.12,.72),(.93,.006,.04),'cream',.001)
    elif kind in {'wall_fixture','ceiling_fixture'}:
        m.box('housing',(0,0,.5),(.98,.94,.98),'white',.008)
        for n in range(7):
            m.box('grille_'+str(n),(0,-.48,.12+n*.12),(.80,.015,.025),'metal',.001)
    elif kind == 'wall_storage':
        for n,(x,y,z,dx,dy,dz) in enumerate(PARTS[kind]):
            m.box('cabinet_part_'+str(n),(x,y,z),(dx,dy,dz),'white',.003)
        for n,x in enumerate((-.23,.23)):
            m.box('door_'+str(n),(x,-.475,.5),(.44,.025,.94),'cream',.003)
            bar('handle_'+str(n),(x,-.495,.43),(x,-.495,.57),.005)
    elif kind == 'door_leaf':
        m.box('wood_door',(0,0,.5),(1,.85,1),'wood',.003)
        m.box('inset',(0,-.44,.5),(.78,.03,.84),'cream',.003)
        bar('handle',(.28,-.49,.44),(.43,-.49,.44),.009)
    elif kind in {'power_adapter','power_strip'}:
        m.box('plastic_housing',(0,0,.45),(.98,.95,.84),'white',.025)
        for n in range(3 if kind=='power_strip' else 1):
            x=-.30+n*.30 if kind=='power_strip' else 0
            m.box('socket_'+str(n),(x,0,.88),(.20,.42,.015),'dark',.001)
    elif kind in {'box','small_equipment','tabletop_item','unknown'}:
        m.box('body',(0,0,.49),(.96,.96,.98),'cream' if kind=='box' else 'metal',.025)
        if kind=='box':
            m.box('lid_seam',(0,0,.98),(.98,.98,.02),'wood',.003)
            m.box('packing_tape',(0,0,.997),(.15,.97,.003),'white',.001)
        elif kind=='unknown':
            m.box('unidentified_marker',(0,-.485,.6),(.6,.02,.25),'cream',.001)
    else:
        raise ValueError('ROOM_VISUAL_KIND_UNSUPPORTED')
    return m.parts
