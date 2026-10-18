// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Separate from the immutable READ helper. Explicit operator-approved torque OFF only.
#include "../include/twinpulse_robot_safety/torque_off.hpp"
#include <dynamixel_sdk/dynamixel_sdk.h>
#include <dynamixel_sdk/port_handler_linux.h>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

static volatile sig_atomic_t interrupted=0;
static void stop(int) { interrupted=1; }
static constexpr const char* device="/dev/serial/by-id/usb-ROBOTIS_OpenCR_Virtual_ComPort_in_FS_Mode_FFFFFFFEFFFF-if00";
class Port : public dynamixel::PortHandlerLinux {
 public: Port():PortHandlerLinux(device){}
 void setPacketTimeout(uint16_t) override { PortHandlerLinux::setPacketTimeout(100.0); }
};
struct IO {
  Port port;
  dynamixel::PacketHandler* packet=dynamixel::PacketHandler::getPacketHandler(2.0);
  void read(uint16_t address,uint16_t length,uint8_t* data) {
    twinpulse::off_require(!interrupted);
    uint8_t error=0;
    const int rc=packet->readTxRx(&port,200,address,length,data,&error);
    std::printf("READ addr=%u len=%u rc=%d error=%u bytes=",address,length,rc,error);
    if(rc==COMM_SUCCESS && error==0) for(unsigned i=0;i<length;++i) std::printf("%02X",data[i]);
    std::puts(""); twinpulse::off_require(rc==COMM_SUCCESS && error==0 && !interrupted);
  }
  void disable() {
    twinpulse::off_require(!interrupted);
    uint8_t error=0;
    const int rc=packet->write1ByteTxRx(&port,200,149,0,&error);
    std::printf("TORQUE_OFF addr=149 value=0 rc=%d error=%u\n",rc,error);
    twinpulse::off_require(rc==COMM_SUCCESS && error==0);
  }
  void wait() { usleep(200000); twinpulse::off_require(!interrupted); }
};
int main(int argc,char** argv) {
  setvbuf(stdout,nullptr,_IONBF,0);
  if(argc!=2 || std::strcmp(argv[1],"--disable-torque")) return 2;
  std::signal(SIGINT,stop); std::signal(SIGTERM,stop); std::signal(SIGHUP,stop);
  char resolved[4096];
  if(!realpath(device,resolved) || std::strcmp(resolved,"/dev/ttyACM0")) return 2;
  int fd=open(device,O_RDWR|O_NOCTTY|O_NONBLOCK);
  if(fd<0) return 2;
  termios saved{}; int modem=0;
  if(flock(fd,LOCK_EX|LOCK_NB)!=0 || tcgetattr(fd,&saved)!=0 ||
     ioctl(fd,TIOCMGET,&modem)!=0 || cfgetospeed(&saved)==B1200) { close(fd); return 2; }
  IO io; int result=0;
  try {
    twinpulse::off_require(io.port.setBaudRate(1000000));
    const auto observation=twinpulse::disable_torque_once(io);
    std::printf("TORQUE_OFF_READBACK_PASS encoder_changed=%d motion_qualified=%d disconnect_waits=%u; no velocity/heartbeat/enable sent\n",
                observation.encoder_changed,observation.motion_qualified,observation.disconnect_waits);
  } catch(const char* reason) {
    std::printf("FAILED: %s; do not infer torque state; independently read board\n",reason); result=3;
  } catch(...) { std::puts("FAILED: unknown IO failure; independently read board"); result=3; }
  io.port.closePort();
  bool restored=tcsetattr(fd,TCSANOW,&saved)==0 && ioctl(fd,TIOCMSET,&modem)==0;
  termios after{}; int after_modem=0;
  restored=restored && tcgetattr(fd,&after)==0 && ioctl(fd,TIOCMGET,&after_modem)==0 &&
    after_modem==modem && after.c_iflag==saved.c_iflag && after.c_oflag==saved.c_oflag &&
    after.c_cflag==saved.c_cflag && after.c_lflag==saved.c_lflag &&
    cfgetispeed(&after)==cfgetispeed(&saved) && cfgetospeed(&after)==cfgetospeed(&saved) &&
    std::memcmp(after.c_cc,saved.c_cc,NCCS)==0;
  std::printf("RESTORE verified=%d\n",restored);
  close(fd); return restored?result:4;
}
