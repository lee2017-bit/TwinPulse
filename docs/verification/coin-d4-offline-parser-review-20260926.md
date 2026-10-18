# COIN-D4 offline parser review — 2026-09-26

## Outcome and scope

**PC-only parser remediation and bounded synthetic regression PASS. Not deployed to the robot.**

User approved continuing the previously interrupted local-copy repair/test. No SSH, serial device, ROS node, OpenCR, firmware, wheel command or power-state operation was performed in this review. The operator previously said the scanner stopped; this does **not** establish that Ubuntu was shut down or the adapter removed. Do not assume the robot is currently powered off or ask for a power change merely to run these PC tests.

The software-command-to-physical-stop discrepancy remains **unresolved**. Upstream `deactivate_grab_thread()` sends `end_lidar` but does not independently measure rotor stop. No start/stop/control-line bytes or lifecycle behavior were modified. These parser results do not authorize sensor runtime or motion.

## Source and changes

- Upstream: https://github.com/ROBOTIS-GIT/coin_d4_driver
- Pinned commit: `8277b288902f28b37948b42e1bb80ba59afbba60`, matching the earlier Pi build.
- Isolated Windows scratch clone: `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\coin-d4-offline-review-20260926`.
- Reviewable two-file patch: [coin-d4-parser-bounds-20260926.patch](coin-d4-parser-bounds-20260926.patch).
- Preserved test source: [parser_test.cpp](coin-d4-offline-tests/parser_test.cpp), with two empty test-only ROS include stubs. Actual upstream parser code and data structures are compiled, not a rewritten parser model. Actual `serial_port.cpp`, ROS node and hardware handlers are deliberately **not linked**. The harness substitutes in-memory reads and aborts on any write request.

The original code derived its writable packet pointer from a two-byte header member, trusted the sample count before payload reads/copies, and ignored actual read lengths. The separate in-memory original-source run triggered an AddressSanitizer heap-buffer-overflow. This establishes a synthetic malformed-input failure, not exploitation, hardware damage, or the cause of the observed rotor behavior.

The local patch:

1. Uses the full packet object's byte representation rather than its header subobject.
2. Rejects zero samples and counts beyond the actual payload array capacity **before** payload reads and angle calculations. Current three-byte format capacity is 85 samples; two-byte format accepts the representable 1–255 range. The 85 limit follows this implementation's buffer size, not a newly established hardware protocol maximum.
3. Rejects inconsistent configured sample widths and null output/unset serial pointers.
4. Uses the actual positive read count, permits short positive reads, and fails on zero, negative or impossible reported counts.

No buffer size expansion, calibration change, baud-rate change or global warning suppression was introduced. Upstream invalid-checksum/zero-range semantics are preserved.

## Verification

Existing PC WSL Ubuntu-22.04, x86-64 GCC 11.4.0; no dependency installation.

- Original source reproduction: AddressSanitizer nonzero exit, before applying the patch.
- Patched `-O1` AddressSanitizer/UndefinedBehaviorSanitizer run: **222727 assertions PASS**.
- Expanded patched `-O2 -Wall -Wextra -Wpedantic -Wstringop-overflow=2 -Werror` build: exit 0, **no compiler warnings** in the compiled parser/harness scope.
- Expanded ASan/UBSan run: **222738 assertions PASS**, exit 0, no sanitizer report. Leak detection was disabled; leak freedom is not claimed.
- Covers all 256 sample-count values × two formats × three fragmentation sizes; normal decoded distance/quality, every truncation point of an 85-byte frame, bad checksum, header noise, header/body read failures and short reads, malformed-frame recovery, inconsistent widths, null output and unset serial.
- The `data check, ...` output is the intentionally corrupted-checksum fixture, not a failed test.
- `git diff --check` and exported patch reverse-apply check PASS. No commit or push.

Commands from the scratch clone (Linux/WSL shell):

```sh
g++ -std=c++14 -g -O2 -fsanitize=address,undefined -fno-omit-frame-pointer \
  -Wall -Wextra -Wpedantic -Wstringop-overflow=2 -Werror \
  -Ioffline_tests/stubs -Iinclude src/lidar_sdk/lidar_data_processor.cpp \
  offline_tests/parser_test.cpp -o offline_tests/parser-patched
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 ./offline_tests/parser-patched
```

`offline_tests/` in the scratch clone corresponds to the preserved `coin-d4-offline-tests/` sources beside this report. The patch must be applied only to the exact pinned upstream revision after reviewing any local changes; this report does not automatically apply it anywhere.

## Limits and next gate

This is a focused `wait_package` parser regression, **not** an audit of the whole driver. The legacy `wait_speed_right` method, serial implementation, ROS lifecycle/threading, other versions, ARM64/ROS full package rebuild and actual sensor data regression remain outside this test. The original installed Pi source remains unchanged, so its warning is not resolved on-device.

Next: review the patch and clarify the physical stop contract before a separately authorized on-device build and bounded sensor-only ROS `/scan` trial. Do not start full TurtleBot bringup, flash OpenCR, or move wheels. Battery switching is not needed for the offline work.
