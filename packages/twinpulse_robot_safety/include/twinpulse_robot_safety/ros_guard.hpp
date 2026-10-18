// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#pragma once
#include <chrono>
#include <array>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <rclcpp/rclcpp.hpp>
#include <turtlebot3_node/dynamixel_sdk_wrapper.hpp>
#include "command_guard.hpp"

namespace twinpulse_robot_safety {
// Owned by official base node on SingleThreadedExecutor. No separate heartbeat timer.
class RosGuard {
 public:
  using SDK = robotis::turtlebot3::DynamixelSDKWrapper;
  RosGuard(rclcpp::Node::SharedPtr node, std::shared_ptr<SDK> sdk)
      : node_(node), sdk_(sdk), guard_(
          [this](int32_t v, int32_t w) { return write_velocity(v, w); },
          [this](uint8_t count) {
            std::string message;
            return sdk_->set_data_to_device(19, 1, &count, &message);
          }) {
    if (node_->get_parameter("use_sim_time").as_bool())
      throw std::runtime_error("Physical command guard rejects use_sim_time");
    if (!guard_.stop()) throw std::runtime_error("Startup zero write failed");
    status_ = node_->create_publisher<std_msgs::msg::String>("motion_guard/status", 1);
    command_ = node_->create_subscription<geometry_msgs::msg::TwistStamped>(
        "guarded_cmd_vel", rclcpp::QoS(1).reliable().durability_volatile(),
        [this](geometry_msgs::msg::TwistStamped::SharedPtr msg, const rclcpp::MessageInfo& info) {
          if (shutdown_) return;
          const auto& gid = info.get_rmw_message_info().publisher_gid;
          if (node_->count_publishers("guarded_cmd_vel") != 1) {
            guard_.latch("command_source_count");
          } else if (guard_.armed() && source_bound_ &&
                     std::memcmp(source_.data(), gid.data, source_.size()) != 0) {
            guard_.latch("command_source_changed");
          } else if (msg->header.frame_id != "base_link" ||
                     msg->twist.linear.y != 0 || msg->twist.linear.z != 0 ||
                     msg->twist.angular.x != 0 || msg->twist.angular.y != 0 ||
                     msg->header.stamp.sec < 0 || msg->header.stamp.nanosec >= 1000000000u) {
            guard_.latch("invalid_frame_or_axes");
          } else {
            if (guard_.armed() && !source_bound_) {
              std::memcpy(source_.data(), gid.data, source_.size()); source_bound_ = true;
            }
            const int64_t stamp = int64_t(msg->header.stamp.sec) * 1000 +
                                  msg->header.stamp.nanosec / 1000000;
            guard_.receive(msg->twist.linear.x, msg->twist.angular.z,
                           stamp, node_->now().nanoseconds() / 1000000, steady_ms());
          }
          guard_.tick(steady_ms());
        });
    arm_ = node_->create_service<std_srvs::srv::Trigger>("motion_guard/arm",
        [this](std_srvs::srv::Trigger::Request::SharedPtr,
               std_srvs::srv::Trigger::Response::SharedPtr response) {
          response->success = !shutdown_ && node_->count_publishers("guarded_cmd_vel") == 1 &&
              guard_.arm(steady_ms(), node_->now().nanoseconds() / 1000000);
          if (response->success) source_bound_ = false;
          response->message = response->success ? "armed; torque unchanged" : "arm rejected";
        });
    stop_ = node_->create_service<std_srvs::srv::Trigger>("motion_guard/stop",
        [this](std_srvs::srv::Trigger::Request::SharedPtr,
               std_srvs::srv::Trigger::Response::SharedPtr response) {
          response->success = guard_.stop(); response->message = guard_.reason();
        });
    timer_ = node_->create_wall_timer(std::chrono::milliseconds(20), [this]() {
      if (guard_.armed() && node_->count_publishers("guarded_cmd_vel") != 1)
        guard_.latch("command_source_count");
      guard_.tick(steady_ms());
      std_msgs::msg::String status;
      status.data = guard_.reason(); status_->publish(status);
    });
  }
  ~RosGuard() { stop(); }
  void stop() noexcept {
    shutdown_ = true;
    if (timer_) timer_->cancel();
    try { guard_.stop(); } catch (...) { /* no future heartbeat */ }
  }
 private:
  static int64_t steady_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
  }
  bool write_velocity(int32_t v, int32_t w) {
    // Pinned Burger protocol2 control table. Never touches torque149.
    union { int32_t words[6]; uint8_t bytes[24]; } data{};
    data.words[0] = v; data.words[5] = w;
    std::string message;
    return sdk_->set_data_to_device(150, 24, data.bytes, &message);
  }
  rclcpp::Node::SharedPtr node_;
  std::shared_ptr<SDK> sdk_;
  CommandGuard guard_;
  std::array<uint8_t, RMW_GID_STORAGE_SIZE> source_{};
  bool source_bound_ = false;
  bool shutdown_ = false;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Subscription<geometry_msgs::msg::TwistStamped>::SharedPtr command_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr arm_, stop_;
};
}  // namespace twinpulse_robot_safety
