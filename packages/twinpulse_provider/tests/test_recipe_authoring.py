# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary generic bounds compilation, not photo/model acceptance."""
from copy import deepcopy
import unittest
from twinpulse_core.model_recipe import compiled_parts,ModelRecipeError,recipe_model_id
from twinpulse_provider.model_recipe_authoring import compile_authoring,AUTHORING_VERSION


def table():
    def part(identity,x,y,z,support=False):
        return dict(id=identity,x_bounds=x,y_bounds=y,z_bounds=z,material='wood',support_top=support)
    return dict(authoring_version=AUTHORING_VERSION,title='Reusable asymmetric two-level stand',family='common',kind='storage',
        parameters=[dict(name=k,type='number',minimum=.4,maximum=3.,default=v)
            for k,v in [('width',1.2),('depth',.6),('height',1.4)]],
        parts=[part('lower',[-.5,.5],[-.5,.5],[.2,.23],True),
               part('upper',[-.5,0],[-.5,.5],[.97,1],True),
               part('left_back',[-.5,-.46],[-.5,-.46],[0,1]),
               part('left_front',[-.5,-.46],[.46,.5],[0,1]),
               part('right_back',[.46,.5],[-.5,-.46],[0,.23]),
               part('right_front',[.46,.5],[.46,.5],[0,.23])])


class AuthoringTests(unittest.TestCase):
    def test_canonical_geometry_resize_and_no_mutation(self):
        raw=table();before=deepcopy(raw);recipe=compile_authoring(raw)
        self.assertEqual(raw,before);self.assertNotIn('authoring_version',recipe)
        self.assertEqual(compile_authoring(recipe),recipe)
        for dims in ([1.2,.6,1.4],[2.4,1.2,2.8],[.4,.4,.4]):
            parts=compiled_parts(recipe,dict(zip(('width','depth','height'),dims)))
            self.assertEqual(len(parts),6)
            self.assertAlmostEqual(parts[1]['size'][0],dims[0]/2)
        self.assertEqual(recipe_model_id(recipe),recipe_model_id(compile_authoring(raw)))

    def test_bad_bounds_are_not_corrected(self):
        for bounds in ([.5,-.5],[0,0],[-.6,.4],[float('nan'),.3]):
            raw=table();raw['parts'][0]['x_bounds']=bounds
            with self.assertRaises(ModelRecipeError):compile_authoring(raw)

    def test_original_connection_envelope_and_panel_checks_remain(self):
        floating=table();floating['parts']=floating['parts'][:2]
        with self.assertRaises(ModelRecipeError):compile_authoring(floating)
        short=table();short['parts'][1]['z_bounds']=[.8,.83]
        short['parts'][2]['z_bounds']=[0,.83];short['parts'][3]['z_bounds']=[0,.83]
        with self.assertRaises(ModelRecipeError):compile_authoring(short)
        thick=table();thick['parts'][1]['z_bounds']=[.23,1]
        with self.assertRaises(ModelRecipeError):compile_authoring(thick)


if __name__=='__main__':unittest.main()
