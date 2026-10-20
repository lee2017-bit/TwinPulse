// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#pragma once
#include <cmath>
#include <cstdint>
#include <functional>
#include <stdexcept>

namespace twinpulse_robot_safety {
// Single-thread-owned final-output gate. Times are milliseconds; no hardware dependency.
// Software protection only, not an emergency-stop safety certification.
class CommandGuard {
 public:
  using VelocityWriter = std::function<bool(int32_t, int32_t)>;
  using HeartbeatWriter = std::function<bool(uint8_t)>;
  static constexpr int64_t timeout_ms = 400;
  static constexpr double max_linear = 0.05, max_angular = 0.30;
  CommandGuard(VelocityWriter velocity, HeartbeatWriter heartbeat, int64_t configured_timeout_ms = timeout_ms)
      : velocity_(velocity), heartbeat_(heartbeat), configured_timeout_ms_(configured_timeout_ms) {
    if (configured_timeout_ms < 150 || configured_timeout_ms > 2000)
      throw std::invalid_argument("output timeout outside reviewed configuration bounds");
  }
  int64_t configured_timeout_ms() const { return configured_timeout_ms_; }
  bool armed() const { return armed_; }
  bool io_fault() const { return io_fault_; }
  const char* reason() const { return reason_; }
  // Caller establishes a single authorized source. This NEVER enables motor torque.
  bool arm(int64_t steady_ms, int64_t ros_ms) {
    if (armed_ || io_fault_ || ros_ms <= 0) return false;
    if (!write_zero()) return false;
    armed_ = true;
    reason_ = "armed_waiting_for_command";
    arm_ros_ms_ = last_stamp_ms_ = last_ros_ms_ = ros_ms;
    deadline_ms_ = steady_ms + configured_timeout_ms_;
    return true;
  }
  void latch(const char* reason) {
    armed_ = false;
    linear_ = angular_ = 0;
    if (!io_fault_) reason_ = reason;
  }
  bool receive(double linear, double angular, int64_t stamp_ms,
               int64_t ros_ms, int64_t steady_ms) {
    expire(steady_ms);
    if (!armed_) return false;
    if (!std::isfinite(linear) || !std::isfinite(angular) ||
        std::abs(linear) > max_linear || std::abs(angular) > max_angular) {
      latch("invalid_or_excess_velocity"); return false;
    }
    if (ros_ms < last_ros_ms_ || stamp_ms <= arm_ros_ms_ ||
        stamp_ms <= last_stamp_ms_ || stamp_ms > ros_ms ||
        ros_ms - stamp_ms >= configured_timeout_ms_) {
      latch("stale_replayed_or_invalid_stamp"); return false;
    }
    last_ros_ms_ = ros_ms;
    last_stamp_ms_ = stamp_ms;
    // Source age reduces remaining lifetime; network delay cannot extend it.
    deadline_ms_ = steady_ms + configured_timeout_ms_ - (ros_ms - stamp_ms);
    linear_ = static_cast<int32_t>(linear * 100.0);
    angular_ = static_cast<int32_t>(angular * 100.0);
    reason_ = "active";
    return true;
  }
  void tick(int64_t steady_ms) {
    expire(steady_ms);
    if (io_fault_) { velocity_(0, 0); return; }
    if (!velocity_(linear_, angular_)) { fail_io(); velocity_(0, 0); return; }
    // Heartbeat is downstream of successful output in the SAME execution path.
    if (!heartbeat_started_ || steady_ms - last_heartbeat_ms_ >= 100) {
      if (!heartbeat_(heartbeat_count_++)) { fail_io(); velocity_(0, 0); return; }
      heartbeat_started_ = true;
      last_heartbeat_ms_ = steady_ms;
    }
  }
  bool stop() { latch("explicit_stop"); return write_zero(); }
 private:
  void expire(int64_t now) { if (armed_ && now >= deadline_ms_) latch("command_timeout"); }
  void fail_io() {
    armed_ = false; io_fault_ = true; reason_ = "io_fault_restart_required";
    linear_ = angular_ = 0;
  }
  bool write_zero() {
    linear_ = angular_ = 0;
    if (!velocity_(0, 0)) { fail_io(); return false; }
    return !io_fault_;
  }
  VelocityWriter velocity_;
  HeartbeatWriter heartbeat_;
  const int64_t configured_timeout_ms_;
  bool armed_ = false, io_fault_ = false, heartbeat_started_ = false;
  const char* reason_ = "startup_disarmed";
  int32_t linear_ = 0, angular_ = 0;
  int64_t deadline_ms_ = 0, arm_ros_ms_ = 0, last_stamp_ms_ = 0;
  int64_t last_ros_ms_ = 0, last_heartbeat_ms_ = 0;
  uint8_t heartbeat_count_ = 0;
};
}  // namespace twinpulse_robot_safety
