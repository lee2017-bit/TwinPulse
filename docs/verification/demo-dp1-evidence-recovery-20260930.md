# DP1 saved-evidence recovery checkpoint — 2026-09-30

Scope: robot OFF. No SSH, serial, sensor, motor, deployment, actual file transfer, paid service, or physical qualification was run. All transfer tests injected a local fake runner/exporter.

## Product behavior added

- A saved real-transport session in App history now offers an explicit **Retry saved evidence transfer only** action. The authenticated/CSRF-protected API starts a background transfer for one path-constrained saved job. It does not call `PhysicalController.start`, preparation, qualification, a sensor driver, or a motor command. Duplicate request IDs are consumed; an active physical operation and an active recovery exclude one another. Result/status is shown in the UI; missing or invalid saved reports are rejected.
- The DP0 inventory now has an 18th `saved_evidence_resume` operation bound to the product recovery class and its offline test. The inventory audit still exits nonzero and `pc_demo_ready=false` because other operations remain unintegrated or unimplemented.
- The existing allowlist exporter still preserves remote originals and reuses only verified local files. It rejects staging symlinks/non-files; an exact regular generated `.part` left by an interrupted transfer is discarded and refetched, with that fact in the receipt. The control/mission/qualification bundle reaches `COMPLETE` only after full raw-frame structure, sequence, topic/type, receipt timestamp, footer/drop count and digest validation, in addition to worker report/run/boot/release binding. A rehashed malformed raw frame is rejected with a bounded `binding_reason` in the receipt. `raw_message_decode=NOT_RUN` is explicit.
- The offline raw inspector rejects symlinks, oversized files/footers, malformed/rehashed metadata, non-integer or inconsistent footer counts and nonempty error lists. It still returns original serialized bytes; it does not reinterpret invalid ROS messages as valid observations.
- The offline inspector now has opt-in `--decode-ros`: when compatible local ROS 2 packages already exist, it uses `rclpy.serialization.deserialize_message` with an allowlisted message class and reports decoded message count. It never installs packages or starts a ROS node. If the decoder is absent, it exits incomplete with `ROS_DECODER_UNAVAILABLE`; a corrupt CDR frame reports its sequence. The default inspection remains byte-integrity only. [ROS 2 serialization API](https://docs.ros.org/en/ros2_packages/jazzy/api/rclpy/rclpy.serialization.html) documents the underlying deserialize call. A successful decode is not an odom/TF validity or physical-position acceptance.

## Verification

- Raw/export/recovery focused: 18/18 PASS, including rehashed malformed metadata, oversized footer, exact stale `.part` recovery, no-transport retry/idempotence, active-operation exclusion, authenticated API and injected decoder type/byte contract.
- Relevant physical-controller + export/recovery: 74/74 PASS.
- `test_robot*.py` integration: 86/86 PASS. These tests use fake transports; console strings that describe SSH are fixture output, not a new robot connection.
- Web: 170/170 PASS, including no automatic transfer and one explicit click; TypeScript and production Vite build PASS. Initial restricted-shell Vite run failed with `spawn EPERM`; the same build passed under the approved local execution permission. No dependency install.
- `git diff --check` for changed implementation files PASS (line-ending warnings only).
- DP0 audit tests 2/2 PASS; the command-line audit returns its expected nonzero/not-ready result.

## Boundary and remaining work

- This closes a narrow DP1 product recovery increment, **not DP1 acceptance**. The existing local manual-control archive contains saved reports/journals but no newly transferred real `ros-messages.raw` bundle for message-level odom/scan/TF replay. The current PC has no compatible ROS decoder packages. The adapter was tested with injected fake modules only; actual ROS CDR decoding, message semantics and physical observation remain `NOT_RUN`. The export receipt itself verifies serialized-byte integrity only.
- A failed automatic end-of-operation export is not silently retried. The user may explicitly retry file transfer from a saved real-transport session. A server restart does not resume transfer on its own; the saved report supports a later explicit retry.
- DP0 operation contract/coverage remains incomplete. COIN ROS lifecycle/target build, current sensor and room↔odom calibration, live mission/product one-session integration, full DP4/DP5 same-build acceptance, and a fresh on-site test remain blocked or unverified. `pc_demo_ready=false`; live mission lock and prior stop failures are unchanged.
