# Robot connection preparation

Open **Robots** in the installed TwinPulse app. Registration, discovery, PC prerequisites and an authenticated robot observation are separate steps.

The current development package enables explicit physical test paths. See [the current App preparation guide](ROBOT_FLEET_PREPARATION_GUIDE.md) for Connect, stationary native collection and the separate supervised field-test workflow. **Check connection (read-only)** remains read-only and is not the persistent control connection. Robot-OFF preparation does not prove live authentication, sensing or motion. Plain SIM alpha still provides local preparation only.

Historical October16 final06 had observation-only capability. Its ordinary Start had debugging off; explicit Test Start enabled local renderer automation, not extra robot authority. Actual PC preparation and help/offline checker probes passed while the connection check was deliberately not clicked. That record is not current physical readiness. See the [historical screen/evidence report](../outputs/desktop-self-test-20261016/report.html).

1. Open **New robot guide**. Find the robot's current address using its setup instructions. A historical DHCP address is not proof of its current location.
2. Power on the robot and wait for its network connection, then click **Search for robots**, or enter a known address in **Manual registration**. **Responded during network search** lists only service advertisements received in that search. It expires after at most 30 seconds (or the shorter remaining advertisement TTL). It is not continuous reachability, power or authenticated identity. Missing advertisements mean "not observed", not "off". The robot must advertise `_twinpulse._tcp` or `_ssh._tcp`; SSH being enabled alone does not advertise a service. Network discovery must also be allowed. TwinPulse does not change the robot's advertisement or Wi-Fi settings.
3. Review the model adapter, SSH account/port and ROS domain. Register the metadata, then explicitly select the saved robot. USB/Bluetooth candidates without a supported adapter cannot be turned into an SSH robot by their device name.
4. Click **Check PC preparation**. The checklist checks the reviewed adapter, existing OpenSSH client, packaged checker files, automation-key file existence and the selected address's local known-host entry. It never opens a robot connection or reads the private key. Results are tied to the instance/endpoint/revision and expire after 120 seconds or a relevant local file change.
5. Review every missing item. The current reviewed Burger adapter uses `%USERPROFILE%\.ssh\twinpulse-burger\id_ed25519_automation` and `%USERPROFILE%\.ssh\known_hosts`. Check the robot fingerprint using a trusted source before recording its host key. TwinPulse does not generate credentials, replace host keys, change firewall settings or install ROS/OpenSSH as part of this button.
6. In Read-only robot mode, explicitly run **Check connection (read-only)** when the robot is ready. This performs bounded SSH health reads, observations of existing ROS topics and the reviewed board-read check. It does not deploy software, start a driver, collect a survey or enable a motor. The result shows an observation ID/time, normalized health/sensor states and a failure reason/next step where available. An authenticated fresh observation is not permanent connectivity or motion readiness. Plain SIM alpha leaves this button disabled and explains its build capability.

The reviewed Burger preparation/control adapter currently requires SSH user `twinpulse`, port 22 and ROS domain 86; read-only observation supports a separately registered SSH account/port/domain. Host selection is configurable. Other robot adapters need review before execution. The manufacturer's example domain is not a reason to replace the robot's actual domain.

**Registered robots** remain saved even when switched off. A current advertisement can show matching saved names using the exact address/advertised hostname and SSH port only; this does not authenticate the robot, change an endpoint or choose between duplicate registrations. Explicit selection and **Check connection** remain necessary. Discovery does not auto-connect or require a search match before a manual connection check. When a search fails or expires, presence is unknown rather than offline.

**Remembered devices and local ports** is a separate collapsed OS inventory. Remembered Bluetooth entries can remain while a device is off or out of range. These entries never enter network response results. Serial ports are not opened, and no Bluetooth radio scan or pairing occurs. The inventory can help prepare manual registration but cannot infer a supported robot protocol.

After connection, stationary collection can confirm sensor data. Room alignment/wall correction needs a cleaned-up multi-position survey/map of the same room, confirmed source/coordinate alignment and explicit Apply/Undo. Stationary data or connection success alone does not establish furniture alignment, route validity or autonomous readiness.

## Release boundaries

The plain SIM alpha manifest disables physical services and supports local metadata/discovery/preparation without diagnostic/collection/control services. The separate robot-observation candidate declares read-only observation explicitly: it creates diagnostics and an exclusive local device-owner lease, but no readiness/collection or physical controller and no legacy physical-record migration. Every frozen role derives this capability from its verified manifest; deployment/collection child roles are rejected. Parent environment flags cannot turn a plain SIM package into the observation variant.

Connection execution pins the expected registry revision and selected endpoint from one snapshot. An externally changed selection is rejected or used as the newly acknowledged selection; a running job retains its original binding. If the device lease is held elsewhere, metadata/preparation remain available with a restart/close-other-session explanation. Do not bypass the lease or edit manifest/environment settings to open a live session.

Existing registry records, credential references, unknown future adapter metadata and old failed sessions are retained. Preparation results are temporary observations, not new stored robot identity. A selected adapter/version that cannot be executed remains visible with a review-required explanation.

## References

- [ROBOTIS TurtleBot3 bringup](https://emanual.robotis.com/docs/en/platform/turtlebot3/bringup/) documents the robot IP/SSH path and matching network/domain requirements. TwinPulse does not automatically launch its standard bringup instructions.
- [OpenSSH ssh-keygen manual](https://man.openbsd.org/ssh-keygen.1) documents local `-F` host lookup, including hashed known_hosts entries and `[host]:port`. TwinPulse suppresses the lookup output and returns only the checklist result.
- [Installed Electron UI test procedure](DESKTOP_UI_TESTING.md).
