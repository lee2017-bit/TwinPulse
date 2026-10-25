# SPDX-License-Identifier: Apache-2.0
"""Kit-thread-only review ghost/projection. No fleet, collision or controls."""
import math,re,time

class AlignmentView:
    ROOT='/World/TwinPulse/AlignmentReview'
    def __init__(self):self.packet=None;self.key=None
    def update(self,snapshot,packet):
        import omni.usd
        from pxr import UsdGeom
        stage=omni.usd.get_context().get_stage()
        if stage is None:return
        valid=(isinstance(packet,dict) and packet.get('physical_authority') is False and packet.get('status')=='GEOMETRIC_REVIEW'
            and packet.get('scene_revision')==snapshot.applied_revision and snapshot.applied_revision is not None
            and packet.get('source') in {'CURRENT','SAVED'} and re.fullmatch('[a-f0-9]{32}',str(packet.get('review_id')))
            and all(isinstance(packet.get(k),list) and len(packet[k])==3 and all(type(n) in (int,float) and math.isfinite(n) for n in packet[k]) for k in ('body_pose','sensor_pose'))
            and isinstance(packet.get('points_body'),list) and len(packet['points_body'])<=180
            and all(isinstance(p,list) and len(p)==2 and all(type(n) in (int,float) and math.isfinite(n) and abs(n)<100 for n in p) for p in packet['points_body'])
            and type(packet.get('height_m')) in (int,float) and .05<=packet['height_m']<=1.)
        if valid and packet['source']=='CURRENT':
            stamp=packet.get('original_captured_at_ms');valid=type(stamp) in (int,float) and 0<=time.time()*1000-stamp<1000
        if valid and 'points_pose' in packet:
            p=packet['points_pose'];valid=isinstance(p,list) and len(p)==3 and all(type(n) in (int,float) and math.isfinite(n) for n in p)
        if valid and 'show_body' in packet:valid=type(packet['show_body']) is bool
        if not valid:
            self.packet=None;self.key=None
            if stage.GetPrimAtPath(self.ROOT):stage.RemovePrim(self.ROOT)
            return
        key=(snapshot.engine_session_id,snapshot.stage_epoch,snapshot.applied_revision,packet['review_id'])
        if key!=self.key or not stage.GetPrimAtPath(self.ROOT):
            if stage.GetPrimAtPath(self.ROOT):stage.RemovePrim(self.ROOT)
            placement=UsdGeom.Xform.Define(stage,self.ROOT);placement.AddTranslateOp();placement.AddRotateZOp()
            placement.GetPrim().SetCustomDataByKey('reviewOnly',True)
            from twinpulse_app.simulation_assets import ASSET_ROOT,burger_inventory
            burger_inventory();model=stage.DefinePrim(self.ROOT+'/Model','Xform')
            model.GetReferences().AddReference(str(ASSET_ROOT/'turtlebot3_burger.usda'));model.GetVariantSet('Physics').SetVariantSelection('none')
            self.key=key
        UsdGeom.Imageable(stage.GetPrimAtPath(self.ROOT+'/Model')).GetVisibilityAttr().Set('inherited' if packet.get('show_body',True) else 'invisible')
        x,y,yaw=packet['body_pose'];ops=UsdGeom.Xform(stage.GetPrimAtPath(self.ROOT)).GetOrderedXformOps()
        ops[0].Set((x,y,0.));ops[1].Set(math.degrees(yaw));self.packet=packet

    def frame(self,viewport):
        if not self.packet:return None
        import omni.usd
        from pxr import Gf,UsdGeom
        stage=omni.usd.get_context().get_stage();camera=UsdGeom.Camera(stage.GetPrimAtPath(str(viewport.camera_path)))
        if not camera:return None
        view=camera.GetCamera(0).frustum.ComputeViewMatrix();projection=camera.GetCamera(0).frustum.ComputeProjectionMatrix()
        def project(x,y,z):
            point=Gf.Vec3d(x,y,z)
            if view.Transform(point)[2]>=0:return None
            p=(view*projection).Transform(point);uv=[float((p[0]+1)/2),float((1-p[1])/2)]
            return uv if all(0<=v<=1 for v in uv) else None
        p=self.packet;x,y,yaw=p.get('points_pose',p['body_pose']);c,s=math.cos(yaw),math.sin(yaw);height=p['height_m'];hits=[]
        for a,b in p['points_body']:
            uv=project(x+c*a-s*b,y+s*a+c*b,height)
            if uv:hits.append(uv)
        bounds=UsdGeom.BBoxCache(0,[UsdGeom.Tokens.default_,UsdGeom.Tokens.render]).ComputeWorldBound(stage.GetPrimAtPath(self.ROOT+'/Model')).ComputeAlignedRange()
        corners=[project(*bounds.GetCorner(i)) for i in range(8)] if p.get('show_body',True) and not bounds.IsEmpty() else []
        corners=[v for v in corners if v];box=None
        if corners:box=[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)]
        return dict(review_id=p['review_id'],source=p['source'],body_bounds_uv=box,
            origin_uv=project(p['sensor_pose'][0],p['sensor_pose'][1],height),points_uv=hits,
            original_captured_at_ms=p['original_captured_at_ms'],physical_authority=False)
