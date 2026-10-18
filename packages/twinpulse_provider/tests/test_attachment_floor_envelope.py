# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic attachment floor bounds, not photo fidelity or physical acceptance."""
from copy import deepcopy
import unittest

from twinpulse_core import SiteToolPlan, execute_site_tool_plan, canonical_sha256
from twinpulse_provider.photo_layout import compile_layout
from test_photo_layout import observation, request
from test_photo_parametric import object_intent, intent


class AttachmentFloorEnvelopeTests(unittest.TestCase):
    def test_all_drape_anchors_and_quarter_turns_fit_without_changing_input(self):
        for anchor in ('front','rear','left','right'):
            for yaw in (0,90,-90,180):
                with self.subTest(anchor=anchor,yaw=yaw):
                    parent=object_intent('support','bed','front_left',size=[1.2,1.8,.5])
                    parent['yaw_deg']=yaw
                    cloth=object_intent('fabric','bedding_overhang',parent='support',part='mattress',
                        relation='drape',anchor=anchor,size=[.8,.9,.2])
                    value=intent(parent,cloth,width=4,length=4);before=deepcopy(value)
                    payload,trace=compile_layout(value,observation(),request('An estimated room'),None)
                    execute_site_tool_plan(SiteToolPlan.from_dict(payload),source='photo',source_ref=canonical_sha256(value))
                    self.assertEqual(value,before)
                    self.assertFalse(trace['physical_authority'])
                    self.assertEqual({c['arguments']['id'] for c in payload['calls'][4:]},{'support','fabric'})

    def test_unrelated_floor_object_preserved_and_oversize_not_silently_shrunk(self):
        value=intent(object_intent('support','bed','front_left',size=[1.2,1.8,.5]),
            object_intent('fabric','bedding_overhang',parent='support',part='mattress',
                relation='drape',anchor='front',size=[.8,.9,.2]),
            object_intent('other','box','rear_right',size=[.3,.3,.3]),width=5,length=5)
        before=deepcopy(value)
        payload,_=compile_layout(value,observation(),request('An estimated room'),None)
        execute_site_tool_plan(SiteToolPlan.from_dict(payload),source='photo',source_ref=canonical_sha256(value))
        self.assertEqual(value,before)
        value['objects'][1]['dimensions_m']=[8,8,.2];before=deepcopy(value)
        with self.assertRaisesRegex(ValueError,'PHOTO_LAYOUT_REGION_FULL'):
            compile_layout(value,observation(),request('An estimated room'),None)
        self.assertEqual(value,before)


if __name__=='__main__':unittest.main()
