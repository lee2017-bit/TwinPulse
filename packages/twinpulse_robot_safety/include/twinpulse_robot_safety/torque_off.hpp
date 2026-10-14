// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#pragma once
#include <cstdint>
#include <cstring>

// One-shot de-energization only. No heartbeat, velocity or torque-enable API.
// IO failures throw; there is deliberately no retry or re-enable rollback.
namespace twinpulse {
inline uint32_t off_u32(const uint8_t* p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8 |
         uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
inline void off_require(bool ok) { if (!ok) throw "torque-off precondition/readback failed"; }
inline bool off_zero(const uint8_t* p, unsigned n) {
  for (unsigned i=0; i<n; ++i) if (p[i]) return false;
  return true;
}
struct TorqueOffObservation {
  bool encoder_changed = false;
  unsigned disconnect_waits = 0;
  // OFF acknowledgement is never a stopping/motion qualification.
  bool motion_qualified = false;
};
template<class IO> TorqueOffObservation disable_torque_once(IO& io) {
  TorqueOffObservation observation;
  uint8_t id[9]{}, state[5]{}, volts[4]{}, motors[2]{}, buttons[2]{};
  uint8_t commands[24]{}, before[16]{}, sample[16]{};
  io.read(0,9,id);
  off_require(id[0]==0 && id[1]==0x50 && off_u32(id+2)==1 && id[6]==5 && id[7]==200);
  auto gates = [&](bool awaiting_disconnect = false) {
    io.read(14,5,state);  // debug=0, host disconnected, device status=0
    off_require(state[0]==0 && state[4]==0);
    off_require(state[1]==0 || (awaiting_disconnect && state[1]==1));
    io.read(42,4,volts); off_require(off_u32(volts)>=1110 && off_u32(volts)<=1265);
    io.read(148,2,motors); off_require(motors[0]==1 && motors[1]<=1);
    io.read(26,2,buttons); off_require(off_zero(buttons,2));
    io.read(150,24,commands); off_require(off_zero(commands,24));
    io.read(128,16,sample); off_require(off_zero(sample,8));
  };
  // ROS process exit and the firmware host-connection flag are asynchronous.
  // Observe only: no heartbeat/velocity/enable writes and no retry of failed IO.
  // Every sample still checks zero velocity/commands and all other gates.
  // 10 x 200ms is a bounded handover budget, NOT a stopping-time allowance.
  gates(true);
  while (state[1]==1 && observation.disconnect_waits<10) {
    io.wait(); ++observation.disconnect_waits; gates(true);
  }
  if (state[1]!=0) throw "HOST_DISCONNECT_TIMEOUT";
  std::memcpy(before,sample,16);
  io.wait(); gates();
  // Encoder stability belongs to stop qualification, not permission to remove
  // motor power on an operator-confirmed flat floor. Record every difference;
  // do not turn it into a movement PASS or adjust any driving/settling threshold.
  observation.encoder_changed = std::memcmp(before+8,sample+8,8)!=0;
  // Hard-coded IO method sends exactly address 149, one byte, value zero.
  if (motors[1]) io.disable();
  for (int i=0; i<3; ++i) {
    io.wait(); gates(); off_require(motors[1]==0);
    observation.encoder_changed |= std::memcmp(before+8,sample+8,8)!=0;
  }
  return observation;
}
}
