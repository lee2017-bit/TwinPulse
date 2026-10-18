# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core.sim_robot_selection import sim_robot_selection


class SelectionTests(unittest.TestCase):
    def test_environment_is_default_without_inventing_a_photo_robot(self):
        value=sim_robot_selection('Build an apartment with a sofa and dining table')
        self.assertIsNone(value['asset_id'])
        self.assertEqual(value['code'],'SIM_ENVIRONMENT_ONLY')
        self.assertIn('no SIM robot',value['reason'])

    def test_requested_burger_is_supported(self):
        for text in ('A warehouse with Burger3','터틀봇3 로봇을 준비해줘', 'Use TurtleBot3 Burger, no red walls',
                     'TurtleBot3를 사용해줘'):
            with self.subTest(text=text):
                self.assertEqual(sim_robot_selection(text)['code'],'SIM_BURGER_EXPLICIT')

    def test_model_mention_without_selection_action_is_environment_only(self):
        for text in ('Burger3 in a warehouse','The photo mentions TurtleBot3 Burger',
                     'TurtleBot3 is not needed; build the room only'):
            with self.subTest(text=text):
                self.assertEqual(sim_robot_selection(text)['code'],'SIM_ENVIRONMENT_ONLY')

    def test_common_words_are_not_robot_model_requests(self):
        self.assertEqual(sim_robot_selection('Find a clear spot and fetch the room description')['code'],'SIM_ENVIRONMENT_ONLY')

    def test_robot_omission_does_not_select_even_a_named_supported_robot(self):
        for text in ('방을 만들고 로봇은 추가하지마', '로봇 없이 환경만 만들어줘',
                     '버거3는 사용하지 마', 'Create the room without a robot',
                     "Do not add TurtleBot3 Burger", 'No robots in this photo-based room',
                     'UR5 없이 방만 만들어줘', 'Go2는 사용하지마', '드론은 제외', 'No Spot robot',
                     '터틀봇3 Burger를 추가하지마', 'TurtleBot3 Burger를 추가하지마',
                     'TurtleBot3 를 추가하지 마', 'Do not add UR5', 'without a Spot',
                     'Do not use the existing TurtleBot3', 'Do not add a simulated TurtleBot3 Burger'):
            with self.subTest(text=text):
                value=sim_robot_selection(text)
                self.assertEqual(value['code'],'SIM_ENVIRONMENT_ONLY')
                self.assertIsNone(value['asset_id'])

    def test_other_robot_requires_explicit_alternative(self):
        for text in ('Spot in a home','UR5 arm','Waffle','Go2','드론으로 검사','humanoid robot'):
            with self.subTest(text=text):
                self.assertIsNone(sim_robot_selection(text)['asset_id'])
                self.assertEqual(sim_robot_selection(text)['code'],'SIM_ROBOT_ALTERNATIVE_REQUIRED')
