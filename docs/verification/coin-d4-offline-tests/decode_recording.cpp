// Decode a bounded SAVED file with the actual patched vendor parser.
// Replaces serial_port.cpp; no device, ROS, socket or command writer is linked.
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include "coin_d4_driver/lidar_sdk/lidar_data_processor.hpp"

// Default preserves the original8s harness. A separate offline build may opt
// into the explicitly bounded40s recording size; parser logic is unchanged.
#ifndef TP_OFFLINE_MAX_BYTES
#define TP_OFFLINE_MAX_BYTES (512 * 1024)
#endif

namespace {
std::vector<uint8_t> input;
size_t cursor = 0;
}
SerialPort::SerialPort(const std::string &, uint32_t, Timeout, bytesize_t,
  parity_t, stopbits_t, flowcontrol_t) {}
SerialPort::~SerialPort() = default;
uint32_t SerialPort::getByteTime() { return 1; }
size_t SerialPort::write_data(const uint8_t *, size_t) { std::abort(); }
size_t SerialPort::available() { return input.size() - cursor; }
result_t SerialPort::waitForData(size_t, uint64_t, size_t * count) {
  *count = input.size() - cursor;
  return *count ? RESULT_OK : RESULT_TIMEOUT;
}
result_t SerialPort::read_data(uint8_t * data, size_t requested) {
  size_t n = std::min(requested, input.size() - cursor);
  std::memcpy(data, input.data() + cursor, n);
  cursor += n;
  return static_cast<result_t>(n);
}
uint32_t get_milliseconds() { static uint32_t tick = 0; return ++tick; }
uint64_t getTime() { return get_milliseconds() * 1000000ULL; }

int main(int argc, char ** argv) {
  if (argc != 2) return 2;
  std::ifstream stream(argv[1], std::ios::binary | std::ios::ate);
  if (!stream || stream.tellg() <= 0 || stream.tellg() > TP_OFFLINE_MAX_BYTES) return 3;
  stream.seekg(0);
  input.assign(std::istreambuf_iterator<char>(stream), {});
  LidarTimeStatus timing{};
  LidarHardwareStatus state{};
  LidarGeneralInfo info{};
  LidarPackage packages{};
  info.intensity_data_flag = true;
  state.serial_connected = true;
  SerialPort serial;
  LidarDataProcessor parser(&timing, &state, info, packages);
  parser.set_serial_port(&serial);
  parser.package_sample_bytes_ = 3;
  size_t decoded = 0, errors = 0;
  // A packet payload read consumes bytes before all its samples are returned.
  // Keep calling until timeout with no remaining bytes, not merely cursor==EOF.
  for (size_t tries = 0; tries <= input.size() * 2; ++tries) {
    node_info node{};
    auto result = parser.wait_package(&node, 100000);
    if (!IS_OK(result)) {
      ++errors;
      if (cursor == input.size()) break;
      continue;
    }
    ++decoded;
    std::cout << "{\"angle_deg\":" << (node.angle_q6_checkbit >> 1) / 64.0
      << ",\"distance_m\":" << node.distance_q2 / 1000.0
      << ",\"quality\":" << node.sync_quality
      << ",\"ring_start\":" << ((node.sync_flag & 1) ? "true" : "false")
      << ",\"source_byte_cursor\":" << cursor << "}\n";
  }
  std::cerr << "Saved data only: bytes=" << input.size() << " decoded=" << decoded
    << " parser_non_ok_including_EOF=" << errors << '\n';
  return decoded ? 0 : 4;
}
