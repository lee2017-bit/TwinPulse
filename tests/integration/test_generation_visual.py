# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exact, display-only ephemeral catalog transport; no engine/LLM fixture PASS."""
from copy import deepcopy
from dataclasses import replace
import unittest

from twinpulse_core import execute_site_tool_plan, canonical_sha256
from twinpulse_core.generation_visual import generation_visual, checked_generation_visual
from twinpulse_app.command_broker import CommandBroker
from tests.integration.test_scene_changes import furnished_source


class GenerationVisualTests(unittest.TestCase):
    def setUp(self):
        self.plan = furnished_source().plan
        self.scene = execute_site_tool_plan(self.plan, source='photo', source_ref='a'*64).scene
        self.value = generation_visual(self.plan, self.scene, 'example')

    def test_ephemeral_plan_exactly_binds_without_project_commit(self):
        self.assertEqual(checked_generation_visual(self.value, self.scene, 'example').to_dict(), self.plan.to_dict())
        broker = CommandBroker(project_id='example')
        before = self.scene.to_dict()
        registered = broker.register_site_scene('preview', self.scene, visual_preview=self.value)
        self.value['plan']['summary'] = 'Caller changed its own object'
        self.assertEqual(registered.visual_preview['plan']['summary'], self.plan.summary)
        self.assertEqual(self.scene.to_dict(), before)
        self.assertEqual(broker.public_state('owner')['operations'], [])

    def test_wrong_project_revision_hash_extra_and_stale_geometry_rejected(self):
        for change in ('project','revision','hash','extra','plan'):
            with self.subTest(change=change):
                value = deepcopy(self.value)
                if change=='project':value['project_id']='other'
                elif change=='revision':value['scene_revision']='b'*64
                elif change=='hash':value['plan_sha256']='b'*64
                elif change=='extra':value['path']='untrusted.usd'
                else:value['plan']['summary']='Changed typed plan'
                with self.assertRaises(ValueError):checked_generation_visual(value, self.scene, 'example')
                with self.assertRaises(ValueError):CommandBroker(project_id='example').register_site_scene('preview', self.scene, visual_preview=value)
        objects = list(self.scene.objects)
        objects[-1]=replace(objects[-1],transform=replace(objects[-1].transform,
            position_m=(objects[-1].transform.position_m[0]+.02,*objects[-1].transform.position_m[1:])))
        changed=replace(self.scene,objects=tuple(objects),parent_revision=self.scene.revision)
        value=deepcopy(self.value);value['scene_revision']=changed.revision
        with self.assertRaisesRegex(ValueError,'SCENE_CHANGED'):
            checked_generation_visual(value,changed,'example')

    def test_untrusted_executable_or_robot_call_is_never_accepted(self):
        for tool,args in [('execute_python',dict(code='print(1)')),('place_predefined_agv',
                dict(profile_id='compact_2wd.v1',position_m=[0,0,0],yaw_deg=0))]:
            with self.subTest(tool=tool):
                value=deepcopy(self.value)
                value['plan']['calls'].append(dict(call_id='untrusted',tool=tool,arguments=args))
                value['plan'].pop('call_evidence',None)
                value['plan_sha256']=canonical_sha256(value['plan'])
                with self.assertRaises(ValueError):checked_generation_visual(value,self.scene,'example')


if __name__=='__main__':unittest.main()
