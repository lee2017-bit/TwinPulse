// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// One explicitly authorized straight-line command-expiry test, not teleoperation.
// Fixed speed/duration/domain/namespace. No serial SDK or firmware writes here.
#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <std_srvs/srv/set_bool.hpp>
#include <turtlebot3_msgs/msg/sensor_state.hpp>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <fcntl.h>
#include <unistd.h>
#include <iostream>
#include <stdexcept>
#include <thread>
#include "battery_policy.hpp"
#ifdef TP_FAKE
#include "twinpulse_robot_safety/ros_guard.hpp"
#endif
using namespace std::chrono_literals;
using Trigger=std_srvs::srv::Trigger;
using Power=std_srvs::srv::SetBool;
using Sensor=turtlebot3_msgs::msg::SensorState;
static volatile std::sig_atomic_t interrupted=0;
static void on_signal(int) { interrupted=1; }
static int64_t ms() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}
static void require(bool value,const char* message) {
  if(!value) throw std::runtime_error(message);
}
class Probe {
 public:
  Probe(rclcpp::Node::SharedPtr node,rclcpp::executors::SingleThreadedExecutor& ex)
      : n(node),e(ex) {
    pub=n->create_publisher<geometry_msgs::msg::TwistStamped>("guarded_cmd_vel",1);
    arm=n->create_client<Trigger>("motion_guard/arm");
    stop=n->create_client<Trigger>("motion_guard/stop");
    power=n->create_client<Power>("motor_power");
    ss=n->create_subscription<Sensor>("sensor_state",rclcpp::SensorDataQoS(),
      [this](Sensor::SharedPtr s) {
        // Observed disabled hardware jitters by one encoder tick. A fixed
        // two-tick anchor band (~0.10mm nominal) tolerates quantization, not
        // accumulating motion: crossing the band resets the stable interval.
        if(std::abs(int64_t(s->left_encoder)-anchor_left)>2 ||
           std::abs(int64_t(s->right_encoder)-anchor_right)>2) {
          last_change=ms(); anchor_left=s->left_encoder; anchor_right=s->right_encoder;
        }
        sensor=*s; received=ms(); ++samples;
        if(log_motion) std::cout<<"SENSOR t="<<received-start<<" left="<<s->left_encoder
          <<" right="<<s->right_encoder<<" torque="<<s->torque<<" V="<<s->battery<<std::endl;
      });
    st=n->create_subscription<std_msgs::msg::String>("motion_guard/status",1,
      [this](std_msgs::msg::String::SharedPtr s) {
        if(status!=s->data) std::cout<<"STATUS "<<s->data<<" steady_ms="<<ms()<<std::endl;
        status=s->data; status_time=ms();
      });
  }
  void spin(int duration) {
    const auto end=ms()+duration;
    do { require(!interrupted,"operator signal"); e.spin_some(); std::this_thread::sleep_for(2ms); }
    while(ms()<end);
  }
  bool trigger(rclcpp::Client<Trigger>::SharedPtr c) {
    if(!c->service_is_ready()) return false;
    auto f=c->async_send_request(std::make_shared<Trigger::Request>());
    return e.spin_until_future_complete(f,500ms)==rclcpp::FutureReturnCode::SUCCESS && f.get()->success;
  }
  bool torque(bool value) {
    if(!power->service_is_ready()) return false;
    auto q=std::make_shared<Power::Request>(); q->data=value;
    auto f=power->async_send_request(q);
    return e.spin_until_future_complete(f,500ms)==rclcpp::FutureReturnCode::SUCCESS && f.get()->success;
  }
  void fresh() {
    require(samples>=3 && ms()-received<200 && ms()-status_time<200,"telemetry stale");
    const auto age=(n->now()-rclcpp::Time(sensor.header.stamp)).seconds();
    require(age>=0 && age<.2,"sensor source timestamp stale");
    require(twinpulse_test_policy::above_charge_threshold(sensor.battery),
            "estimated battery at/below user charging threshold 20% or invalid");
    require(sensor.button==0,"board drive button pressed");
    require(n->count_publishers("guarded_cmd_vel")==1 && pub->get_subscription_count()==1,
            "unexpected command endpoints");
  }
  void preflight() {
    const auto deadline=ms()+12000;
    while(ms()<deadline && (samples<10 || !arm->service_is_ready() ||
          !stop->service_is_ready() || !power->service_is_ready() || pub->get_subscription_count()!=1))
      spin(20);
    // DDS discovery may deliver queued samples in one burst. Observe an actual
    // steady-clock stationary interval, independent of that initial sample count.
    spin(250);
    fresh(); require(status=="explicit_stop","not disarmed at startup");
    require(!sensor.torque,"motors not initially disabled");
    require(ms()-last_change>=200,"encoders not stationary");
    left=sensor.left_encoder; right=sensor.right_encoder;
    std::cout<<"PREFLIGHT V="<<sensor.battery<<" estimated_percent="
      <<twinpulse_test_policy::estimated_percent(sensor.battery)
      <<" left="<<left<<" right="<<right<<std::endl;
  }
  void run_once() {
    touched=true;
    require(trigger(stop),"initial zero/stop failed");
    require(torque(true),"motor enable failed");
    spin(100); fresh(); require(sensor.torque,"motor enable readback false");
    require(std::abs(int64_t(sensor.left_encoder)-left)<=2 &&
            std::abs(int64_t(sensor.right_encoder)-right)<=2,"movement before arm");
    require(trigger(arm),"arm rejected");
    // Service acknowledgement precedes the next 20ms status publication.
    const auto arm_status_deadline=ms()+100;
    while(status!="armed_waiting_for_command" && ms()<arm_status_deadline) spin(2);
    require(status=="armed_waiting_for_command","armed status not observed");
    start=ms(); last_send=start; log_motion=true;
    std::cout<<"MOVE fixed_v=0.03 fixed_w=0 publish_window_ms=600 no_repeat"<<std::endl;
    unsigned sent=0;
    while(ms()-start<600) {
      fresh(); require(sensor.torque,"torque lost during motion"); bound();
      require(status=="armed_waiting_for_command" || status=="active","unexpected stop during send");
      geometry_msgs::msg::TwistStamped m;
      m.header.frame_id="base_link"; m.header.stamp=n->now(); m.twist.linear.x=.03;
      pub->publish(m); last_send=ms(); ++sent; spin(50);
    }
    require(sent>0 && status=="active","no active movement");
    std::cout<<"INPUT_SILENT t="<<last_send-start<<" sent="<<sent<<std::endl;
    // Keep publisher alive, send NO zero: specifically test command-age timeout.
    while(ms()-last_send<700 && status!="command_timeout") { spin(10); fresh(); bound(); }
    require(status=="command_timeout","no guard timeout by 700ms; abort");
    std::cout<<"TIMEOUT_OBSERVED after_last_send_ms="<<ms()-last_send<<std::endl;
    const auto expiry_seen=ms();
    while(ms()-expiry_seen<500) { spin(10); fresh(); bound(); require(status=="command_timeout","stop not latched"); }
    require(ms()-last_change>=200,"encoders still changing after timeout");
    require(sensor.left_encoder>left && sensor.right_encoder>right,"forward movement not observed");
    std::cout<<"STOP_STABLE delta_left="<<sensor.left_encoder-left
      <<" delta_right="<<sensor.right_encoder-right<<" V="<<sensor.battery<<std::endl;
  }
  bool cleanup() {
    if(!touched) return true;
    const bool zero=trigger(stop);
    const bool off=torque(false);
    const auto end=ms()+400;
    while(ms()<end) { e.spin_some(); std::this_thread::sleep_for(2ms); }
    const bool readback=ms()-received<200 && !sensor.torque && ms()-last_change>=200;
    std::cout<<"CLEANUP stop_ack="<<zero<<" torque_off_ack="<<off<<" stable_off_readback="<<readback<<std::endl;
    return zero && off && readback;
  }
 private:
  void bound() {
    const auto dl=int64_t(sensor.left_encoder)-left, dr=int64_t(sensor.right_encoder)-right;
    require(dl>=-40 && dr>=-40 && dl<1300 && dr<1300 && std::abs(dl-dr)<350,
            "encoder direction/distance/asymmetry bound exceeded");
  }
  rclcpp::Node::SharedPtr n;
  rclcpp::executors::SingleThreadedExecutor& e;
  rclcpp::Publisher<geometry_msgs::msg::TwistStamped>::SharedPtr pub;
  rclcpp::Client<Trigger>::SharedPtr arm,stop;
  rclcpp::Client<Power>::SharedPtr power;
  rclcpp::Subscription<Sensor>::SharedPtr ss;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr st;
  Sensor sensor{};
  std::string status;
  int64_t received=0,status_time=0,last_change=0,start=0,last_send=0;
  int32_t left=0,right=0;
  int32_t anchor_left=0,anchor_right=0;
  unsigned samples=0;
  bool touched=false,log_motion=false;
};
int main(int argc,char** argv) {
  std::cout.setf(std::ios::unitbuf);
  const bool run=argc==2 && std::string(argv[1])=="--run-once";
  const bool check=argc==2 && std::string(argv[1])=="--check";
#ifdef TP_FAKE
  const bool low=argc==2 && std::string(argv[1])=="--fake-low-battery";
  setenv("ROS_DOMAIN_ID","87",1);
  const char* ns="/tp_guard_probe_fake";
#else
  const bool low=false;
  setenv("ROS_DOMAIN_ID","86",1);
  const char* ns="/tp_guard_stationary";
#endif
  if(!run && !check && !low) { std::cerr<<"Use --check or explicitly authorized --run-once\n"; return 2; }
  setenv("ROS_LOCALHOST_ONLY","1",1);
  rclcpp::init(0,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);
  std::signal(SIGINT,on_signal); std::signal(SIGTERM,on_signal); std::signal(SIGHUP,on_signal);
  rclcpp::executors::SingleThreadedExecutor ex;
  auto node=std::make_shared<rclcpp::Node>("bounded_stop_probe",ns); ex.add_node(node);
#ifdef TP_FAKE
  auto base=std::make_shared<rclcpp::Node>("fake_base",ns); ex.add_node(base);
  auto sdk=std::make_shared<twinpulse_robot_safety::RosGuard::SDK>();
  twinpulse_robot_safety::RosGuard guard(base,sdk);
  // Exercise the exact 20% boundary and the formerly rejected 11.40V case.
  Sensor s; s.battery=low?10.86f:11.4f; s.left_encoder=930; s.right_encoder=4648;
  unsigned enables=0;
  auto power=base->create_service<Power>("motor_power",[&](Power::Request::SharedPtr q,Power::Response::SharedPtr p){
    s.torque=q->data; if(q->data) ++enables; p->success=true;
  });
  auto sp=base->create_publisher<Sensor>("sensor_state",10);
  unsigned fake_ticks=0;
  auto timer=base->create_wall_timer(50ms,[&](){
    if(s.torque) { s.left_encoder+=sdk->last_velocity()*10; s.right_encoder+=sdk->last_velocity()*10; }
    s.header.stamp=base->now(); auto sample=s;
    if(!s.torque || sdk->last_velocity()==0) sample.right_encoder+=int((++fake_ticks)%2);
    sp->publish(sample);
  });
#endif
  Probe probe(node,ex); int result=0;
  try {
    probe.preflight();
    if(run) {
#ifndef TP_FAKE
      // Atomically consume the one physical run before any enable/arm request.
      const int fd=open("/home/twinpulse/guard-validation.RIUO8r/stop-probe-20260927-policy20-consumed",O_WRONLY|O_CREAT|O_EXCL,0600);
      require(fd>=0,"one-shot marker already exists or cannot be created; no rerun"); close(fd);
#endif
      probe.run_once();
    }
  } catch(const std::exception& e) { std::cerr<<"ABORT "<<e.what()<<std::endl; result=1; }
  try { if(!probe.cleanup()) result=2; } catch(...) { std::cerr<<"CLEANUP FAILED; operator cutoff required\n"; result=2; }
#ifdef TP_FAKE
  if(low) { if(result!=1 || enables!=0) return 3; std::cout<<"FAKE_LOW_BATTERY_REJECTED_BEFORE_ENABLE\n"; result=0; }
  if(run && enables!=1) result=4;
#endif
  std::cout<<"RESULT "<<result<<(run?" run":" check")<<std::endl;
  rclcpp::shutdown(); return result;
}
