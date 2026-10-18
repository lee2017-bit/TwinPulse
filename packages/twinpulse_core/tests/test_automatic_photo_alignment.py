# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
from twinpulse_core.automatic_photo_alignment import align_photo_map, structural_section
from twinpulse_core.room_localization import compose, inverse, angle
from twinpulse_core.revisions import canonical_sha256
from packages.twinpulse_core.tests.test_room_localization import fixture, scan_points


def room(scale=1):
    outline=copy.deepcopy(fixture())
    outline['segments']=[[[x*scale,y*scale] for x,y in s] for s in outline['segments']]
    objects=[{'id':'floor','kind':'floor','transform':{'position_m':[0,0,-.05]},'shape':{'dimensions_m':[3*scale,4*scale,.1]}}]
    for i,(a,b) in enumerate(outline['segments']):
        objects.append({'id':f'wall_{i}','kind':'wall','material':'preserve-me',
                        'transform':{'position_m':[(a[0]+b[0])/2,(a[1]+b[1])/2,1.2],
                                     'rotation_rpy_deg':[0,0,math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))]},
                        'shape':{'dimensions_m':[math.dist(a,b),.04,2.4]}})
    objects.append({'id':'chair','kind':'chair','transform':{'position_m':[.2,.2,.5]},'shape':{'dimensions_m':[.6,.6,1.]}})
    return outline,objects


def mapping(outline,start=(0,-.6,.4), *, changed_validation=None,moving_furniture=False):
    rows=[];anchor=inverse(start)
    for i in range(30):
        truth=[start[0]+.35*math.sin(i*.8),start[1]+i*.026,start[2]+i*.006]
        current=changed_validation if i>18 and changed_validation else outline
        if moving_furniture:
            current=copy.deepcopy(current);x=.5*math.sin(i*.7);y=.5
            corners=[[x-.3,y-.25],[x+.3,y-.25],[x+.3,y+.25],[x-.3,y+.25]]
            current['segments']+=[[corners[j],corners[(j+1)%4]] for j in range(4)]
        rows.append({'stamp_ns':1_000_000_000+i*500_000_000,'sequence':i*10,
                     'pose':compose(anchor,truth),'points':scan_points(current,truth)})
    body={'keyframes':rows};return {**body,'revision':canonical_sha256(body)}


class PhotoAlignmentTests(unittest.TestCase):
    def test_two_recipes_different_starts_hidden_truth_no_manual_pairs(self):
        for scale in (1,1.2):
            outline,objects=room(scale)
            for start in ((0,-.6,.4),(-.3,-.5,-1.1)):
                result=align_photo_map(mapping(outline,start),objects,policy='correct_walls')
                self.assertEqual(result['status'],'ALIGNMENT_CANDIDATE',result)
                self.assertLess(math.dist(result['room_from_map'][:2],start[:2]),.08)
                self.assertLess(abs(angle(result['room_from_map'][2]-start[2])),.06)
                self.assertFalse(set(result['fit_sequences'])&set(result['validation_sequences']))
                self.assertEqual(result['sensor_section']['unknown'][0]['status'],'LOWER_STRUCTURE_UNKNOWN')
                self.assertFalse(result['alignment_verified']);self.assertFalse(result['motion_authorized'])

    def test_geometry_bounded_improves_separate_holdout_preserves_photo_ids_height_material(self):
        outline,objects=room();nominal=copy.deepcopy(objects)
        nominal[1]['transform']['position_m'][1]-=.12
        before=copy.deepcopy(nominal)
        result=align_photo_map(mapping(outline),nominal,policy='correct_walls')
        self.assertEqual(result['status'],'ALIGNMENT_CANDIDATE',result)
        self.assertEqual(result.get('geometry_status'),'BOUNDED_WALL_PROPOSAL_VALIDATED',result)
        self.assertLess(result['validation_after_m'],result['validation_before_m'])
        self.assertEqual(before,nominal)
        for a,b in zip(nominal,result['corrected_objects']):
            self.assertEqual(a['id'],b['id']);self.assertEqual(a['shape'],b['shape'])
            self.assertEqual(a.get('material'),b.get('material'));self.assertEqual(a['transform']['position_m'][2],b['transform']['position_m'][2])
        # Hidden evaluator checks geometry against independently authored truth.
        target=result['corrected_objects'][1]['transform']['position_m']
        self.assertLess(math.dist(target[:2],objects[1]['transform']['position_m'][:2]),.06)

    def test_sparse_symmetric_wrong_dimensions_and_moving_structure_never_forced(self):
        outline,objects=room();saved=mapping(outline)
        sparse=copy.deepcopy(saved);sparse['keyframes']=sparse['keyframes'][:3]
        self.assertEqual(align_photo_map(sparse,objects)['status'],'INSUFFICIENT_EVIDENCE')
        from packages.twinpulse_core.tests.test_room_localization import scan_points
        square={'segments':[[[-1.5,-1.5],[1.5,-1.5]],[[1.5,-1.5],[1.5,1.5]],[[1.5,1.5],[-1.5,1.5]],[[-1.5,1.5],[-1.5,-1.5]]]}
        square_objects=room()[1][:1]
        for i,(a,b) in enumerate(square['segments']):
            square_objects.append({'id':f's{i}','kind':'wall','transform':{'position_m':[(a[0]+b[0])/2,(a[1]+b[1])/2,1],
                                  'rotation_rpy_deg':[0,0,math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))]},'shape':{'dimensions_m':[3,.04,2]}})
        self.assertEqual(align_photo_map(mapping(square),square_objects)['status'],'AMBIGUOUS')
        wrong=copy.deepcopy(objects)
        for o in wrong[1:-1]:
            o['transform']['position_m'][:2]=[v*1.5 for v in o['transform']['position_m'][:2]]
            o['shape']['dimensions_m'][0]*=1.5
        self.assertNotEqual(align_photo_map(saved,wrong)['status'],'ALIGNMENT_CANDIDATE')
        moved=copy.deepcopy(outline);moved['segments']=[[[x+.4,y+.3] for x,y in s] for s in moved['segments']]
        result=align_photo_map(mapping(outline,changed_validation=moved),objects)
        self.assertEqual(result['status'],'VALIDATION_REJECTED',result)

    def test_furniture_is_not_wall_and_bad_sensor_height_rejected(self):
        _,objects=room();section=structural_section(objects,.182)
        self.assertNotIn('chair',[w['id'] for w in section['walls']])
        with self.assertRaises(ValueError):structural_section(objects,2)
        self.assertEqual(align_photo_map({'revision':'a'*64,'keyframes':[]},objects,policy='disabled')['status'],'DISABLED')

    def test_moving_furniture_never_becomes_an_automatic_wall_edit(self):
        outline,objects=room();result=align_photo_map(mapping(outline,moving_furniture=True),objects,policy='correct_walls')
        self.assertFalse(result['alignment_verified']);self.assertFalse(result['motion_authorized'])
        self.assertNotIn('chair',[p['id'] for p in result['proposals']])
        if result['room_from_map'] is not None:
            self.assertLess(math.dist(result['room_from_map'][:2],[0,-.6]),.08)
            self.assertLess(abs(angle(result['room_from_map'][2]-.4)),.06)

    def test_corrupt_nonfinite_or_reordered_views_rejected_before_registration(self):
        outline,objects=room();saved=mapping(outline)
        saved['keyframes'][1]['pose'][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'POINT_BUDGET'):align_photo_map(saved,objects)
        saved=mapping(outline);saved['keyframes'][1]['stamp_ns']=saved['keyframes'][0]['stamp_ns']
        with self.assertRaisesRegex(ValueError,'KEYFRAME_ORDER'):align_photo_map(saved,objects)


if __name__=='__main__':unittest.main()
