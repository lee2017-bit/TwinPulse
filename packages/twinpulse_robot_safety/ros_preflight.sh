#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
# ROS argument parsing only; no robot device, publisher, service or motor call.
set -eo pipefail
tp_release="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=86 ROS_LOCALHOST_ONLY=1
exec python3 -B "$tp_release/ros_preflight.py"
