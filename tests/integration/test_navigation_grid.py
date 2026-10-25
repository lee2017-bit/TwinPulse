# SPDX-License-Identifier: Apache-2.0
import base64
from copy import deepcopy
import math
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from twinpulse_core.navigation_grid import encode_navigation_grid,decode_navigation_grid,checked_navigation_grid
from twinpulse_core.sim_fleet_navigation import checked_scene_geometry,approach_plan
from twinpulse_core import canonical_sha256
from tests.integration.test_robot_fleet import Broker
from twinpulse_app.robot_fleet import RobotFleet


class NavigationGridTests(unittest.TestCase):
    def grid(self):
        return [[(x+.5)*.1,(y+.5)*.1,'free' if x<15 or y>15 else 'occupied',0,0,0,0]
            for y in range(-5,35) for x in range(-10,30)]

    def wire(self):
        return dict(schema='scene-navigation-2.0',epoch=1,source_sha256='a'*64,scene_revision='b'*64,
            units_basis='selected_for_sim',meters_per_unit=1.,targets=[],bounds=[-1.,-.5,3.,3.5],obstacles=[],
            grid=encode_navigation_grid(self.grid()))

    def test_round_trip_negative_origin_row_order_exact_free_mask(self):
        rows=self.grid();encoded=encode_navigation_grid(rows);decoded=decode_navigation_grid(encoded,[-1.,-.5,3.,3.5])
        self.assertEqual(decoded,rows)
        self.assertLess(len(encoded['free_bits']),len(rows))
        self.assertEqual(checked_scene_geometry(self.wire()),self.wire())

    def test_unknown_is_blocked_and_duplicate_missing_offcenter_rejected(self):
        rows=self.grid();rows[0][2]='unknown'
        self.assertEqual(decode_navigation_grid(encode_navigation_grid(rows))[0][2],'occupied')
        for change in ('duplicate','hole','center','nan','boolean'):
            bad=deepcopy(rows)
            if change=='duplicate':bad[-1]=bad[0]
            if change=='hole':bad.pop(1)
            if change=='center':bad[0][0]+=.01
            if change=='nan':bad[0][1]=math.nan
            if change=='boolean':bad[0][0]=False
            with self.subTest(change=change),self.assertRaises(ValueError):encode_navigation_grid(bad)

    def test_invalid_wire_shape_hash_padding_size_bounds_and_metadata(self):
        for change in ('missing_grid','tamper','padding','oversize','bounds','source','scene','units','scale','resolution','extra'):
            value=self.wire();g=value['grid']
            if change=='missing_grid':value.pop('grid')
            if change=='tamper':g['free_bits']='A'+g['free_bits'][1:]
            if change=='padding':
                g.update(size=[1,1],origin_cell=[0,0],free_bits=base64.b64encode(b'\x80').decode());value['bounds']=[0,0,.1,.1]
                g['sha256']=canonical_sha256({k:v for k,v in g.items() if k!='sha256'})
            if change=='oversize':g['size']=[101,100]
            if change=='bounds':value['bounds'][0]+=.1
            if change=='source':value['source_sha256']='z'*64
            if change=='scene':value['scene_revision']='a'
            if change=='units':value['units_basis']='measured'
            if change=='scale':value['meters_per_unit']=True
            if change=='resolution':g['resolution_m']=.2
            if change=='extra':value['auto_motion']=True
            with self.subTest(change=change):self.assertIsNone(checked_scene_geometry(value))

    def test_legacy_wire_still_exact_and_import_mask_changes_same_plan(self):
        self.assertIsNotNone(checked_scene_geometry(dict(epoch=1,targets=[],bounds=[0,0,3,3],obstacles=[])))
        targets=[dict(id='sofa',kind='sofa',label='sofa',bounds=[2.1,.3,2.6,.8])]
        start=[.1,.3,0.]  # Interior of the left arm; right arm is blocked.
        # A larger scene keeps both starts/goal within the original .25m envelope.
        rows=[[(x+.5)*.1,(y+.5)*.1,'occupied' if 8<=x<=17 and y<18 else 'free',0,0,0,0]
            for y in range(-5,30) for x in range(-5,30)]
        bounds=[-.5,-.5,3.,3.]
        direct=approach_plan(start,'sofa',targets,bounds,[])
        self.assertLess(direct['path_length_m'],3.)
        try:masked=approach_plan(start,'sofa',targets,bounds,[],observed_cells=decode_navigation_grid(encode_navigation_grid(rows),bounds))
        except ValueError:return  # No bounded approach is a legitimate terminal result.
        self.assertGreater(masked['path_length_m'],direct['path_length_m'])

    def test_fleet_mask_cache_and_immutable_epoch_survive_invalid_gap_and_downgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            broker=Broker();broker.state=deepcopy(broker.state)
            broker.state['snapshot']['applied_revision']='b'*64
            fleet=RobotFleet(broker,Path(directory),clock=lambda:100.)
            def report(value):
                fleet.engine_exchange('engine','stage',dict(engine_session_id='engine',stage_epoch='stage',
                    report=dict(applied_revision='b'*64,robots=[],scene_geometry=value,produced_monotonic_s=100.)))
            a=self.wire();b=deepcopy(a);b['targets']=[dict(id='chair',kind='chair',label='chair',bounds=[0,0,.1,.1])]
            try:
                with patch('twinpulse_core.navigation_grid.decode_navigation_grid',wraps=decode_navigation_grid) as decode:
                    report(a);first=fleet.navigation_scene['observed_cells'];report(a)
                    self.assertIs(fleet.navigation_scene['observed_cells'],first);self.assertEqual(decode.call_count,1)
                report(b);self.assertIsNone(fleet.navigation_scene)
                report(b);self.assertIsNone(fleet.navigation_scene)
                report(a);self.assertIsNotNone(fleet.navigation_scene)
                report(None);report(b);self.assertIsNone(fleet.navigation_scene)
                legacy={k:a[k] for k in ('epoch','targets','bounds','obstacles')}
                for epoch in (1,1,2,2):
                    legacy['epoch']=epoch;report(legacy);self.assertIsNone(fleet.navigation_scene)
                b['epoch']=2;report(b);self.assertIsNotNone(fleet.navigation_scene)
                report(a);self.assertIsNone(fleet.navigation_scene) # Older accepted epoch cannot be replayed.
                broker.navigation_source=lambda revision:dict(source_sha256='c'*64,units_basis='selected_for_sim',meters_per_unit=1.)
                report(b);self.assertIsNone(fleet.navigation_scene)
                broker.navigation_source=lambda revision:dict(source_sha256='a'*64,units_basis='selected_for_sim',meters_per_unit=1.)
                report(b);self.assertIsNotNone(fleet.navigation_scene)
            finally:fleet.close()


if __name__=='__main__':unittest.main()
