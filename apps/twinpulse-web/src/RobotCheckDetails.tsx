// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type { RobotReportState } from './RobotReport';

/** Render validated observations only; missing legacy fields never imply PASS. */
export function RobotCheckDetails({ record, healthStatus, sensorStatus }: {
  record: NonNullable<RobotReportState['record']>; healthStatus?: string; sensorStatus?: string;
}) {
  const board = record.board_observation;
  const moving = board && board.wheel_velocity_raw.some(value => value !== 0);
  const command = board && !board.command_bytes_zero;
  const torque = board?.torque_enabled;
  const port = board && !board.port_restored;
  const battery = record.battery;
  const idle = board && !torque && !moving && !command && !port;
  const deployment = record.guard_artifact_verified_at_observation === true && Boolean(record.release_id);
  const sensorMessages: Record<string, string> = {
    NO_SENSOR_DATA: 'No sensor data. This check does not start the driver, so this result alone does not indicate a fault. Coordinate synchronization remains unavailable.',
    PARTIAL_SENSOR_DATA: 'Only some sensor data was received. The full sensor set is not ready.',
    SENSOR_MESSAGES_RECEIVED: 'Existing sensor messages were received. This does not verify coordinate alignment or obstacle safety.',
    ROS_PYTHON_UNAVAILABLE: 'The ROS Python environment was unavailable, so sensor reception was not checked. No automatic reinstall was attempted.',
    ROS_PROBE_FAILED: 'Sensor query failed. A lack of reception cannot be distinguished from a fault.',
  };
  return <section className="native-quality" aria-label="Findings and next actions">
    <h3>Findings and next actions</h3>
    {board ? <>
      <p>Board observation time: {board.observed_at_utc} · This is a snapshot, not a continuous stop test.</p>
      <ul>
        <li>Motor torque: {torque ? 'enabled — idle condition not met' : 'disabled according to board'}.
          {torque && ' This means torque could be applied; it does not by itself mean the wheels moved.'}</li>
        <li>Raw wheel velocity: left {board.wheel_velocity_raw[0]}, right {board.wheel_velocity_raw[1]} — {moving ? 'nonzero' : 'both zero'}.</li>
        <li>Velocity command bytes: {command ? 'nonzero — stop-command condition not met' : 'all zero'}.</li>
        <li>Communication port restored: {port ? 'unverified — further access paused' : 'verified'}.</li>
      </ul>
    </> : <p>{record.board_status === 'OBSERVED'
      ? 'This result has no individual torque, velocity, or port values. Do not infer a cause from an older summary. Close the check window, reopen Open-Robot-Console.cmd, and run the bundled check once to save details.'
      : `No board details (${record.board_status}). Another program may own the port, or reading may have failed. Do not force-close other programs or repeatedly run the check.`}</p>}
    <p>Guard program file: {record.guard_artifact_verified_at_observation === true ? 'verified file found' : 'unverified'} · deployment version: {record.release_id ? 'found' : 'unverified'}. Finding a file does not verify physical control behavior.</p>
    <p>{sensorMessages[sensorStatus ?? ''] ?? 'Sensor query result is missing or unrecognized. Do not treat sensors as ready.'}</p>
    <h4>Next actions</h4>
    {battery && (battery.charge_requested_at_observation || battery.near_protection_at_observation) &&
      <p>Do not drive. Follow the established shutdown and charging procedure. Repeating a check cannot resolve low voltage.</p>}
    {(moving || command) && <p>Wheel velocity or command is nonzero. Do not touch the wheels or drive. If physical motion continues, use the robot's physical stop mechanism. This read-only check sends no stop command.</p>}
    {port && <p>Port restoration was not verified, so further connection and control are paused. Review the check program's restoration behavior.</p>}
    {torque && !moving && !command && !port && <p>Motor torque is enabled. Velocity and command were observed as zero, but the motor-disabled condition was not met. Instead of repeating checks or reinstalling, consider Motor OFF and status confirmation in the control panel. This read-only check does not do that automatically.</p>}
    {!deployment && <p>Guard program or deployment evidence is insufficient. Do not drive. Installation status needs review; nothing is deployed automatically.</p>}
    {idle && deployment && healthStatus === 'IDLE_SNAPSHOT_OK' && <p>Board and deployment conditions passed this read-only snapshot. No need to repeat it. This is not a passed stop test. Verify a valid result for the current boot and deployment in the manual control panel. Do not begin moving based on this observation alone.</p>}
    {idle && deployment && healthStatus !== 'IDLE_SNAPSHOT_OK' && <p>The board snapshot met its conditions, but overall health is unresolved ({healthStatus ?? 'unverified'}). Review running programs or collection status; the robot is not cleared to drive.</p>}
    <p>Pending development and validation: sensor coordinate alignment and physical autonomous mission integration. Motor OFF, stop test, and manual control live in a separate panel; this read-only result does not replace them. Repeating the same check will not complete unfinished features.</p>
  </section>;
}
