# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reviewed compiled COIN source, shared by manual control and scan collection.

Importing this module does not contact hardware or load a driver. These pins
identify compiled artifacts, not calibrated timing, geometry or motion approval.
"""
from pathlib import Path

CANDIDATE = Path('/home/twinpulse/.local/share/twinpulse/robot/candidates/coin-time-build-20261006T125707Z-30d7bdc2')
BINARY = CANDIDATE / 'build/single_coin_d4_node'
BINARY_SHA256 = 'd2e06c51786963ec828993faea2a91048dcac0e826145af0d738cf847f65b9c9'
DRIVER_LIB = CANDIDATE / 'build/libcoin_d4_driver_lib.so'
DRIVER_LIB_SHA256 = '4c3ac61f023eb90f8bce4376dcce8cc22339e791a44a7e573f048d2980452d6b'
SOURCE_SHA256 = '0ac6ccd380d8d146828cf28334bb17e20d58aa2c3c046aa27f6a1e83c3f30e16'
TIMING_BASIS = 'HOST_SYNC_APPROXIMATE_NOT_HARDWARE_FIRST_RAY'
DEVICE = '/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0'


def description():
    return {'schema':'coin-driver-identity-1.0','binary':BINARY.as_posix(),
            'binary_sha256':BINARY_SHA256,'library':DRIVER_LIB.as_posix(),
            'library_sha256':DRIVER_LIB_SHA256,'source_sha256':SOURCE_SHA256,
            'timing_basis':TIMING_BASIS,'physical_verified':False}
