// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Bounded OpenCR identification/status check. No ROS nodes or write-register calls.
// Target and protocol come from the installed ROBOTIS TurtleBot3 configuration.
#include <dynamixel_sdk/dynamixel_sdk.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>
#include <csignal>

static volatile std::sig_atomic_t interrupted = 0;
static void stop_reading(int) { interrupted = 1; }

int main()
{
  std::signal(SIGTERM, stop_reading);
  std::signal(SIGINT, stop_reading);
  constexpr const char *device = "/dev/serial/by-id/usb-ROBOTIS_OpenCR_Virtual_ComPort_in_FS_Mode_FFFFFFFEFFFF-if00";
  char resolved[4096];
  if (!realpath(device, resolved) || std::strcmp(resolved, "/dev/ttyACM0") != 0) {
    std::puts("Unexpected device; no access attempted."); return 2;
  }
  const int guard = open(device, O_RDWR | O_NOCTTY | O_NONBLOCK);
  if (guard < 0) { std::perror("open"); return 2; }
  termios saved{};
  if (flock(guard, LOCK_EX | LOCK_NB) != 0 || tcgetattr(guard, &saved) != 0) {
    std::perror("save/lock"); close(guard); return 2;
  }
  int modem = 0;
  const bool have_modem = ioctl(guard, TIOCMGET, &modem) == 0;
  auto *port = dynamixel::PortHandler::getPortHandler(device);
  auto *packet = dynamixel::PacketHandler::getPacketHandler(2.0);
  int result = 0;
  // setBaudRate opens the SDK port directly; no intermediate baud or reset request.
  if (!port->setBaudRate(1000000)) {
    std::puts("SDK port setup failed."); result = 3;
  } else {
    constexpr uint8_t id = 200;
    uint16_t model = 0;
    uint8_t error = 0;
    const int comm = packet->ping(port, id, &model, &error);
    std::printf("PING id=200 comm=%d error=%u model=%u message=%s\n",
      comm, error, model, packet->getTxRxResult(comm));
    if (comm != COMM_SUCCESS || error != 0) {
      result = 4;
    } else {
      // All ranges are READ operations from the installed host control table.
      // Print raw bytes; do not assume this firmware implements those meanings.
      struct Range { uint16_t address, length; const char *label; };
      const Range ranges[] = {
        {0, 9, "identification"}, {18, 1, "expected_device_status"},
        {42, 4, "expected_supply_voltage"}, {128, 16, "expected_wheel_feedback"},
        {149, 1, "expected_torque_state"}, {150, 24, "expected_command_state"}
      };
      for (const auto &range : ranges) {
        if (interrupted) { result = 7; break; }
        uint8_t data[24]{};
        error = 0;
        const int status = packet->readTxRx(port, id, range.address, range.length, data, &error);
        std::printf("READ %s addr=%u len=%u comm=%d error=%u bytes=",
          range.label, range.address, range.length, status, error);
        if (status == COMM_SUCCESS && error == 0) {
          for (unsigned i = 0; i < range.length; ++i) std::printf("%02X", data[i]);
        } else { result = 5; }
        std::puts("");
        if (result != 0) break;
      }
    }
  }
  port->closePort();
  const int restored = tcsetattr(guard, TCSANOW, &saved);
  const int modem_restored = have_modem ? ioctl(guard, TIOCMSET, &modem) : 0;
  std::printf("RESTORE termios=%d modem=%d modem_saved=%d\n", restored, modem_restored, have_modem);
  if (restored != 0 || modem_restored != 0) result = 6;
  flock(guard, LOCK_UN);
  close(guard);
  delete port;
  if (interrupted) result = 7;
  return result;
}
