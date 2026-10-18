# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import unittest
from twinpulse_core.automatic_photo_alignment import align_photo_map, _residual_audit, _parallel_separations, _line
from packages.twinpulse_core.tests.test_automatic_photo_alignment import room, mapping


class ResidualDiagnosisTests(unittest.TestCase):
    def test_rejected_structure_keeps_disjoint_uncapped_diagnosis_not_pose(self):
        outline,objects=room()
        for o in objects[1:-1]:
            o['transform']['position_m'][:2]=[v*1.5 for v in o['transform']['position_m'][:2]]
            o['shape']['dimensions_m'][0]*=1.5
        original=copy.deepcopy(objects)
        result=align_photo_map(mapping(outline),objects,policy='correct_walls',diagnostics=True)
        self.assertEqual(result['status'],'MODEL_MISMATCH')
        self.assertIsNone(result['room_from_map']);self.assertEqual(result['proposals'],[])
        diagnostic=result['residual_diagnosis']
        self.assertFalse(diagnostic['candidate_is_accepted_pose'])
        self.assertFalse(diagnostic['motion_authorized'])
        fit={s for r in diagnostic['fit'] for s in r['support_sequences']}
        held={s for r in diagnostic['held_out'] for s in r['support_sequences']}
        self.assertFalse(fit&held);self.assertTrue(fit);self.assertTrue(held)
        self.assertTrue(any(r['mean_uncapped_residual_m']>.5 for r in diagnostic['fit']))
        self.assertEqual(objects,original)

    def test_transformed_line_reports_signed_offset_and_uncapped_severity(self):
        line={'a':[0.,0.],'b':[1.,0.],'n':[0.,1.],'support_sequences':[1,2,3]}
        wall={'id':'wall','a':[0.,2.],'b':[1.,2.],'n':[0.,1.],'rho':2.,'thickness':.04}
        row=_residual_audit([line],[wall],[0.,0.,0.])[0]
        self.assertAlmostEqual(row['normal_offset_m'],-2.)
        self.assertAlmostEqual(row['mean_uncapped_residual_m'],1.98)
        self.assertEqual(row['search_capped_residual_m'],.5)
        self.assertFalse(row['physical_wall_identity_verified'])

    def test_sparse_and_disabled_do_not_invent_candidate(self):
        outline,objects=room();saved=mapping(outline)
        saved['keyframes']=saved['keyframes'][:3]
        self.assertNotIn('residual_diagnosis',align_photo_map(saved,objects))
        self.assertNotIn('residual_diagnosis',align_photo_map(saved,objects,policy='disabled'))

    def test_default_wire_contract_is_byte_identical_to_diagnostic_projection(self):
        import json
        outline,objects=room();saved=mapping(outline)
        wire=align_photo_map(saved,objects,policy='correct_walls')
        diagnostic=align_photo_map(saved,objects,policy='correct_walls',diagnostics=True)
        self.assertNotIn('residual_diagnosis',wire)
        diagnostic.pop('residual_diagnosis')
        self.assertEqual(json.dumps(wire,sort_keys=True),json.dumps(diagnostic,sort_keys=True))

    def test_parallel_gap_does_not_depend_on_arbitrary_candidate_transform(self):
        from twinpulse_core.room_localization import compose
        points=([[0.,0.],[2.,0.]],[[0.,3.],[2.,3.]])
        for pose in ([0.,0.,0.],[1.7,-2.4,.7]):
            lines=[]
            for pair in points:
                moved=[compose(pose,[*p,0])[:2] for p in pair]
                lines.append({**_line(moved),'a':moved[0],'b':moved[1]})
            gap=_parallel_separations(lines)[0]
            self.assertAlmostEqual(gap['normal_separation_m'],3.)
            self.assertFalse(gap['physical_wall_pair_verified'])
