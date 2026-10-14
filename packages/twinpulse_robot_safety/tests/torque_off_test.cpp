// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
#include "../include/twinpulse_robot_safety/torque_off.hpp"
#include <array>
#include <cassert>
#include <cstdio>
struct Fake {
  std::array<uint8_t,174> data{};
  int writes=0,reads=0,waits=0,fail_read=-1;
  int disconnect_after=-1;
  bool fail_write=false,ignore_write=false,drift=false,velocity_after_off=false;
  twinpulse::TorqueOffObservation observation;
  Fake() { data[1]=0x50;data[2]=1;data[6]=5;data[7]=200;
           data[42]=0xC4;data[43]=4;data[148]=1;data[149]=1; }
  void read(uint16_t a,uint16_t n,uint8_t* out) {
    if(++reads==fail_read) throw "read failure";
    std::memcpy(out,data.data()+a,n);
  }
  void disable() { ++writes; if(fail_write) throw "write failure"; if(!ignore_write)data[149]=0; }
  void wait() { ++waits; if(waits==disconnect_after)data[15]=0; if(drift)data[136]++; if(velocity_after_off&&writes)data[128]=1; }
};
static bool run(Fake& f) { try { f.observation=twinpulse::disable_torque_once(f);return true; }catch(...){return false;} }
int main() {
  int cases=0;
  Fake ok; assert(run(ok) && ok.writes==1 && ok.data[149]==0 && !ok.observation.encoder_changed && !ok.observation.motion_qualified); ++cases;
  const int total=ok.reads;
  Fake off;off.data[149]=0;assert(run(off)&&off.writes==0);++cases;
  for(int n: {1,3,10}) { Fake f;f.data[15]=1;f.disconnect_after=n;
    assert(run(f)&&f.writes==1&&f.observation.disconnect_waits==unsigned(n));++cases; }
  Fake connected;connected.data[15]=1;assert(!run(connected)&&connected.writes==0&&connected.waits==10);++cases;
  Fake late;late.data[15]=1;late.disconnect_after=11;assert(!run(late)&&late.writes==0);++cases;
  Fake moving_wait;moving_wait.data[15]=1;moving_wait.data[128]=1;assert(!run(moving_wait)&&!moving_wait.writes&&!moving_wait.waits);++cases;
  Fake read_wait;read_wait.data[15]=1;read_wait.fail_read=8;assert(!run(read_wait)&&!read_wait.writes&&read_wait.waits==1);++cases;
  for(int i=1;i<=total;++i) { Fake f;f.fail_read=i;assert(!run(f)&&f.writes<=1);if(i<=13)assert(f.writes==0);++cases; }
  const int bad[]={0,1,2,3,4,5,6,7,14,15,18,26,27,128,129,130,131,132,133,134,135,148,149};
  for(int a:bad) { Fake f;f.data[a]^=2;assert(!run(f)&&f.writes==0);++cases; }
  for(int a=150;a<174;++a) { Fake f;f.data[a]=1;assert(!run(f)&&f.writes==0);++cases; }
  for(unsigned v: {0u,1109u,1266u,65535u}) {Fake f;f.data[42]=v&255;f.data[43]=v>>8;assert(!run(f)&&!f.writes);++cases;}
  Fake drift;drift.drift=true;assert(run(drift)&&drift.writes==1&&drift.observation.encoder_changed&&!drift.observation.motion_qualified);++cases;
  Fake moving_after;moving_after.velocity_after_off=true;assert(!run(moving_after)&&moving_after.writes==1);++cases;
  Fake fail;fail.fail_write=true;assert(!run(fail)&&fail.writes==1);++cases;
  Fake ignored;ignored.ignore_write=true;assert(!run(ignored)&&ignored.writes==1);++cases;
  std::printf("PASS %d device-free torque-off cases\n",cases);
}
