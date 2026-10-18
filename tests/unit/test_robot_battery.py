# SPDX-License-Identifier: Apache-2.0
import unittest
from twinpulse_core.robot_battery import battery_estimate,battery_display_config,checked_battery_display,battery_display_estimate
from copy import deepcopy


class RobotBatteryTests(unittest.TestCase):
    def test_custom_piecewise_mapping_clamp_and_voltage_only(self):
        config=battery_display_config('custom');config['label']='Test measured table'
        config['points']=[dict(voltage_v=10,percent=0),dict(voltage_v=11,percent=20),dict(voltage_v=12,percent=100)]
        for v,p in ((9,0),(10.5,10),(11,20),(11.5,60),(13,100)):
            self.assertEqual(battery_display_estimate(v,config)['estimated_percent'],p)
        self.assertIsNone(battery_display_estimate(11.34,battery_display_config())['estimated_percent'])
        result=battery_display_estimate(11.34,battery_display_config('robotis_opencr'))
        self.assertEqual(result['estimated_percent'],46.7);self.assertEqual(len(result['display_config_sha256']),64)
        self.assertIsNone(battery_display_estimate(30,battery_display_config('robotis_opencr'))['estimated_percent'])
        self.assertEqual(battery_estimate(11.1)['voltage_protection'],'LOW_VOLTAGE_GUARD')

    def test_reject_invalid_mapping_and_forged_preset(self):
        custom=battery_display_config('custom');custom['points']=[dict(voltage_v=10,percent=0),dict(voltage_v=12,percent=100)]
        variants=[]
        for key,value in (('voltage_v',10),('voltage_v',float('nan')),('voltage_v',True),('percent',99)):
            row=deepcopy(custom);row['points'][-1][key]=value;variants.append(row)
        for points in ([],custom['points'][::-1],custom['points']*17):
            row=deepcopy(custom);row['points']=points;variants.append(row)
        row=battery_display_config('robotis_opencr');row['points'][0]['voltage_v']=9;variants.append(row)
        row=deepcopy(custom);row['source']='x\ny';variants.append(row)
        for row in variants:
            with self.subTest(row=row),self.assertRaises(ValueError):checked_battery_display(row)
    def test_official_display_mapping_and_user_reserve(self):
        for voltage,percent in ((10.5,0),(10.86,20),(11.1,33.3),(11.34,46.7),(11.4,50),(12.3,100),(12.6,100)):
            with self.subTest(voltage=voltage):
                result=battery_estimate(voltage)
                self.assertEqual(result['estimated_percent'],percent)
                self.assertEqual(result['capacity_measured'],False)
        self.assertEqual(battery_estimate(10.86)['reserve_state'],'AT_OR_BELOW_RESERVE')
        self.assertEqual(battery_estimate(11.1)['voltage_protection'],'LOW_VOLTAGE_GUARD')
        self.assertEqual(battery_estimate(11.34)['voltage_protection'],'CLEAR')

    def test_unknown_nonfinite_and_invalid_voltage_never_become_percent(self):
        for value in (None,True,'11.4',float('nan'),float('inf'),0,-1,30):
            result=battery_estimate(value)
            self.assertIsNone(result['estimated_percent'])
            self.assertEqual(result['reserve_state'],'UNKNOWN')


if __name__=='__main__':unittest.main()
