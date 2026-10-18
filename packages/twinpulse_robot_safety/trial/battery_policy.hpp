// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#pragma once
#include <algorithm>
#include <cmath>
namespace twinpulse_test_policy {
// User-selected charging threshold; not a measured SOC or firmware cutoff.
// Vendor public estimate: (V - 10.5) / (12.3 - 10.5) * 100.
// OpenCR's independent ~11.0V protection remains unchanged and takes priority.
constexpr int charge_threshold_percent=20;
constexpr int charge_threshold_centivolts=1086;
inline int centivolts(float volts) {
  if(!std::isfinite(volts) || volts<0 || volts>13.0f) return -1;
  return static_cast<int>(std::lround(static_cast<double>(volts)*100.0));
}
inline double estimated_percent(float volts) {
  const int cv=centivolts(volts);
  if(cv<0) return -1;
  return std::clamp((cv-1050)*100.0/180.0,0.0,100.0);
}
inline bool above_charge_threshold(float volts) {
  return centivolts(volts)>charge_threshold_centivolts;
}
}
