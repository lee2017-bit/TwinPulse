// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#include "twinpulse_robot_safety/ros_guard.hpp"
#include <cstdlib>
#include <iostream>
#include <thread>
using namespace std::chrono_literals;
static unsigned checks=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::cerr<<"FAIL line "<<__LINE__<<": " #x "\n"; std::exit(1); } } while(0)
int main(int argc,char** argv) {
  setenv("ROS_DOMAIN_ID","87",1); setenv("ROS_LOCALHOST_ONLY","1",1);
  rclcpp::init(argc,argv);
  auto node=std::make_shared<rclcpp::Node>("guard", "/twinpulse_guard_fake_only");
  auto client_node=std::make_shared<rclcpp::Node>("test", "/twinpulse_guard_fake_only");
  auto sdk=std::make_shared<twinpulse_robot_safety::RosGuard::SDK>();
  auto guard=std::make_unique<twinpulse_robot_safety::RosGuard>(node,sdk);
  auto publisher=client_node->create_publisher<geometry_msgs::msg::TwistStamped>("guarded_cmd_vel",1);
  auto arm=client_node->create_client<std_srvs::srv::Trigger>("motion_guard/arm");
  auto stop=client_node->create_client<std_srvs::srv::Trigger>("motion_guard/stop");
  std::string status;
  auto subscription=client_node->create_subscription<std_msgs::msg::String>("motion_guard/status",1,
      [&](std_msgs::msg::String::SharedPtr msg){status=msg->data;});
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node); executor.add_node(client_node);
  auto spin=[&](int milliseconds) {
    auto end=std::chrono::steady_clock::now()+std::chrono::milliseconds(milliseconds);
    do { executor.spin_some(); std::this_thread::sleep_for(2ms); } while(std::chrono::steady_clock::now()<end);
  };
  auto call=[&](auto service) {
    CHECK(service->wait_for_service(1s));
    auto future=service->async_send_request(std::make_shared<std_srvs::srv::Trigger::Request>());
    CHECK(executor.spin_until_future_complete(future,1s)==rclcpp::FutureReturnCode::SUCCESS);
    return future.get()->success;
  };
  auto send=[&](double velocity,int age=0,std::string frame="base_link") {
    geometry_msgs::msg::TwistStamped msg;
    msg.header.stamp=client_node->now()-rclcpp::Duration::from_seconds(age/1000.0);
    msg.header.frame_id=frame; msg.twist.linear.x=velocity;
    publisher->publish(msg); spin(40);
  };
  spin(500); CHECK(node->count_publishers("guarded_cmd_vel")==1);
  send(.03); CHECK(sdk->last_velocity()==0); // startup latched
  CHECK(call(arm)); spin(5); send(.03); CHECK(sdk->last_velocity()==3);
  spin(450); CHECK(sdk->last_velocity()==0); CHECK(status=="command_timeout");
  send(.03); CHECK(sdk->last_velocity()==0); // no automatic reconnect/restart
  CHECK(call(arm)); spin(5); send(.03,1000); CHECK(sdk->last_velocity()==0);
  CHECK(status=="stale_replayed_or_invalid_stamp");
  CHECK(call(arm)); spin(5); send(.03,0,"map"); CHECK(sdk->last_velocity()==0);
  CHECK(status=="invalid_frame_or_axes");
  CHECK(call(arm)); spin(5); send(.03); CHECK(sdk->last_velocity()==3);
  CHECK(call(stop)); CHECK(sdk->last_velocity()==0);
  CHECK(call(arm)); spin(5); send(.03);
  auto second=client_node->create_publisher<geometry_msgs::msg::TwistStamped>("guarded_cmd_vel",1);
  spin(200); CHECK(sdk->last_velocity()==0); CHECK(status=="command_source_count"); CHECK(!call(arm));
  second.reset(); spin(200); CHECK(call(arm)); spin(5); send(.03);
  publisher.reset(); spin(200); CHECK(sdk->last_velocity()==0);
  publisher=client_node->create_publisher<geometry_msgs::msg::TwistStamped>("guarded_cmd_vel",1);
  spin(200); send(.03); CHECK(sdk->last_velocity()==0);
  CHECK(call(arm)); spin(5); send(.03); CHECK(sdk->last_velocity()==3);
  sdk->fail=true; spin(40); const auto hb=sdk->heartbeats();
  sdk->fail=false; spin(200); CHECK(sdk->heartbeats()==hb); CHECK(sdk->last_velocity()==0); CHECK(!call(arm));
  guard.reset(); spin(50); CHECK(sdk->last_velocity()==0);
  guard=std::make_unique<twinpulse_robot_safety::RosGuard>(node,sdk);
  spin(100); send(.03); CHECK(sdk->last_velocity()==0); // process-component restart disarmed
  CHECK(call(arm)); spin(5); send(.03); CHECK(sdk->last_velocity()==3);
  guard->stop(); CHECK(sdk->last_velocity()==0);
  const auto stopped_hb=sdk->heartbeats(); spin(150); CHECK(sdk->heartbeats()==stopped_hb);
  send(.03); CHECK(sdk->last_velocity()==0); CHECK(sdk->heartbeats()==stopped_hb);
  CHECK(!call(arm));
  guard.reset(); rclcpp::shutdown();
  std::cout<<"PASS "<<checks<<" ROS integration checks (FAKE SDK, NO hardware)\n";
}
