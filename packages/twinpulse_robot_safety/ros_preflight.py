# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free check of the exact ROS namespace arguments used by stationary.sh."""
import json


def check(rclpy):
    args = ['--ros-args', '-r', '__ns:=/tp_guard_stationary', '-p', 'namespace:=""']
    rclpy.init(args=args)
    node = None
    try:
        node = rclpy.create_node('twinpulse_parameter_probe')
        value = node.declare_parameter('namespace').value
        if node.get_namespace() != '/tp_guard_stationary' or value != '':
            raise ValueError('ROS_NAMESPACE_OVERRIDE_MISMATCH')
        return {'status': 'ROS_ARGUMENTS_VERIFIED', 'topic_namespace': node.get_namespace(),
                'vendor_frame_prefix': value, 'motion_authorized': False}
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def main():
    import rclpy
    print('TWINPULSE_ROS_PREFLIGHT=' + json.dumps(check(rclpy)), flush=True)


if __name__ == '__main__':
    main()
