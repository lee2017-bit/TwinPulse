// TwinPulse offline regression harness. No serial implementation/device access.
#include <algorithm>
#include <cassert>
#include <cstring>
#include <iostream>
#include <limits>
#include <vector>
#include "coin_d4_driver/lidar_sdk/lidar_data_processor.hpp"

namespace {
std::vector<uint8_t> input;
size_t cursor = 0, chunk = 1000, max_request = 0, fault_after = 0;
int read_fault = 0;
unsigned checks = 0;
void require(bool value) {
  ++checks;
  if (!value) { std::cerr << "FAILED check " << checks << '\n'; std::abort(); }
}
void reset(std::vector<uint8_t> data, size_t fragment = 1000) {
  input = std::move(data); cursor = 0; chunk = fragment; max_request = 0;
  read_fault = 0; fault_after = 0;
}
std::vector<uint8_t> packet(unsigned count, bool intensity) {
  std::vector<uint8_t> bytes{0xAA, 0x55, 0x01, uint8_t(count), 0x01, 0x05, 0x01, 0x0A, 0, 0};
  uint16_t sum = PH ^ (count << 8 | 1) ^ 0x0501 ^ 0x0A01;
  for (unsigned i = 0; i < count; ++i) {
    if (intensity) { bytes.push_back(0x28); sum ^= 0x28; }
    bytes.push_back(0xA0); bytes.push_back(0x0F); sum ^= 0x0FA0;
  }
  bytes[8] = sum & 255; bytes[9] = sum >> 8;
  return bytes;
}
struct Fixture {
  LidarTimeStatus time{};
  LidarHardwareStatus status{};
  LidarGeneralInfo info{};
  LidarPackage packages{};
  SerialPort serial;
  LidarDataProcessor parser;
  explicit Fixture(bool intensity) :
    info(make_info(intensity)), parser(&time, &status, info, packages) {
    status.serial_connected = true;
    parser.set_serial_port(&serial);
    parser.package_sample_bytes_ = intensity ? 3 : 2;
  }
  static LidarGeneralInfo make_info(bool intensity) {
    LidarGeneralInfo info;
    info.intensity_data_flag = intensity;
    return info;
  }
};
}

// These definitions replace, not wrap, serial_port.cpp. No file/socket syscalls.
SerialPort::SerialPort(const std::string &, uint32_t, Timeout, bytesize_t,
  parity_t, stopbits_t, flowcontrol_t) {}
SerialPort::~SerialPort() = default;
uint32_t SerialPort::getByteTime() { return 1; }
size_t SerialPort::write_data(const uint8_t *, size_t) {
  std::cerr << "UNEXPECTED DEVICE WRITE ATTEMPT\n"; std::abort();
}
size_t SerialPort::available() { return input.size() - cursor; }
result_t SerialPort::waitForData(size_t requested, uint64_t, size_t * returned) {
  max_request = std::max(max_request, requested);
  *returned = std::min(input.size() - cursor, chunk);
  return *returned ? RESULT_OK : RESULT_TIMEOUT;
}
result_t SerialPort::read_data(uint8_t * data, size_t requested) {
  const int active_fault = cursor >= fault_after ? read_fault : 0;
  if (active_fault == 1) return RESULT_FAIL;
  if (active_fault == 2) return 0;
  if (active_fault == 3) return static_cast<result_t>(requested + 1);
  size_t size = std::min({requested, input.size() - cursor, chunk});
  if (active_fault == 4) size = std::min(size, size_t(1));
  std::memcpy(data, input.data() + cursor, size); cursor += size;
  return static_cast<result_t>(size);
}
uint32_t get_milliseconds() { static uint32_t tick = 0; return ++tick; }
uint64_t getTime() { return get_milliseconds() * 1000000ULL; }

int main(int argc, char ** argv) {
  if (argc == 2 && std::string(argv[1]) == "--reproduce-overflow") {
    reset(packet(255, true)); Fixture f(true); node_info node{};
    f.parser.wait_package(&node, 100000);
    std::cerr << "Original parser accepted oversized read (unexpected without sanitizer report)\n";
    return 2;
  }
  // Exhaustively test all 8-bit counts, both formats and fragmented reads.
  for (bool intensity : {false, true}) {
    for (size_t fragment : {size_t(1), size_t(7), size_t(1000)}) {
      for (unsigned count = 0; count < 256; ++count) {
        reset(packet(count, intensity), fragment); Fixture f(intensity); node_info node{};
        const bool valid = count > 0 && (!intensity || count <= 85);
        auto result = f.parser.wait_package(&node, 100000);
        if (!valid) {
          require(result == RESULT_FAIL); require(cursor <= 10); require(max_request <= 10);
        } else {
          require(result == RESULT_OK); require(node.distance_q2 == 1000);
          require(node.sync_flag == Node_Sync);
          require(node.sync_quality == (intensity ? 10 : 0));
          for (unsigned i = 1; i < count; ++i) {
            require(f.parser.wait_package(&node, 100000) == RESULT_OK);
            require(node.distance_q2 == 1000);
          }
          require(cursor == input.size());
        }
      }
    }
  }
  // Truncate at every byte, then verify recovery on the same parser instance.
  auto full = packet(25, true);
  for (size_t length = 0; length < full.size(); ++length) {
    reset(std::vector<uint8_t>(full.begin(), full.begin() + length));
    Fixture f(true); node_info node{};
    require(f.parser.wait_package(&node, 100000) != RESULT_OK);
    reset(full);
    require(f.parser.wait_package(&node, 100000) == RESULT_OK);
    require(node.distance_q2 == 1000);
  }
  // Corrupted checksum retains upstream invalid/zero-range semantics.
  auto bad = full; bad[8] ^= 1;
  reset(bad); Fixture corrupt(true); node_info node{};
  for (unsigned i = 0; i < 25; ++i) {
    require(corrupt.parser.wait_package(&node, 100000) == RESULT_OK);
    require(node.distance_q2 == 0); require(node.sync_flag == Node_NotSync);
  }
  // Resynchronize after non-header noise.
  auto noisy = full; noisy.insert(noisy.begin(), {0, 0x31, 0xAA, 0x44, 0xFF});
  reset(noisy, 1); Fixture noise(true);
  require(noise.parser.wait_package(&node, 100000) == RESULT_OK);
  require(node.distance_q2 == 1000);
  // Actual read length, including a positive short read, controls consumption.
  for (size_t boundary : {size_t(0), size_t(10)}) {
    for (int fault : {1, 2, 3, 4}) {
      reset(full); read_fault = fault; fault_after = boundary; Fixture f(true);
      auto result = f.parser.wait_package(&node, 100000);
      require(fault == 4 ? result == RESULT_OK : result != RESULT_OK);
      if (fault == 4) require(node.distance_q2 == 1000);
    }
  }
  // Reject an inconsistent publicly configurable sample width.
  for (int width : {-1, 0, 1, 2, 4, 1000}) {
    reset(full); Fixture f(true); f.parser.package_sample_bytes_ = width;
    require(f.parser.wait_package(&node, 100000) == RESULT_FAIL); require(cursor == 0);
  }
  // Rejected count cannot leave sample state poisoned for the next complete frame.
  reset(packet(86, true)); Fixture recovery(true);
  require(recovery.parser.wait_package(&node, 100000) == RESULT_FAIL);
  reset(full);
  require(recovery.parser.wait_package(&node, 100000) == RESULT_OK);
  require(node.distance_q2 == 1000);
  // Null output/serial must fail without touching input.
  reset(full); Fixture null_output(true);
  require(null_output.parser.wait_package(nullptr, 100000) == RESULT_FAIL);
  require(cursor == 0);
  LidarTimeStatus time{}; LidarHardwareStatus status{};
  LidarGeneralInfo info{}; LidarPackage packages{};
  LidarDataProcessor unconnected(&time, &status, info, packages);
  require(unconnected.wait_package(&node, 100000) == RESULT_FAIL);
  std::cout << "PASS: " << checks << " assertions; all counts/formats/fragments, truncation, checksum, noise, read faults.\n";
}
