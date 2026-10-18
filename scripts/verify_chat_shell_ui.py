# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual Chrome + ordinary local App/API. Explicit engine-state fixture, not Isaac acceptance."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from threading import Event, Thread
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.integration.test_r5_product_api import R5ProductApiTests, png
from twinpulse_app.conversation_service import ConversationService


def run_case(output, case, node):
    folder = output / case
    folder.mkdir()
    harness = R5ProductApiTests()
    harness.setUp()
    stopped = Event()
    thread = None
    try:
        harness.server._static_root = ROOT / 'apps/twinpulse-web/dist'
        if case == 'history':
            harness.server.conversation._message('user', '지난 침실 프로젝트')
            harness.server.conversation._message('assistant', 'Previous run: provider exceeded 90s timeout', status='failed')
            harness.server.conversation._persist()
            harness.server.conversation = ConversationService(harness.workflow, harness.server.conversation.path)
            harness.server.project_catalog.create_empty('old_room')
            saved = json.loads(harness.server.conversation.path.read_text(encoding='utf-8'))
            saved['project_id'] = 'old_room'
            saved['messages'][0]['content'] = '다른 거실 프로젝트'
            (harness.static / 'projects/old_room/project.conversation.json').write_text(json.dumps(saved), encoding='utf-8')
        original = harness.server.conversation.path.read_bytes() if harness.server.conversation.path.exists() else None
        startup = dict(schema_version='1.0', status='starting', phase='waiting_engine',
                       message='Explicit startup-state fixture; no Isaac process',
                       started_at_utc=datetime.now(timezone.utc).isoformat(),
                       backend=dict(owned=True, state='running'), engine=dict(owned=False, state='starting'),
                       browser=dict(launched=False))
        harness.supervisor_status.write_text(json.dumps(startup), encoding='utf-8')

        def engine_fixture():
            engine_id, epoch = 'explicit-ui-engine', 'explicit-ui-epoch'
            registered = False
            while not stopped.wait(.2):
                if (folder / 'ready.signal').exists():
                    if not registered:
                        startup.update(status='ready', phase='ready', message='Explicit engine-state fixture connected')
                        harness.supervisor_status.write_text(json.dumps(startup), encoding='utf-8')
                        harness.broker.register_engine(engine_id, epoch)
                        registered = True
                    harness.broker.engine_heartbeat(engine_id, epoch)
        thread = Thread(target=engine_fixture, daemon=True)
        thread.start()
        bootstrap = secrets.token_urlsafe(32)
        harness.server._bootstrap['product'] = bootstrap
        image = folder / 'fixture.png'
        image.write_bytes(png())
        env = {**os.environ, 'TWINPULSE_UI_URL': harness.server.base_url,
               'TWINPULSE_UI_BOOTSTRAP': bootstrap, 'TWINPULSE_UI_OUTPUT': str(folder),
               'TWINPULSE_UI_CASE': case, 'TWINPULSE_UI_IMAGE': str(image)}
        completed = subprocess.run([str(node), str(ROOT / 'apps/twinpulse-web/e2e/chat-shell-ui.mjs')],
            cwd=ROOT / 'apps/twinpulse-web', env=env, timeout=90, capture_output=True, text=True, encoding='utf-8')
        result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        result['original_history_unchanged'] = (original is None or harness.server.conversation.path.read_bytes() == original) if case == 'history' else None
        result['engine_state_fixture_only'] = True
        result['actual_isaac_start_or_motion'] = False
        result['broker_operation_count'] = len(harness.broker.public_state('unowned')['operations'])
        result['owned_api_and_browser_closed'] = False
        if completed.returncode or result['broker_operation_count'] or case == 'history' and not result['original_history_unchanged']:
            result['status'] = 'FAIL'
        (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result['status'] == 'PASS'
    finally:
        stopped.set()
        if thread:
            thread.join(3)
        harness.tearDown()
        if 'result' in locals():
            result['owned_api_and_browser_closed'] = not thread or not thread.is_alive()
            (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    expected = ROOT / 'outputs/chat-shell-ui-20261012'
    if expected not in output.parents:
        raise SystemExit('SCOPED_NEW_OWNED_OUTPUT_REQUIRED')
    output.mkdir(parents=True, exist_ok=False)
    results = [run_case(output, case, args.node) for case in ('history', 'empty')]
    (output / 'summary.json').write_text(json.dumps(dict(status='PASS' if all(results) else 'FAIL',
        actual_browser_and_api=True, engine_state_fixture_only=True, provider_requests=0,
        physical_robot_requests=0, source_hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [ROOT/'apps/twinpulse-web/dist/index.html', ROOT/'apps/twinpulse-web/e2e/chat-shell-ui.mjs',Path(__file__)]}), indent=2), encoding='utf-8')
    print('CHAT_SHELL_UI_' + ('PASS' if all(results) else 'FAIL'))
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
