# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Windows-to-Pi SSH diagnostic. No ROS install on Windows; no motor commands."""

import argparse
import ipaddress
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
MARKER = "TWINPULSE_ROBOT_REPORT="


def endpoint(host, user):
    # Accept DNS names and IPv4 only. Never interpolate shell/SSH options from input.
    if not isinstance(host,str) or not 1<=len(host)<=253:raise ValueError('Invalid robot host')
    try:ipaddress.ip_address(host)
    except ValueError:
        if not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',part) for part in host.split('.')):
            raise ValueError("Enter a robot IP address or DNS name, not a URL or command.") from None
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,63}", user):
        raise ValueError("Invalid Linux user name.")
    return f"{user}@{host}"


def payload(distro, domain_id=30, health=False, board=False):
    if distro not in {"auto", "humble", "jazzy"}:
        raise ValueError("Unsupported ROS distribution selection")
    if type(domain_id) is not int or not 0 <= domain_id <= 232:
        raise ValueError("ROS domain ID must be an integer from 0 to 232")
    # Only source a known path; do not guess if two supported installations exist.
    prelude = f"set -e\nexport ROS_DOMAIN_ID={domain_id}\n"
    if health:
        prelude += 'export TWINPULSE_HEALTH=1\nexport ROS_LOCALHOST_ONLY=1\n'
    if board:
        if not health:
            raise ValueError('Board snapshot requires the health profile')
        prelude += 'export TWINPULSE_BOARD_SNAPSHOT=1\n'
    if distro == "auto":
        prelude += ('if [ -f /opt/ros/humble/setup.bash ] && [ ! -f /opt/ros/jazzy/setup.bash ]; then . /opt/ros/humble/setup.bash; '
                    'elif [ -f /opt/ros/jazzy/setup.bash ] && [ ! -f /opt/ros/humble/setup.bash ]; then . /opt/ros/jazzy/setup.bash; fi\n')
    else:
        prelude += f"if [ -f /opt/ros/{distro}/setup.bash ]; then . /opt/ros/{distro}/setup.bash; fi\n"
    source = (ROOT / "scripts/robot_health.py").read_text(encoding="utf-8") + '\n' + (ROOT / "scripts/turtlebot_probe.py").read_text(encoding="utf-8")
    return prelude + "python3 - <<'TWINPULSE_READONLY_PY'\n" + source + "\nTWINPULSE_READONLY_PY\n"


def parse_report(output):
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    records = [line[len(MARKER):] for line in output.splitlines() if line.startswith(MARKER)]
    if len(records) != 1:
        raise ValueError("No unique robot report; Python/SSH/startup may have failed.")
    result = json.loads(records[0])
    if (result.get("schema_version") != "robot-connection-1.0"
            or result.get("mode") != "read_only" or result.get("motion_authorized") is not False
            or result.get("physical_identity_verified") is not False
            or result.get("status") not in {"ROS_PYTHON_UNAVAILABLE", "SENSOR_MESSAGES_RECEIVED",
                                            "PARTIAL_SENSOR_DATA", "NO_SENSOR_DATA", "ROS_PROBE_FAILED"}):
        raise ValueError("Unsupported robot report")
    return result


def write_report(result, output):
    output.mkdir(parents=True, exist_ok=False)
    data = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
    (output / "report.json").write_text(data, encoding="utf-8")
    health = result.get('health', {})
    board = health.get('board', {})
    headline = health.get('status', result['status'])
    summary = ''
    if health:
        battery = (f"{board['voltage_v']:.2f} V / estimated {board['estimated_percent']:.1f}%"
                   if board.get('status') == 'OBSERVED' else 'Unavailable')
        summary = '<p>Battery: ' + html.escape(battery) + '</p><ul>' + ''.join(
            '<li>' + html.escape(item) + '</li>' for item in health.get('issues', [])) + '</ul>'
        summary += '<p>Full physical stop qualification: incomplete. Sensors may be offline while drivers are stopped.</p>'
    page = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>TwinPulse Robot Check</title>'
            '<style>body{background:#101722;color:#e4eef8;font:18px Arial;max-width:1000px;margin:40px auto;padding:20px}'
            'pre{background:#1e2c40;padding:20px;white-space:pre-wrap;overflow-wrap:anywhere}strong{color:#7bdec3}</style>'
            '<h1>TwinPulse · Robot connection check</h1><p><strong>' + html.escape(headline) + '</strong></p>' + summary +
            '<p>READ ONLY · No motor command · No photo or room measurement required.</p>'
            '<p>This report does not approve physical movement. Sensor identity, time, TF and safety need separate verification.</p>'
            '<pre>' + html.escape(data) + '</pre></html>')
    (output / "report.html").write_text(page, encoding="utf-8")
    return output / "report.html"


def collect_readonly(host, user, distro='auto', domain_id=86, health=True, board=True,
                     identity_file=None, batch=True, *, port=22, known_hosts=None):
    """Shared CLI/App entry. One bounded SSH read; no launch, retry or deployment."""
    target = endpoint(host, user)
    if type(port) is not int or not 1<=port<=65535:raise ValueError('Invalid SSH port')
    script = payload(distro, domain_id, health, board)
    ssh = shutil.which("ssh.exe" if sys.platform == "win32" else "ssh")
    if not ssh:
        return {"status": "SSH_CLIENT_MISSING", "motion_authorized": False}
    command = [ssh, "-o", "ConnectTimeout=5", "-o", "ConnectionAttempts=1",
               "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=6", "-o", "TCPKeepAlive=yes",
               "-o", "StrictHostKeyChecking=" + ("yes" if batch else "ask"),
               "-o", "BatchMode=" + ("yes" if batch else "no"),
               "-o", "ClearAllForwardings=yes", "-o", "ForwardAgent=no",
               "-o", "PermitLocalCommand=no", '-o', 'ProxyCommand=none', '-o', 'ProxyJump=none',
               '-p',str(port),target, "bash --noprofile --norc -s"]
    if known_hosts:command[1:1]=['-o','UserKnownHostsFile='+str(Path(known_hosts).resolve())]
    if identity_file:
        command[1:1] = ['-i', str(Path(identity_file).resolve()), '-o', 'IdentitiesOnly=yes']
    try:
        completed = subprocess.run(command, input=script.encode("utf-8"), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=120, check=False)
        if completed.returncode:
            stderr = completed.stderr or b''
            diagnostic = (stderr.decode('utf-8', errors='replace') if isinstance(stderr, bytes)
                          else str(stderr))[-4096:].strip()
            return {"status": "SSH_OR_REMOTE_SETUP_FAILED", "exit_code": completed.returncode,
                    "reason": diagnostic or "SSH_EXIT_NONZERO_NO_STDERR",
                    "motion_authorized": False}
        return parse_report(completed.stdout)
    except subprocess.TimeoutExpired:
        return {"status": "CONNECTION_CHECK_TIMEOUT", "motion_authorized": False}
    except (ValueError, OSError):
        return {"status": "CHECK_FAILED", "motion_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host")
    parser.add_argument("--user")
    parser.add_argument('--port',type=int,default=22)
    parser.add_argument('--profile', choices=('generic', 'twinpulse-burger'), default='generic')
    parser.add_argument('--identity-file', type=Path, help='Existing SSH private key path; contents are never read by this program')
    parser.add_argument('--board-snapshot', action='store_true', help='Use the digest-pinned PING/READ backend when serial is idle')
    parser.add_argument("--ros-distro", choices=("auto", "humble", "jazzy"), default="auto")
    parser.add_argument("--domain-id", type=int, default=None,
                        help="Must match robot bringup; 30 is the ROBOTIS example, not an auto-detected value")
    parser.add_argument("--batch", action="store_true", help="Use existing SSH keys; never prompt for authentication")
    parser.add_argument("--open-report", action="store_true")
    args = parser.parse_args()
    profiled = args.profile == 'twinpulse-burger'
    if args.domain_id is None:
        args.domain_id = 86 if profiled else 30
    host = args.host or ('192.168.35.139' if profiled else input("Robot IP address or host name: ").strip())
    user = args.user or ('twinpulse' if profiled else input("Robot Linux user (set during OS setup): ").strip())
    try:
        target = endpoint(host, user)
        script = payload(args.ros_distro, args.domain_id, profiled, args.board_snapshot)
    except ValueError as exc:
        print(str(exc))
        return 2
    ssh = shutil.which("ssh.exe" if sys.platform == "win32" else "ssh")
    if not ssh:
        raise SystemExit("OpenSSH client is missing. No system component was installed.")
    print("Checking only the specified robot. Verify its SSH fingerprint; do not accept an unknown device.")
    print("Passwords are handled by SSH, not stored in TwinPulse. This does not start robot drivers.")
    print(f"Diagnostic ROS_DOMAIN_ID={args.domain_id}; override --domain-id if the robot uses another domain.")
    result = collect_readonly(host, user, args.ros_distro, args.domain_id, profiled,
                              args.board_snapshot, args.identity_file, args.batch,port=args.port)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    page = write_report(result, ROOT / "artifacts/robot-checks" / run_id)
    print(result.get('health', {}).get('status', result['status']) + "\nReport: " + str(page))
    if 'health' in result:
        print('Sensor streams: ' + result['status'] + '; physical motion permission: not granted')
        storage = result['health'].get('storage') or {}
        if storage:
            print('Robot disk: %s GiB free (%s); session evidence: %s sessions, %s GiB (%s)' % (
                storage.get('root_free_gib'), storage.get('state'), storage.get('sessions_count'),
                storage.get('sessions_gib'), storage.get('sessions_dir')))
    if args.open_report:
        webbrowser.open(page.as_uri())
    if profiled:
        return 0 if result.get('health', {}).get('status') == 'IDLE_SNAPSHOT_OK' else 2
    return 0 if result["status"] == "SENSOR_MESSAGES_RECEIVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
