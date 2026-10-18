#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
# Existing Linux Python/g++ only. No SSH, ROS driver, serial or installation.
set -eo pipefail
tp_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
mkdir -p "$tp_root/artifacts/robot-offline"
tp_out="$(mktemp -d "$tp_root/artifacts/robot-offline/run-XXXXXXXX")"
exec > >(tee "$tp_out/checks.log") 2>&1
cd "$tp_root"
printf 'OFFLINE_ONLY output=%s\n' "$tp_out"
python3 -B -m unittest discover -s tests/integration -p 'test_robot*.py' -v
python3 -B packages/twinpulse_robot_safety/tests/runtime_test.py -v
python3 -B packages/twinpulse_robot_safety/tests/stationary_test.py -v
g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  -I packages/twinpulse_robot_safety/include \
  packages/twinpulse_robot_safety/tests/command_guard_test.cpp -o "$tp_out/command_guard_test"
"$tp_out/command_guard_test"
g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
  packages/twinpulse_robot_safety/trial/battery_policy_test.cpp -o "$tp_out/battery_policy_test"
"$tp_out/battery_policy_test"
python3 -B scripts/prepare_robot.py --mode offline
printf 'OFFLINE_CHECKS_PASS; ARM64/ROS/hardware validation NOT_RUN\n'
