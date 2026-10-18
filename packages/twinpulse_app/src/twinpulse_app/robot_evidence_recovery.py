# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit post-session evidence transfer only; never starts a robot operation."""
import json
from pathlib import Path
import re
import threading

from .command_broker import BrokerError
from .robot_evidence_export import MODE_FILES, export_finished_session


class RobotEvidenceRecovery:
    def __init__(self, root, *, exporter=export_finished_session):
        self.root = Path(root).resolve()
        self.exporter = exporter
        self.lock = threading.RLock()
        self.thread = None
        self.state = {'status': 'NOT_STARTED', 'job_id': None, 'transfer_only': True}
        self.requests = {}

    def snapshot(self, owner):
        with self.lock:
            if self.state.get('owner') != owner:
                return {'status': 'NOT_STARTED', 'job_id': None, 'transfer_only': True}
            return {k: v for k, v in self.state.items() if k != 'owner'}

    def start(self, owner, job_id, request_id, *, operation_busy=False):
        if (not isinstance(job_id, str) or re.fullmatch('[a-f0-9]{32}', job_id) is None
                or not isinstance(request_id, str) or re.fullmatch('[a-f0-9]{32}', request_id) is None):
            raise BrokerError('evidence_recovery_request_invalid', 'Saved job and request IDs are required', status=400)
        with self.lock:
            previous = self.requests.get(request_id)
            if previous is not None:
                if previous != (owner, job_id):
                    raise BrokerError('evidence_recovery_request_used', 'Request ID belongs to another job', status=409)
                if self.state.get('owner') == owner and self.state.get('job_id') == job_id:
                    return self.snapshot(owner)
                raise BrokerError('evidence_recovery_request_used', 'Request ID was already consumed', status=409)
            if operation_busy or self.thread and self.thread.is_alive():
                raise BrokerError('evidence_recovery_busy', 'Wait for the current operation or transfer', status=409)
            base = self.root/'artifacts/manual-control'
            target = base/job_id
            report_path = target/'robot-report.json'
            if ((self.root/'artifacts').is_symlink() or base.is_symlink()
                    or target.is_symlink() or report_path.is_symlink()
                    or not target.resolve().is_relative_to(self.root)
                    or not report_path.is_file() or report_path.stat().st_size > 512 * 1024):
                raise BrokerError('evidence_report_unavailable', 'Saved robot report is unavailable', status=409)
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
                from .robot_adapters import checked_binding, legacy_binding
                binding_path=target/'robot-binding.json'
                if binding_path.exists():
                    if binding_path.is_symlink() or binding_path.stat().st_size>8192:raise ValueError('ROBOT_BINDING_UNSAFE')
                    binding=checked_binding(json.loads(binding_path.read_text(encoding='utf-8')))
                else:
                    # Pre-registry sessions used exactly this reviewed endpoint.
                    result_path=target/'result.json'
                    if result_path.exists():
                        if result_path.is_symlink() or result_path.stat().st_size>512*1024:raise ValueError('ROBOT_BINDING_UNSAFE')
                        if 'robot_binding' in json.loads(result_path.read_text(encoding='utf-8')):
                            raise ValueError('ROBOT_BINDING_MISSING')
                    binding=legacy_binding()
            except (OSError, ValueError, TypeError) as exc:
                raise BrokerError('evidence_report_invalid', 'Saved robot report is invalid', status=409) from exc
            if (not isinstance(report, dict) or report.get('mode') not in MODE_FILES
                    or not isinstance(report.get('robot_session_id'), str)
                    or re.fullmatch('manual-[a-f0-9]{32}', report['robot_session_id']) is None
                    or not isinstance(report.get('boot_id'), str) or not report['boot_id']
                    or not isinstance(report.get('release_id'), str) or not report['release_id']):
                raise BrokerError('evidence_report_invalid', 'Saved robot report is invalid', status=409)
            if len(self.requests) >= 128:
                raise BrokerError('evidence_recovery_limit', 'Restart the idle App before another transfer', status=409)
            self.requests[request_id] = (owner, job_id)
            self.state = {'status': 'TRANSFERRING', 'job_id': job_id,
                          'transfer_only': True, 'owner': owner, 'receipt': None, 'reason': None}
            self.thread = threading.Thread(target=self._run, args=(report, target, binding),
                                           name='TwinPulseEvidenceTransfer', daemon=True)
            self.thread.start()
            return self.snapshot(owner)

    def _run(self, report, target, binding):
        try:
            receipt = (self.exporter(report, target/'robot-evidence',robot_binding=binding)
                       if self.exporter is export_finished_session else self.exporter(report, target/'robot-evidence'))
            with self.lock:
                self.state['status'] = 'COMPLETE' if receipt.get('status') == 'COMPLETE' else 'INCOMPLETE'
                self.state['receipt'] = str(target/'robot-evidence'/'export.json')
                self.state['reason'] = None if self.state['status'] == 'COMPLETE' else 'EVIDENCE_INCOMPLETE'
        except Exception as exc:
            with self.lock:
                self.state['status'] = 'INCOMPLETE'
                self.state['reason'] = type(exc).__name__
