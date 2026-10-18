// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#include "battery_policy.hpp"
#include <iostream>
#include <limits>
int main() {
  using namespace twinpulse_test_policy;
  int checks=0;
  auto check=[&](bool ok) { ++checks; if(!ok) { std::cerr<<"FAIL "<<checks<<"\n"; std::exit(1); } };
  check(!above_charge_threshold(10.85f));
  check(!above_charge_threshold(10.86f));
  check(above_charge_threshold(10.87f));
  check(above_charge_threshold(11.4f));
  check(estimated_percent(11.4f)==50.0);
  check(std::abs(estimated_percent(11.45f)-52.7777777778)<1e-6);
  check(estimated_percent(10.86f)==20.0);
  check(estimated_percent(12.6f)==100.0);
  check(estimated_percent(10.0f)==0.0);
  check(!above_charge_threshold(std::numeric_limits<float>::quiet_NaN()));
  check(!above_charge_threshold(std::numeric_limits<float>::infinity()));
  check(!above_charge_threshold(-1.0f));
  check(!above_charge_threshold(13.1f));
  for(int cv=1000;cv<=1300;++cv) {
    const float v=cv/100.0f;
    check(centivolts(v)==cv);
    check(above_charge_threshold(v)==(cv>1086));
  }
  std::cout<<"PASS "<<checks<<" battery policy checks; no ROS/device access\n";
}
