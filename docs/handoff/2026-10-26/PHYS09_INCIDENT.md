# PHYS09 — 2026-10-26 22:01–22:32 KST physical attempt, stopped by the user (incident log)

Installed build `20261026T125513Z-8ff43ad1f4dc` (development channel, "build 52": build 50 + model-list refresh UI + photo token cap; robot-side packages unchanged since `9aeb7ef`). Robot: TurtleBot3 Burger, registration "Imported existing settings · unverified" (robot_id `2bf518f0…`). Operator at the PC and with the robot; no motion command was ever sent; Run route was never pressed. Screen recording `outputs/path-b-20261026/demo-sim/rec-physical.mp4` (26:06, kept; an earlier 2-minute file `rec-physical-part0.mp4` covers the New chat → USD import part before a driver abort). All times UTC (KST = UTC+9).

## Timeline (confirmed from PC-side records)

| UTC | Event | Source |
|---|---|---|
| 12:54–13:06 | New chat `chat_mvp9mbiw_9253ff0c`, home USD `Project-2610222326.usd` (units m) inspected, imported, Show Twin; Twin edits → Auto-apply; photo analysis (DeepSeek V4.1 Flash) of a downscaled living-room/bedroom photo, 1 candidate auto-applied at (0.74, 1.14) → "Twin updated, saved and its current 3D frame confirmed". | driver log, conversation |
| 13:11:13 | **Connect** → CONNECTED · UNPREPARED · reason `FIELD_CONFIG_CHANGED`; battery **12.39 V** (measured, OpenCR idle read; voltage protection CLEAR, low-voltage guard 11.1 V). Robot worker started (`persistent_worker_started`), control_pause `FIELD_CONFIG_CHANGED` at robot time 231.5 s (normal pre-release pause). | `physical-fleet-operations/731ec1ef…`, live recording |
| 13:13:19 | **LiDAR on** → STREAMING (robot 346.4 s). Scan stream: 1746 scans, 4.87 Hz, median gap 0.205 s, **max gap 0.234 s** (no freshness/watchdog trip). | live recording `physical-live/731ec1ef…` (82 362 events, 125 MB) |
| 13:13–13:19 | Operator asked to tick "I am present…" (the supervisor confirmations cannot be ticked by the automation; see UI problems). | chat relay |
| **13:19:08** (robot 705.29 s) | **FAULT** event: `{"reason":"NATIVE_ARCHIVE_SESSION_JOURNAL_WRITE_FAILED","subsystem":"native_archive"}`. Same second: last scan (705.23 s), heartbeat `control_state: CLOSED`, `lidar_state: FAULT`, blockers `CONTROL_WORKER_CLOSED`, `RECORDING_INCOMPLETE`; battery 12.22 V. The App showed **DEGRADED · "LiDAR No current stream · last reported FAULT" · 12.26 V · "Disconnect to reconnect"**, and the Physical-setup confirmation checkboxes were no longer rendered. | live recording (fault + heartbeat), robot card text |
| 13:20:43 | Explicit **Disconnect** (by me, to reconnect) → `services_closed` with `cleanup_errors: ["REMOTE_CLEANUP_UNCONFIRMED"]`; robot cleanup event at 789.48 s. | operations log |
| 13:20:49, 13:25:08, 13:27:58 | Three **Connect** attempts (`7cd28909…`, `129311fb…`, `bd6aba2f…`): each worker start rejected, `ssh-stderr.log` = `FLEET_WORKER_REJECTED:OSError`; App reason **`REMOTE_EXIT_WITHOUT_CLEANUP`**, battery unavailable. | live dirs (1 PC-start event each), card text |
| 13:31 | User stopped the experiment and powered the robot off (LiDAR observed not spinning). **Stop** pressed on the card for the record (robot disconnected, nothing active); recording stopped at 13:32:23. | chat relay, driver |

Battery curve (robot time s → V): 233→12.37, 288→12.35, 342→12.33, 398→12.30, 454→12.28, 509→12.26, 565→12.26, 621→12.22, 676→12.22, 733→12.26, 789→12.26. Always ≥ 12.22 V; the 11.1 V guard never tripped.

## What is confirmed vs. inferred

Confirmed (records above): the robot-side runtime raised `NATIVE_ARCHIVE_SESSION_JOURNAL_WRITE_FAILED` in its `native_archive` subsystem, then closed control and stopped the LiDAR stream itself (the LiDAR had been streaming at 4.9 Hz with no gaps for 6 minutes). Every later worker start failed with an `OSError` on the robot (`FLEET_WORKER_REJECTED:OSError`). No motion, Arm, Prepare or Bootstrap command was issued in this session.

Inferred (not verified, robot is off): a robot-side storage problem (Raspberry Pi SD card full or read-only / journal directory not writable) — a journal write failure followed by `OSError` on every new worker start fits this; the LiDAR not spinning is the expected consequence of the worker closing the sensor, not evidence of a sensor failure. Robot-side ROS/LDS driver logs were not retrieved (robot off; nothing is restarted remotely without approval). To confirm: on the robot, check free space and write permission of the TwinPulse native-archive/journal directory and the worker's stderr for the 13:19 UTC fault.

## UI problems the operator hit (confirmed on the PC)

1. **Control view squeezes the Robots panel** into a ~250 px strip with inner scrollbars and overlapping text ("Connected · Prepare" over "SIM-world test obstacle · 0"); Details → Physical setup and the three safety checkboxes were unreachable/too small to click. Regression from today's "Twin render ≥ 40vh, robot panel scrolls" CSS change (`0b8b1f4`). Fix after the session: Control view must give the robot panel at least ~60vh when the selected robot is physical, and never clip the confirmation checkboxes.
2. **Checkboxes disappear when the link is DEGRADED/DISCONNECTED** (Physical setup renders blockers instead) with no on-screen sentence saying why. Fix after the session: show "Reconnect first — supervisor confirmations need a live link" in place of the hidden controls.
3. Photo over 5 MiB is rejected ("Choose a JPEG or PNG photo up to 5 MiB") instead of being downscaled; a 1600-px copy was used. Follow-up: auto-downscale in the App.
4. Automation boundary (correct, not a bug): the supervisor confirmations ("I am present…", "I am supervising…", "I reviewed the selected trial…") must be ticked by the operator; the driver only presses the buttons after verifying the box is ticked (`prepare-button`, `arm-button`, `bootstrap-button`).

## Evidence locations (PC)

- `%LOCALAPPDATA%\TwinPulse\runtime\devices\local\physical-fleet-operations\731ec1ef2f944bb18098b8b292381072.jsonl` (6 events + footer), `…\7cd28909…`, `…\129311fb…`, `…\bd6aba2f…`
- `%LOCALAPPDATA%\TwinPulse\runtime\devices\local\physical-live\731ec1ef2f944bb18098b8b292381072\` (30 segments, receipt.json `complete:false`), and the three 1-event dirs with `ssh-stderr.log`
- Driver log `outputs/path-b-20261026/demo-sim/ui-actions.jsonl`; screenshots `H1…H4-connected.png`; recording `rec-physical.mp4`, `rec-physical-part0.mp4`

No credentials, hostnames or tokens appear in this log.
