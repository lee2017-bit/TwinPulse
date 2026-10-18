"""Device-free boundary regressions, not physical sensor/motion acceptance."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('sensor_only',Path(__file__).parents[2]/'scripts/robot_sensor_only_trial.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class SensorOnlyTest(unittest.TestCase):
    def board(self,**changes):
        return dict(status='OBSERVED',port_restored=True,torque_enabled=True,
                    wheel_velocity_raw=[0,0],command_bytes_zero=True,
                    near_board_protection=False,encoders=[100,200])|changes

    def test_torque_on_is_not_drive_or_deenergized_qualification(self):
        module.require_sensor_stationary(self.board())
        module.require_sensor_stationary(self.board(torque_enabled=False))

    def test_every_zero_and_restoration_condition_is_required(self):
        for changes in ({'status':'UNKNOWN'},{'port_restored':False},{'torque_enabled':None},
                        {'wheel_velocity_raw':[0,1]},{'command_bytes_zero':False},
                        {'near_board_protection':True},{'encoders':[]}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                module.require_sensor_stationary(self.board(**changes))

    def test_stable_encoders_required(self):
        with self.assertRaisesRegex(ValueError,'DISPLACEMENT'):
            module.require_sensor_stationary(self.board(encoders=[103,200]),self.board())

    def test_after_error_cannot_be_success(self):
        value=dict(final_stationary_checked=True,scan_count=3,finite_valid_beams=50,
                   raw_ros={'complete':True},cleanup={'sensor_stop':dict(
                       write_complete=True,quiet_after_1s=True,port_restored=True)})
        self.assertTrue(module.trial_success(value))
        for key in ('error','after_error','cleanup_error'):
            with self.subTest(key=key):self.assertFalse(module.trial_success(value|{key:'FAILED'}))
        self.assertFalse(module.trial_success(value|{'final_stationary_checked':False}))
        self.assertFalse(module.trial_success(value|{'cleanup':{'error':'FAILED'}}))


if __name__=='__main__':unittest.main()
