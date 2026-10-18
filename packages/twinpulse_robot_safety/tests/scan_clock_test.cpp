// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Build in the prepared source: g++ -std=c++17 -Wall -Wextra -Werror
// -I include offline_tests/scan_clock_test.cpp -o scan_clock_test
// No ROS, serial, SDK or devices are used by this contract harness.
#include "coin_d4_driver/scan_clock_contract.hpp"
#include <cassert>
#include <string>
using robotis::coin_d4::scan_contract;
int main() {
  const auto a=scan_contract(1000000000ULL,1100000000ULL,1120000000ULL,
    2120000000LL,{0.,.01,.02},INT64_MIN);
  assert(a.stamp_ns==2000000000LL);
  assert(a.time_increment>0. && a.angle_increment>0.);
  const auto b=scan_contract(1000000000ULL,1100000000ULL,1120000000ULL,
    2120000000LL,{.02,.01,0.},1000000000LL);
  assert(b.time_increment==a.time_increment && b.angle_increment<0.);
  const auto wrap=scan_contract(1000000000ULL,1100000000ULL,1120000000ULL,
    2120000000LL,{6.28, .006814692820414, .016814692820414},INT64_MIN);
  assert(wrap.last_angle>6.28);
  auto fails=[](uint64_t start,uint64_t end,uint64_t now,int64_t ros,
               std::vector<double> angles,int64_t offset,const char * reason) {
    try {scan_contract(start,end,now,ros,angles,offset);assert(false);}
    catch(const std::runtime_error & error){assert(std::string(error.what())==reason);}
  };
  fails(110,100,120,1000,{0.,.01},INT64_MIN,"SCAN_CLOCK_DOMAIN_WRAP_OR_LATENCY");
  fails(UINT64_MAX-5,UINT64_MAX,2,1000,{0.,.01},INT64_MIN,"SCAN_CLOCK_DOMAIN_WRAP_OR_LATENCY");
  fails(100,110,120,1,{0.,.01},INT64_MIN,"SCAN_ROS_CLOCK_UNDERFLOW");
  fails(100,110,120,1000000000,{0.,.01},0,"SCAN_ROS_CLOCK_JUMP");
  fails(100,110,120,1000,{0.,.01,.05},INT64_MIN,"SCAN_NONUNIFORM_BEAM_GRID");
  fails(100,110,120,1000,{0.,.01,0.},INT64_MIN,"SCAN_ANGLE_ORDER_OR_SPAN");
  return 0;
}
