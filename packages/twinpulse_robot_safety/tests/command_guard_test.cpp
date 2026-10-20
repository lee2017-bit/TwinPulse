// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#include "twinpulse_robot_safety/command_guard.hpp"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>
#include <vector>
using twinpulse_robot_safety::CommandGuard;
static unsigned checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::cerr << "FAIL line " << __LINE__ << ": " #x "\n"; std::exit(1); } } while (0)
struct Fixture {
  int32_t v = 0, w = 0;
  bool velocity_ok = true, heartbeat_ok = true;
  int hb = 0;
  std::vector<std::string> events;
  CommandGuard gate{
    [this](int32_t a, int32_t b) { v=a; w=b; events.push_back("velocity"); return velocity_ok; },
    [this](uint8_t) { ++hb; events.push_back("heartbeat"); return heartbeat_ok; }};
  void start() { CHECK(gate.arm(0,10000)); CHECK(gate.receive(.03,.1,10001,10001,1)); }
};
int main() {
  { int32_t v=0; CommandGuard gate([&](int32_t a,int32_t){v=a;return true;},[](uint8_t){return true;},450);
    CHECK(gate.configured_timeout_ms()==450); CHECK(gate.arm(0,10000));
    CHECK(gate.receive(.03,0,10001,10350,350)); // original age349ms, NOT a new450ms lease
    gate.tick(450);CHECK(v==3);gate.tick(451);CHECK(v==0 && !gate.armed()); }
  { bool rejected=false; try { CommandGuard gate([](int32_t,int32_t){return true;},[](uint8_t){return true;},2001); }
    catch(const std::invalid_argument&){rejected=true;} CHECK(rejected); }
  { Fixture f; f.gate.tick(0); CHECK(!f.gate.armed()); CHECK(f.v==0 && f.w==0);
    CHECK(!f.gate.receive(.03,0,10001,10001,1)); CHECK(f.events[0]=="velocity"); CHECK(f.events[1]=="heartbeat"); }
  { Fixture f; f.start(); f.gate.tick(400); CHECK(f.v==3 && f.w==10); f.gate.tick(401);
    CHECK(!f.gate.armed()); CHECK(f.v==0 && f.w==0); CHECK(std::string(f.gate.reason())=="command_timeout");
    CHECK(!f.gate.receive(.03,0,10402,10402,402)); CHECK(f.gate.arm(500,10500));
    CHECK(!f.gate.receive(.03,0,10001,10501,501)); CHECK(!f.gate.armed()); }
  { Fixture f; CHECK(f.gate.arm(0,10000)); f.gate.tick(400); CHECK(!f.gate.armed()); }
  { Fixture f; f.start(); CHECK(!f.gate.arm(300,10300)); f.gate.tick(401); CHECK(f.v==0); }
  { Fixture f; f.start(); CHECK(f.gate.receive(.02,0,10300,10300,300));
    f.gate.tick(699); CHECK(f.v==2); f.gate.tick(700); CHECK(f.v==0); }
  { Fixture f; CHECK(f.gate.arm(0,10000)); CHECK(f.gate.receive(.03,0,10001,10300,300));
    f.gate.tick(401); CHECK(f.v==0 && !f.gate.armed()); }
  for (double bad : {std::numeric_limits<double>::quiet_NaN(),
                      std::numeric_limits<double>::infinity(), .051, -.051}) {
    Fixture f; f.start(); CHECK(!f.gate.receive(bad,0,10002,10002,2)); f.gate.tick(2); CHECK(f.v==0); }
  for (double bad : {std::numeric_limits<double>::quiet_NaN(), .301, -.301}) {
    Fixture f; f.start(); CHECK(!f.gate.receive(0,bad,10002,10002,2)); f.gate.tick(2); CHECK(f.w==0); }
  { Fixture f; f.start(); CHECK(f.gate.receive(-.05,-.3,10002,10002,2)); f.gate.tick(2); CHECK(f.v==-5 && f.w==-30); }
  for (int64_t stamp : {0,10000,10001,10003}) {
    Fixture f; f.start(); CHECK(!f.gate.receive(.03,0,stamp,10002,2)); CHECK(!f.gate.armed()); }
  { Fixture f; f.start(); CHECK(!f.gate.receive(.03,0,10002,10402,2)); }
  { Fixture f; f.start(); CHECK(f.gate.receive(.03,0,10003,10005,5));
    CHECK(!f.gate.receive(.03,0,10004,10004,6)); CHECK(!f.gate.armed()); }
  { Fixture f; f.start(); CHECK(f.gate.stop()); CHECK(f.v==0 && f.w==0); CHECK(!f.gate.armed());
    CHECK(!f.gate.receive(.03,0,10002,10002,2)); }
  { Fixture f; f.start(); f.gate.latch("source_lost"); f.gate.tick(2); CHECK(f.v==0 && !f.gate.armed()); }
  { Fixture f; f.start(); f.velocity_ok=false; f.gate.tick(2); CHECK(f.gate.io_fault()); CHECK(f.hb==0);
    f.velocity_ok=true; f.gate.tick(500); CHECK(f.v==0 && f.hb==0); CHECK(!f.gate.arm(500,10500)); }
  { Fixture f; f.start(); f.heartbeat_ok=false; f.gate.tick(2); CHECK(f.gate.io_fault()); CHECK(f.v==0);
    f.heartbeat_ok=true; f.gate.tick(500); CHECK(f.hb==1); CHECK(!f.gate.arm(500,10500)); }
  { Fixture f; f.velocity_ok=false; CHECK(!f.gate.arm(0,10000)); CHECK(f.gate.io_fault()); }
  { Fixture f; CHECK(!f.gate.arm(0,0)); CHECK(!f.gate.armed()); }
  { Fixture f; f.start(); f.gate.tick(1); f.gate.tick(50); CHECK(f.hb==1); f.gate.tick(101); CHECK(f.hb==2); }
  for (int64_t age=0; age<400; ++age) {
    Fixture f; CHECK(f.gate.arm(0,10000)); CHECK(f.gate.receive(.03,0,10001,10001+age,1+age) == (age < 399));
    f.gate.tick(401); CHECK(f.v==0 && !f.gate.armed());
  }
  std::cout << "PASS " << checks << " checks (fake output only, no hardware)\n";
}
