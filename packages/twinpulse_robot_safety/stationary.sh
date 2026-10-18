#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
# Fixed disarmed check only. Not a general command/launch interface.
set -eo pipefail
tp_release="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=86 ROS_LOCALHOST_ONLY=1
case "${1:-}" in
  base)
    exec "$tp_release/bin/turtlebot3_ros" \
      -i /dev/serial/by-id/usb-ROBOTIS_OpenCR_Virtual_ComPort_in_FS_Mode_FFFFFFFEFFFF-if00 \
      --ros-args --params-file "$tp_release/burger.yaml" \
      -r __ns:=/tp_guard_stationary -p 'namespace:=""'
    ;;
  observe)
    test "$#" -eq 2
    exec python3 -B "$tp_release/stationary_observer.py" "$2"
    ;;
  *) exit 2 ;;
esac
