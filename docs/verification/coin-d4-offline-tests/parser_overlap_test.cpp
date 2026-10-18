// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Saved/synthetic memory only. No serial implementation, ROS, or sockets linked.
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
#include "coin_d4_driver/lidar_sdk/lidar_data_processor.hpp"

namespace {
std::vector<uint8_t> input;
size_t cursor = 0, fragment = 1000;
unsigned checks = 0, cases = 0;
void require(bool value) {
  ++checks;
  if (!value) {
    std::cerr << "OVERLAP_FAIL assertion=" << checks << " case=" << cases
      << " cursor=" << cursor << '\n';
    std::exit(7);
  }
}
void reset(const std::vector<uint8_t> & bytes, size_t limit) {
  input = bytes; cursor = 0; fragment = limit;
}
std::vector<uint8_t> packet(unsigned count, bool intensity, bool ring) {
  const uint8_t ct = ring ? 1 : 0;
  std::vector<uint8_t> bytes{0xAA, 0x55, ct, uint8_t(count), 0x01, 0x05, 0x01, 0x0A, 0, 0};
  uint16_t sum = PH ^ (count << 8 | ct) ^ 0x0501 ^ 0x0A01;
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
  explicit Fixture(bool intensity) : info(make_info(intensity)), parser(&time, &status, info, packages) {
    status.serial_connected = true;
    parser.set_serial_port(&serial);
    parser.package_sample_bytes_ = intensity ? 3 : 2;
  }
  static LidarGeneralInfo make_info(bool intensity) {
    LidarGeneralInfo value{}; value.intensity_data_flag = intensity; return value;
  }
};
void same_measurement(const node_info & a, const node_info & b) {
  require(a.angle_q6_checkbit == b.angle_q6_checkbit);
  require(a.distance_q2 == b.distance_q2);
  require(a.sync_quality == b.sync_quality);
  require(a.sync_flag == b.sync_flag);
}
std::vector<node_info> decode(const std::vector<uint8_t> & data, bool intensity,
                            size_t count, size_t chunk) {
  reset(data, chunk); Fixture fixture(intensity);
  std::vector<node_info> result;
  for (size_t i = 0; i < count; ++i) {
    node_info node{};
    require(fixture.parser.wait_package(&node, 100000) == RESULT_OK);
    result.push_back(node);
  }
  require(cursor == data.size());
  node_info end{};
  require(fixture.parser.wait_package(&end, 100000) != RESULT_OK);
  return result;
}
}

SerialPort::SerialPort(const std::string &, uint32_t, Timeout, bytesize_t,
  parity_t, stopbits_t, flowcontrol_t) {}
SerialPort::~SerialPort() = default;
uint32_t SerialPort::getByteTime() { return 1; }
size_t SerialPort::write_data(const uint8_t *, size_t) {
  std::cerr << "UNEXPECTED_DEVICE_WRITE\n"; std::abort();
}
size_t SerialPort::available() { return input.size() - cursor; }
result_t SerialPort::waitForData(size_t, uint64_t, size_t * count) {
  *count = std::min(input.size() - cursor, fragment);
  return *count ? RESULT_OK : RESULT_TIMEOUT;
}
result_t SerialPort::read_data(uint8_t * bytes, size_t requested) {
  const size_t n = std::min({requested, input.size() - cursor, fragment});
  std::memcpy(bytes, input.data() + cursor, n); cursor += n;
  return static_cast<result_t>(n);
}
uint32_t get_milliseconds() { static uint32_t tick = 0; return ++tick; }
uint64_t getTime() { return get_milliseconds() * 1000000ULL; }

int main() {
  for (bool intensity : {false, true}) {
    for (bool ring : {false, true}) {
      for (unsigned count : {1u, 25u, intensity ? 85u : 255u}) {
        const auto plain = packet(count, intensity, ring);
        const auto baseline = decode(plain, intensity, count, 1000);
        for (size_t chunk : {size_t(1), size_t(2), size_t(3), size_t(7), size_t(10), size_t(1000)}) {
          for (size_t repeat = 1; repeat <= 32; ++repeat) {
            ++cases;
            std::vector<uint8_t> bytes(repeat, 0xAA);
            bytes.insert(bytes.end(), plain.begin(), plain.end());
            const auto recovered = decode(bytes, intensity, count, chunk);
            for (size_t i = 0; i < count; ++i) same_measurement(recovered[i], baseline[i]);
          }
          for (size_t padding = 0; padding <= 20; ++padding) {
            ++cases;
            std::vector<uint8_t> bytes(padding, 0x31);
            bytes.insert(bytes.end(), {0xAA, 0x44, 0xFF, 0xAA});
            bytes.insert(bytes.end(), plain.begin(), plain.end());
            const auto recovered = decode(bytes, intensity, count, chunk);
            for (size_t i = 0; i < count; ++i) same_measurement(recovered[i], baseline[i]);
          }
        }
      }
    }
  }
  // Repeated sync prefixes must not hide checksum corruption or admit missing bytes.
  auto full = packet(25, true, false);
  // The vendor's reverse-angle fallback uses the preceding packet's interval.
  // Recovering a lost packet must restore that same state, not force suffix
  // values to equal a decode that omitted the state-setting packet.
  for (bool intensity : {false, true}) {
    auto first = packet(25, intensity, false);
    auto reversed = first;
    std::swap(reversed[4], reversed[6]);
    std::swap(reversed[5], reversed[7]); // XOR checksum is unchanged by this swap.
    auto combined = first;
    combined.insert(combined.end(), reversed.begin(), reversed.end());
    const auto baseline = decode(combined, intensity, 50, 1000);
    const auto cold = decode(reversed, intensity, 25, 1000);
    require(baseline[26].angle_q6_checkbit != cold[1].angle_q6_checkbit);
    combined.insert(combined.begin(), 0xAA);
    for (size_t chunk : {size_t(1), size_t(2), size_t(7), size_t(1000)}) {
      ++cases;
      const auto recovered = decode(combined, intensity, 50, chunk);
      for (size_t i = 0; i < baseline.size(); ++i) same_measurement(recovered[i], baseline[i]);
    }
  }
  for (size_t chunk : {size_t(1), size_t(2), size_t(7), size_t(1000)}) {
    ++cases;
    auto bad = full; bad[8] ^= 1; bad.insert(bad.begin(), 0xAA);
    const auto nodes = decode(bad, true, 25, chunk);
    for (const auto & node : nodes) {
      require(node.distance_q2 == 0); require(node.sync_flag == Node_NotSync);
    }
    for (size_t length = 0; length < full.size(); ++length) {
      ++cases;
      std::vector<uint8_t> truncated;
      truncated.reserve(full.size() + 1);
      truncated.push_back(0xAA);
      for (size_t i = 0; i < length; ++i) truncated.push_back(full[i]);
      reset(truncated, chunk); Fixture fixture(true); node_info node{};
      require(fixture.parser.wait_package(&node, 100000) != RESULT_OK);
      reset(full, chunk);
      require(fixture.parser.wait_package(&node, 100000) == RESULT_OK);
      require(node.distance_q2 == 1000);
    }
  }
  // Rejected oversized/zero frames cannot bypass count bounds through overlap.
  for (unsigned count : {0u, 86u, 255u}) {
    for (size_t chunk : {size_t(1), size_t(7), size_t(1000)}) {
      ++cases;
      auto bad = packet(count, true, false); bad.insert(bad.begin(), 0xAA);
      reset(bad, chunk); Fixture fixture(true); node_info node{};
      require(fixture.parser.wait_package(&node, 100000) == RESULT_FAIL);
      require(cursor <= 11);
      reset(full, chunk);
      require(fixture.parser.wait_package(&node, 100000) == RESULT_OK);
      require(node.distance_q2 == 1000);
    }
  }
  // A malformed synchronization prefix is not itself a measurement.
  for (size_t chunk : {size_t(1), size_t(7), size_t(1000)}) {
    ++cases;
    reset(std::vector<uint8_t>(4096, 0xAA), chunk); Fixture fixture(true); node_info node{};
    require(fixture.parser.wait_package(&node, 100000) != RESULT_OK);
  }
  std::cout << "PASS overlap: cases=" << cases << " assertions=" << checks
    << " both_formats both_ring_flags repeated_prefix fragments checksum truncation bounds\n";
  return 0;
}
