// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <stdexcept>
namespace robotis { namespace turtlebot3 {
// Compile-time replacement for RosGuard integration test. NO device or serial API.
class DynamixelSDKWrapper {
 public:
  struct Write { uint16_t address; int32_t linear, angular; };
  std::vector<Write> writes;
  bool fail = false;
  bool set_data_to_device(const uint16_t& addr, const uint16_t& len,
                          uint8_t* bytes, std::string* result) {
    int32_t v=0,w=0;
    if (addr == 150 && len == 24) {
      std::memcpy(&v, bytes, 4); std::memcpy(&w, bytes+20, 4);
    } else if (!(addr == 19 && len == 1)) {
      throw std::runtime_error("Unexpected output register");
    }
    writes.push_back({addr,v,w}); *result="fake"; return !fail;
  }
  int32_t last_velocity() const {
    for (auto it=writes.rbegin(); it!=writes.rend(); ++it) if(it->address==150) return it->linear;
    return 0;
  }
  unsigned heartbeats() const {
    unsigned n=0; for(const auto& w:writes) if(w.address==19) ++n; return n;
  }
};
}}
