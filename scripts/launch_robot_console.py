# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Open the robot console; it auto-runs one read-only status check, never motion."""
import argparse
import json
from pathlib import Path
import secrets
import sys
from threading import Event
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))
from twinpulse_app import (ApplicationService, CommandBroker, JsonProviderSettingsStore,
                          LocalApiServer, ProductWorkflow, ProjectStore, ReplayOnlyGateway)
from twinpulse_app.robot_diagnostics import RobotDiagnostics
from twinpulse_app.physical_controller import PhysicalController
from twinpulse_core import InputArtifactStore


class DisabledCredentials:
    target_name = 'robot-console-no-provider'

    def is_configured(self): return False
    def load(self): raise RuntimeError('Provider disabled in robot console')
    def save(self, _value): raise RuntimeError('Provider disabled in robot console')
    def delete(self): raise RuntimeError('Provider disabled in robot console')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pc-only', action='store_true', help='Check only local prerequisites, then exit')
    args = parser.parse_args()
    diagnostics = RobotDiagnostics(ROOT)
    if args.pc_only:
        pc = diagnostics.preflight('pc-only')['pc']
        print(json.dumps(pc, ensure_ascii=True))  # No start token or key content.
        diagnostics.close()
        return 0 if pc['ready'] else 2
    if not (ROOT/'apps/twinpulse-web/dist/index.html').is_file():
        print('Built App missing. Build the existing web project first; nothing installed.')
        return 2
    state = ROOT/'.runtime/robot-console'
    broker = CommandBroker()
    app = ApplicationService(ReplayOnlyGateway(), project_store=ProjectStore(state/'project.json'),
        artifact_store=InputArtifactStore(state/'inputs'), allow_invalid_restore=True)
    workflow = ProductWorkflow(app, broker, mode='simulation_offline',
        generation_settings_getter=lambda: {'request_schema': 'offline-1.0'},
        provider_state_getter=lambda: {'configured': False, 'label': 'Robot console: provider disabled'},
        gateway_factory=ReplayOnlyGateway)
    secret = secrets.token_urlsafe(32)
    server = LocalApiServer(broker, product_bootstrap_secret=secret,
        engine_bootstrap_secret=secrets.token_urlsafe(32), product_workflow=workflow,
        static_root=ROOT/'apps/twinpulse-web/dist', robot_diagnostics=diagnostics,
        physical_controller=PhysicalController(ROOT),
        provider_settings_store=JsonProviderSettingsStore(state/'settings.json'),
        credential_store=DisabledCredentials(), bootstrap_ttl_s=60)
    try:
        server.start()
        print('TwinPulse robot console: no Isaac or provider. One read-only connection check starts after browser session opens.', flush=True)
        print('Failed checks require an explicit Retry; opening the console never starts motors or LiDAR.', flush=True)
        print('Control preparation and movement are separate approved actions. A read-only check does not enable movement.', flush=True)
        print('Keep this window open. Ctrl+C closes this owned console; an active check may take up to120s to finish.', flush=True)
        if not webbrowser.open(server.base_url+'/#robot-console=1&bootstrap='+secret):
            print('Browser did not open. Close this console and try again.')
            return 2
        Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == '__main__': raise SystemExit(main())
