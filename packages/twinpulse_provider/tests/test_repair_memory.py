# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_provider.repair_memory import remember_failure


def test_rejected_targets_are_kept_without_duplicate_geometry_or_mutation():
    candidate={'objects':{'bed':{'region':'front_left','dimensions_m':[1.4,2.,.5]},
        'unrelated':{'region':'rear_right'}}}
    diagnosis={'checks':[{'check_id':'floor_packing','status':'failed'}]}
    context={'targets':[{'id':'bed'}]}
    first=remember_failure([],candidate,diagnosis,['PHOTO_LAYOUT_REGION_FULL:bed'],context,'A',kind='geometry')
    candidate['objects']['bed']['region']='middle_left'
    second=remember_failure(first,candidate,diagnosis,['PHOTO_LAYOUT_REGION_FULL:bed'],context,'B',kind='geometry')
    assert first[0]['targets']['bed']['region']=='front_left'
    assert [r['candidate_revision'] for r in second]==['A','B']
    assert 'unrelated' not in second[0]['targets']
    assert remember_failure(second,candidate,diagnosis,['PHOTO_LAYOUT_REGION_FULL:bed'],context,'B',kind='geometry')==second
    assert second[0]['failed_checks']==['floor_packing']


def test_bounded_context_is_explicit_not_inventory_deletion():
    candidate={'objects':{f'i{i}':{'region':'centre_middle'} for i in range(40)}}
    context={'targets':[{'id':i} for i in candidate['objects']]}
    history=[]
    for i in range(10):
        history=remember_failure(history,candidate,{},['REJECTED'],context,str(i),kind='quality')
    assert len(history)==8 and len(history[-1]['targets'])==32
    assert history[-1]['target_context_truncated'] is True
    assert len(candidate['objects'])==40


class RepairMemoryTests(unittest.TestCase):
    def test_rejected_targets(self):
        test_rejected_targets_are_kept_without_duplicate_geometry_or_mutation()

    def test_explicit_bounding(self):
        test_bounded_context_is_explicit_not_inventory_deletion()
