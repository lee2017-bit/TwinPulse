# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Optional, local execution diagnostics. Never used to authorize an operation.

Contexts are passed explicitly across threads; clocks identify one process, not
just one computer. Events contain only allowlisted scalar metadata, never input
text, image bytes, credentials, exception messages or arbitrary filesystem paths.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from itertools import islice
import json
import math
import os
from pathlib import Path
from queue import Queue, Empty, Full
import re
from threading import Event, Lock, RLock, Thread, get_ident
import time
from uuid import uuid4

_CLOCK = uuid4().hex
_PROFILE_GUARD = Lock()  # cProfile's monitoring tool slot is interpreter-wide.
_ID = re.compile(r"[a-f0-9]{32}")
_CHUNK = re.compile(r"events-(\d{4})\.jsonl")
_DIGEST = re.compile(r"[a-f0-9]{64}")
_COMPONENT = re.compile(r"[a-z][a-z0-9_]{0,31}")
_SAFE = re.compile(r"[A-Za-z0-9_.:/-]{1,160}")
_FIELDS = frozenset({
    "workflow_id", "operation_id", "generation_id", "request_id", "attempt_id",
    "command_id", "engine_session_id", "run_id", "plan_id", "robot_session_id",
    "boot_id", "release_id", "mission_id", "task_id", "leg_id", "retry_of",
    "project_id", "mode", "input_kind", "input_revision", "draft_revision",
    "model_id", "provider_name", "stage", "error_code", "error_type", "role",
    "request_sha256", "schema_sha256", "response_sha256", "stored_response_sha256",
    "image_count", "max_tokens", "http_status", "finish_reason", "cancelled",
    "prompt_tokens", "completion_tokens", "total_tokens", "elapsed_s",
    "output_pattern", "final_empty", "visible_chars", "visible_nonwhitespace_chars",
    "visible_trailing_whitespace_chars", "reasoning_chars", "reasoning_nonwhitespace_chars", "reasoning_tokens",
    "persisted", "remote_outcome", "automatic_retry", "timer_basis",
    "evidence_kind", "evidence_id", "profile_id", "profiled_elapsed_s",
    "function", "source_file", "source_line", "calls", "self_s", "cumulative_s", "chat_request_id",
    "reported_clock_instance_id", "measurement_source",
    "frame_id", "frame_sha256",
    "browser_metadata_ms", "browser_image_ms", "browser_decode_ms", "browser_poll_ms",
    "browser_frame_age_ms", "browser_schedule_lag_ms",
    "source_scene_revision", "scene_edit_revision", "artifact_id", "scene_edit_execution_id",
    "launch_id", "launch_execution_id", "failed_span_id", "scene_change_sha256",
    "command_execution_id", "stage_epoch", "runtime_state", "safety_state", "snapshot_sequence",
    "map_revision", "alignment_revision", "correction_revision", "goal_room_revision", "semantic_stage",
    "policy_sha256", "checkpoint_id", "parent_checkpoint_id", "semantic_revision",
    "requests", "max_requests", "repairs", "max_repairs", "stop_reason",
    "plan_sha256",
    "context_sha256", "scene_state_sha256", "parent_state_sha256", "result_state_sha256", "preview_sha256",
    "transaction_state", "journal_sha256",
    "control_lease_refresh_phase", "control_lease_owned_before_refresh", "expected_engine_identity_current",
    "feedback_execution_id", "feedback_operation_id", "feedback_request_id", "feedback_approval_id",
    "feedback_response_sha256", "feedback_context_sha256", "feedback_preview_execution_id",
    "sensor_map_id", "sensor_execution_id", "sensor_raw_sha256", "sensor_evidence_sha256",
    "sensor_alignment_sha256", "sensor_binding_sha256", "sensor_status",
    "diagnostic_sha256", "termination_code", "candidate_count", "accepted_count",
    "profiler_kind", "profile_status", "profile_valid", "profile_row_count",
})
_STATUSES = {"running", "succeeded", "failed", "cancelled", "skipped", "unknown"}


class DiagnosticQueryError(ValueError):
    """Invalid selectors, distinct from inaccessible diagnostic storage."""


def metadata(values):
    """Positive allowlist; even known string fields cannot contain free prose."""
    result = {}
    for key, value in values.items():
        if key not in _FIELDS or value is None:
            continue
        if key in {'control_lease_owned_before_refresh','expected_engine_identity_current'}:
            if type(value) is bool:result[key]=value
            continue
        if key=='control_lease_refresh_phase':
            if type(value) is str and value in {'before_dispatch','compensation'}:result[key]=value
            continue
        if key in {'map_revision','alignment_revision','correction_revision','goal_room_revision',
                'context_sha256','scene_state_sha256','parent_state_sha256','result_state_sha256','preview_sha256','journal_sha256',
                'feedback_response_sha256','feedback_context_sha256','sensor_raw_sha256',
                'sensor_evidence_sha256','sensor_alignment_sha256','sensor_binding_sha256'}:
            if type(value) is str and _DIGEST.fullmatch(value):result[key]=value
            continue
        if type(value) is bool or type(value) is int:
            result[key] = value
        elif type(value) is float and math.isfinite(value):
            result[key] = value
        elif isinstance(value, str) and _SAFE.fullmatch(value) and not value.lower().startswith(("bearer", "data:", "http")):
            if key in {'source_file','function'} and ('/' in value or ':' in value):
                continue
            result[key] = value
    return result


def _stamp():
    return {"at": datetime.now(timezone.utc).isoformat(), "monotonic_ns": time.monotonic_ns(),
            "clock_domain": "process_monotonic", "clock_instance_id": _CLOCK}


@dataclass(frozen=True)
class TraceContext:
    store: ExecutionStore
    execution_id: str
    span_id: str
    _finished: Event = field(default_factory=Event,repr=False,compare=False)
    _root: bool = field(default=False,repr=False,compare=False)
    component: str = "app"

    def bind(self, **values):
        self.store.emit(self, "references", values)

    def child(self, stage: str, *, component=None, **values):
        component = component or self.component
        if not _COMPONENT.fullmatch(component):
            raise ValueError('invalid diagnostic component')
        child = TraceContext(self.store, self.execution_id, uuid4().hex, component=component)
        self.store.emit(child, "span_started", {"stage": stage, **values}, parent_span_id=self.span_id)
        return child

    def finish(self, status="succeeded", *, error=None, role="primary", **values):
        if status not in _STATUSES or status == "running":
            raise ValueError("invalid terminal diagnostic status")
        if role != 'primary':
            values = {**values, "role": role}
        if error is not None:
            values = {**values, "error_type": type(error).__name__, "role": role}
            code = getattr(error, "code", None)
            if code:
                values["error_code"] = code
        self.store.emit(self, "span_finished", values, status=status)

    @contextmanager
    def span(self, stage: str, **values):
        child = self.child(stage, **values)
        try:
            yield child
        except BaseException as error:
            child.finish("cancelled" if type(error).__name__ in {"CancelledError", "GenerationCancelledError"} else "failed", error=error)
            raise
        else:
            child.finish()


class ExecutionStore:
    """One bounded writer, lazy files; optional sink failures never fail control.

Root manifests are fsynced before dispatch. Later events use a bounded queue;
terminal events have reserved slots. No retention deletes raw evidence. Full
stores reject diagnostic writes, not execution, and visibly report degradation.
"""
    def __init__(self, root: Path, project_id: str, *, queue_limit=1024,
                 execution_limit=64 * 1024 * 1024, total_limit=512 * 1024 * 1024,
                 chunk_limit=8 * 1024 * 1024, default_refs=None):
        self.root, self.project_id = Path(root), project_id
        self.execution_limit, self.total_limit = execution_limit, total_limit
        self.chunk_limit = max(8192, min(chunk_limit, execution_limit))
        self.default_refs=metadata(default_refs or {})
        self._queue = Queue(queue_limit)
        self._terminal = Queue(16)
        self._lock = RLock()
        self._io_lock = RLock()
        self._writer_generation = None
        self._worker = None
        self._sequence = 0
        self._failures = 0
        self._dropped = 0
        from collections import OrderedDict
        self._sizes = OrderedDict()
        self._total_size = None

    @property
    def health(self):
        with self._lock:
            return {"diagnostics_degraded": bool(self._failures or self._dropped),
                    "storage_errors": self._failures, "dropped_events": self._dropped}

    def note_storage_error(self):
        """Count an optional sink failure without retaining exception contents."""
        with self._lock:
            self._failures += 1

    def _directory(self, execution_id, *, create=False):
        if not _ID.fullmatch(execution_id):
            raise ValueError("invalid execution identity")
        # Reject symlinks/junctions at every existing component, not only leaf.
        for candidate in (self.root, *self.root.parents):
            if candidate.is_symlink() or (hasattr(candidate, "is_junction") and candidate.is_junction()):
                raise ValueError("diagnostic location is linked")
        directory = self.root / execution_id
        if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()):
            raise ValueError("diagnostic location is linked")
        if create:
            directory.mkdir(parents=True, exist_ok=False)
        return directory

    @contextmanager
    def _write_guard(self):
        """Nonblocking cross-process reservation; only disk writers enter here.

        The fixed 8-byte marker invalidates another writer's quota cache. An
        odd value means a writer exited during its write, so the next owner
        rescans. Contention loses optional diagnostics visibly, never waits
        in a motor/watchdog path, and never replays the underlying operation.
        """
        with self._io_lock:
            self._directory('0'*32)
            self.root.mkdir(parents=True,exist_ok=True)
            path=self.root/'writer.lock'
            if path.is_symlink():raise ValueError('diagnostic writer lock is linked')
            flags=os.O_CREAT|os.O_RDWR|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)
            with os.fdopen(os.open(path,flags,0o600),'r+b') as stream:
                if os.fstat(stream.fileno()).st_nlink!=1:raise ValueError('diagnostic writer lock is linked')
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                try:
                    marker=stream.read(9)
                    if len(marker) not in (0,8):raise ValueError('invalid diagnostic writer marker')
                    generation=int.from_bytes(marker,'little')
                    if generation>=2**64-2:raise ValueError('diagnostic writer marker exhausted')
                    if generation!=self._writer_generation or generation%2:
                        self._total_size=None;self._sizes.clear()
                    pending=(generation//2+1)*2-1
                    stream.seek(0);stream.write(pending.to_bytes(8,'little'));stream.flush()
                    try:
                        yield
                    except BaseException:
                        self._total_size=None;self._sizes.clear()
                        raise
                    finally:
                        committed=pending+1
                        stream.seek(0);stream.write(committed.to_bytes(8,'little'));stream.flush()
                        self._writer_generation=committed
                finally:
                    stream.seek(0)
                    if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                    else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

    def begin(self, stage: str, *, durable=True, component="app", **values):
        values={**self.default_refs,**values}
        if not _COMPONENT.fullmatch(component):
            raise ValueError('invalid diagnostic component')
        identity = uuid4().hex
        context = TraceContext(self, identity, uuid4().hex, _root=True, component=component)
        manifest = {"schema_version": "1.1", "execution_id": identity, "component":component,
                    "root_span_id": context.span_id, "project_id": self.project_id,
                    "stage": stage, **_stamp(), "metadata": metadata(values)}
        encoded=json.dumps(manifest,ensure_ascii=True).encode('utf-8')
        if not durable:
            with self._lock:
                try:
                    self._queue.put_nowait((identity, encoded, 'manifest'))
                except Full:
                    self._dropped += 1
            self.emit(context, 'span_started', {'stage': stage, **values})
            return context
        try:
            if len(encoded)>8192:raise ValueError('diagnostic manifest exceeds limit')
            with self._write_guard():
                self._budget(identity, len(encoded))
                directory = self._directory(identity, create=True)
                with (directory / "manifest.json").open("xb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
        except (OSError, ValueError):
            with self._lock:
                self._failures += 1
        self.emit(context, "span_started", {"stage": stage, **values})
        return context

    def emit(self, context, event_type, values, *, parent_span_id=None, status=None):
        with self._lock:
            if event_type == "span_finished":
                if context._finished.is_set():
                    return  # Late completion cannot rewrite a terminal result.
                context._finished.set()
            self._sequence += 1
            item = {"schema_version":"1.1", "event_id":uuid4().hex, "component":context.component,
                    "sequence": self._sequence, "type": event_type,
                    "execution_id": context.execution_id, "span_id": context.span_id,
                    **_stamp(), "metadata": metadata(values)}
            if parent_span_id:
                item["parent_span_id"] = parent_span_id
            if status:
                item["status"] = status
            if event_type=='span_finished' and context._root:
                item['diagnostic_health']=self.health
            data = (json.dumps(item, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
            if len(data) > 8192:
                self._dropped += 1
                return
            try:
                self._queue.put_nowait((context.execution_id, data, 'terminal' if context._root and status else 'events'))
            except Full:
                try:
                    if event_type != "span_finished":
                        raise Full
                    self._terminal.put_nowait((context.execution_id, data, 'terminal' if context._root and status else 'events'))
                except Full:
                    self._dropped += 1
            if self._worker is None:
                self._worker = Thread(target=self._write, name="TwinPulseDiagnostics", daemon=True)
                self._worker.start()

    def _budget(self, identity, added, *, reset=False, terminal=False):
        with self._io_lock:
            if self._total_size is None or reset:
                self._sizes.clear()
                self._total_size = 0
                if self.root.exists():
                    marker=self.root/'writer.lock'
                    if marker.exists():
                        if marker.is_symlink() or marker.stat().st_nlink!=1 or marker.stat().st_size>8:
                            raise ValueError('invalid diagnostic writer marker')
                        self._total_size+=marker.stat().st_size
                    for directory in self.root.iterdir():
                        if _ID.fullmatch(directory.name):
                            checked = self._directory(directory.name)
                            size = self._stored_size(checked)
                            self._sizes[directory.name] = size
                            while len(self._sizes)>4096:self._sizes.popitem(last=False)
                            self._total_size += size
                    links = self._link_directory()
                    if links.exists():
                        paths=list(islice(links.iterdir(),4097))
                        if len(paths)>4096:raise ValueError('diagnostic link count exceeds limit')
                        for path in paths:
                            if path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size>8192:
                                raise ValueError('invalid diagnostic link')
                            self._total_size += path.stat().st_size
            size = self._sizes.get(identity)
            if size is None:
                directory=self._directory(identity)
                size=self._stored_size(directory) if directory.exists() else 0
            execution_cap=self.execution_limit if terminal else max(0,self.execution_limit-min(16384,self.execution_limit//16))
            total_cap=self.total_limit if terminal else max(0,self.total_limit-min(1024*1024,self.total_limit//16))
            if size + added > execution_cap or self._total_size + added > total_cap:
                raise OSError("diagnostic quota exceeded")
            self._sizes[identity] = size + added
            self._sizes.move_to_end(identity)
            while len(self._sizes)>4096:self._sizes.popitem(last=False)
            self._total_size += added

    @staticmethod
    def _stored_size(directory):
        return sum(f.stat().st_size for f in directory.iterdir()
                   if (f.name in {'manifest.json', 'events.jsonl'} or _CHUNK.fullmatch(f.name))
                   and not f.is_symlink())

    def _event_paths(self, directory):
        paths = []
        for index, path in enumerate(directory.iterdir()):
            if index >= 4096:
                raise ValueError('diagnostic event directory exceeds limit')
            match = _CHUNK.fullmatch(path.name)
            if path.name == 'events.jsonl' or match:
                if path.is_symlink() or path.stat().st_nlink != 1:
                    raise ValueError('diagnostic event file is linked')
                paths.append((int(match[1]) if match else 0, path))
                if len(paths) > 128:
                    raise ValueError('diagnostic event chunks exceed limit')
        # Includes a damaged or missing chunk in the quota, never delete/rewrite.
        if len(paths) > 128 or sum(p.stat().st_size for _, p in paths) > self.execution_limit:
            raise ValueError('diagnostic events exceed limit')
        return [p for _, p in sorted(paths)]

    def _event_lines(self, directory, *, read_limit=None):
        consumed = 0
        for path in self._event_paths(directory):
            with path.open('rb') as stream:
                # readline(size) avoids allocating an arbitrarily large line.
                while line := stream.readline(8193):
                    if len(line) > 8192:
                        raise ValueError('diagnostic event exceeds limit')
                    consumed += len(line)
                    if read_limit is not None and consumed > read_limit:
                        raise ValueError('diagnostic read budget exceeded')
                    yield line.decode('utf-8')

    def _write(self):
        while True:
            try:
                entry = self._queue.get(timeout=.25)
                source = self._queue
            except Empty:
                with self._lock:
                    try:
                        entry = self._terminal.get_nowait()
                        source = self._terminal
                    except Empty:
                        if self._queue.empty():
                            self._worker = None
                            return
                        continue
            try:
                with self._write_guard():self._write_entry(*entry)
            except (OSError, ValueError):
                with self._lock:
                    self._failures += 1
            finally:
                source.task_done()

    def _write_entry(self, identity, data, kind):
        if kind == 'manifest':
            self._budget(identity,len(data))
            directory=self._directory(identity,create=True)
            with (directory/'manifest.json').open('xb') as stream:stream.write(data)
            return
        directory=self._directory(identity)
        if kind=='terminal':
            terminal_item=json.loads(data);terminal_item['diagnostic_health']=self.health
            data=(json.dumps(terminal_item,separators=(',',':'))+'\n').encode()
        paths=self._event_paths(directory)
        target=paths[-1] if paths else directory/'events.jsonl'
        if target.exists() and target.stat().st_size+len(data)>self.chunk_limit:
            match=_CHUNK.fullmatch(target.name);index=int(match[1])+1 if match else 1
            target=directory/f'events-{index:04d}.jsonl'
            if target.exists() or index>=128:raise ValueError('diagnostic chunk rollover unavailable')
        self._budget(identity,len(data),terminal=kind=='terminal')
        with target.open('ab') as stream:stream.write(data)

    def flush(self, timeout=2.0):
        # Developer reads/tests only. Motor/watchdog paths never call flush.
        deadline = time.monotonic() + timeout
        while (self._queue.unfinished_tasks or self._terminal.unfinished_tasks) and time.monotonic() < deadline:
            time.sleep(.005)
        return not (self._queue.unfinished_tasks or self._terminal.unfinished_tasks)

    def _manifest(self, identity):
        directory = self._directory(identity)
        manifest_path = directory / "manifest.json"
        if manifest_path.is_symlink() or (manifest_path.exists() and manifest_path.stat().st_nlink != 1):
            raise ValueError("diagnostic manifest is linked")
        if manifest_path.stat().st_size > 8192:
            raise ValueError('diagnostic manifest exceeds limit')
        with manifest_path.open('rb') as stream:
            encoded = stream.read(8193)
        if len(encoded) > 8192:
            raise ValueError('diagnostic manifest exceeds limit')
        manifest = json.loads(encoded.decode('utf-8'))
        if not isinstance(manifest,dict):
            raise ValueError('invalid diagnostic manifest')
        if manifest.get("project_id") != self.project_id or manifest.get("execution_id") != identity:
            raise ValueError("diagnostic project mismatch")
        allowed = {'schema_version','execution_id','root_span_id','project_id','stage',
                   'at','monotonic_ns','clock_domain','clock_instance_id','metadata'}
        version=manifest.get('schema_version')
        if (type(version) is not str or
                set(manifest) != (allowed | {'component'} if version=='1.1' else allowed) or version not in {'1.0','1.1'} or
                (version=='1.1' and (type(manifest.get('component')) is not str or not _COMPONENT.fullmatch(manifest['component']))) or
                manifest.get('clock_domain') != 'process_monotonic' or type(manifest.get('root_span_id')) is not str or
                not _ID.fullmatch(manifest['root_span_id']) or type(manifest['metadata']) is not dict or
                type(manifest['monotonic_ns']) is not int or type(manifest['stage']) is not str or
                not _SAFE.fullmatch(manifest['stage']) or type(manifest['clock_instance_id']) is not str or
                not _ID.fullmatch(manifest['clock_instance_id']) or type(manifest['at']) is not str or len(manifest['at'])>40):
            raise ValueError('invalid diagnostic manifest')
        datetime.fromisoformat(manifest['at'])
        manifest['metadata'] = metadata(manifest['metadata'])
        return directory, manifest

    def detail(self, identity, *, read_limit=None):
        directory, manifest = self._manifest(identity)
        from collections import deque
        events = deque(maxlen=8192)
        first_error = None
        event_count = 0
        malformed_events = 0
        duplicate_events = 0
        from collections import OrderedDict
        seen = OrderedDict()
        stages = OrderedDict({manifest['root_span_id']:manifest['stage']})
        historical_health={}
        if directory.exists():
            for line in self._event_lines(directory, read_limit=read_limit):
                    if len(line) > 8192:
                        raise ValueError("diagnostic event exceeds limit")
                    try:
                        item = json.loads(line)
                    except ValueError:
                        malformed_events += 1
                        continue  # Partial last write after a crash is not PASS.
                    allowed_event={'sequence','type','execution_id','span_id','at','monotonic_ns',
                                   'clock_domain','clock_instance_id','metadata','parent_span_id','status','diagnostic_health',
                                   'schema_version','event_id','component'}
                    if (type(item) is dict and set(item) <= allowed_event and
                            (not {'schema_version','event_id','component'} & set(item) or
                             (item.get('schema_version')=='1.1' and type(item.get('event_id')) is str and _ID.fullmatch(item['event_id']) and
                              type(item.get('component')) is str and _COMPONENT.fullmatch(item['component']))) and
                            item.get('execution_id')==identity and type(item.get('span_id')) is str and _ID.fullmatch(item['span_id']) and
                            type(item.get('type')) is str and item['type'] in {'span_started','span_finished','references','profile_row'} and
                            type(item.get('monotonic_ns')) is int and type(item.get('sequence')) is int and
                            type(item.get('at')) is str and len(item['at'])<=40 and
                            item.get('clock_domain')=='process_monotonic' and
                            type(item.get('clock_instance_id')) is str and len(item['clock_instance_id'])<=80 and
                            type(item.get('status','running')) is str and item.get('status','running') in _STATUSES and
                            (item.get('type') != 'span_finished' or 'status' in item) and
                            ('parent_span_id' not in item or (type(item['parent_span_id']) is str and _ID.fullmatch(item['parent_span_id']))) and
                            type(item.get('metadata')) is dict):
                        item["metadata"] = metadata(item.get("metadata", {}))
                        try:
                            datetime.fromisoformat(item['at'])
                        except ValueError:
                            malformed_events += 1
                            continue
                        identity_key=item.get('event_id') or (item['clock_instance_id'],item['sequence'])
                        if identity_key in seen:
                            duplicate_events += 1
                            continue
                        seen[identity_key]=True
                        while len(seen)>8192:seen.popitem(last=False)
                        if item['type']=='span_started':
                            stages[item['span_id']]=item['metadata'].get('stage')
                            while len(stages)>8192:stages.popitem(last=False)
                        supplied=item.get('diagnostic_health')
                        if type(supplied) is dict:
                            checked_health={key:supplied[key] for key in ('diagnostics_degraded','storage_errors','dropped_events') if
                                            type(supplied.get(key)) in (bool,int) and supplied[key]>=0}
                            item['diagnostic_health']=checked_health
                            historical_health=checked_health
                        if first_error is None and item.get('status') in {'failed','unknown'} and item['metadata'].get('role','primary')=='primary':
                            first_error = metadata({**item['metadata'],'failed_span_id':item['span_id'],
                                                    'stage':stages.get(item['span_id'])})
                        events.append(item)
                        event_count += 1
                    else:
                        malformed_events += 1
        events = sorted(events, key=lambda e: (e['monotonic_ns'],e['sequence']))
        spans = {manifest['root_span_id']:{'span_id':manifest['root_span_id'], 'status':'unknown',
                 'metadata':metadata(manifest['metadata']), 'stage':manifest['stage'], 'parent_span_id':None, 'start':manifest}}
        for event in events:
            span = spans.setdefault(event["span_id"], {"span_id": event["span_id"], "status": "unknown", "metadata": {}})
            span["metadata"].update(event["metadata"])
            if event["type"] == "span_started":
                span.update(parent_span_id=event.get("parent_span_id"), stage=event["metadata"].get("stage"), start=event)
            elif event["type"] == "span_finished" and "end" not in span:
                span.update(status=event["status"], end=event)
        for span in spans.values():
            start, end = span.pop("start", None), span.pop("end", None)
            span["duration_s"] = (end["monotonic_ns"] - start["monotonic_ns"]) / 1e9 if start and end and start["clock_instance_id"] == end["clock_instance_id"] else None
            span["at"] = start["at"] if start else None
            if start and not end and start["clock_instance_id"] == _CLOCK:
                span["status"] = "running"
        root = spans.get(manifest["root_span_id"], {})
        manifest["metadata"] = metadata(manifest.get("metadata", {}))
        paths=self._event_paths(directory)
        indices={int(match[1]) if (match:=_CHUNK.fullmatch(p.name)) else 0 for p in paths}
        missing_chunks=len(set(range(max(indices)+1))-indices) if indices else 0
        health={key:max(value,historical_health.get(key,0)) for key,value in self.health.items()}
        health.update(malformed_events=malformed_events,missing_chunks=missing_chunks,duplicate_events=duplicate_events)
        health['diagnostics_degraded']=bool(health['diagnostics_degraded'] or malformed_events or missing_chunks or duplicate_events)
        return {"manifest": manifest, "status": root.get("status", "unknown"),
                "duration_s": root.get("duration_s"), "spans": list(spans.values()),
                "events": events, "event_count":event_count, "events_truncated":event_count>len(events),
                "first_error":first_error,
                "health": health,
                "raw_included": False, "physical_authority": False}

    def _link_directory(self):
        self._directory('0'*32)  # Same project root/link checks as execution files.
        directory=self.root/'links'
        if directory.is_symlink() or (hasattr(directory,'is_junction') and directory.is_junction()):
            raise ValueError('diagnostic links are linked')
        return directory

    def _binding_key(self, request_id, input_revision, source_revision):
        if (type(request_id) is not str or not _SAFE.fullmatch(request_id) or
                type(input_revision) is not str or not _DIGEST.fullmatch(input_revision) or
                type(source_revision) is not str or not _DIGEST.fullmatch(source_revision)):
            raise ValueError('invalid diagnostic binding identity')
        identity={'project_id':self.project_id,'request_id':request_id,
                  'input_revision':input_revision,'source_scene_revision':source_revision}
        digest=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return digest,identity

    def remember_binding(self, execution_id, *, request_id, input_revision, source_revision):
        """Optional immutable sidecar, never a source record or control permission."""
        try:
            digest,identity=self._binding_key(request_id,input_revision,source_revision)
            detail=self.detail(execution_id)
            refs=metadata({**detail['manifest']['metadata'],**identity,
                           'evidence_kind':'generation_execution','evidence_id':execution_id})
            value={'schema_version':'1.0','identity':identity,'metadata':refs}
            data=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
            if len(data)>8192:raise ValueError('diagnostic binding exceeds limit')
            with self._write_guard():
                directory=self._link_directory();directory.mkdir(parents=True,exist_ok=True)
                path=directory/(digest+'.json')
                if path.exists():
                    if self.restore_binding(**dict(request_id=request_id,input_revision=input_revision,source_revision=source_revision)) != refs:
                        raise ValueError('diagnostic binding conflict')
                    return True
                if len(list(islice(directory.iterdir(),4096)))>=4096:raise ValueError('diagnostic binding count exceeds limit')
                self._budget('0'*32,len(data))
                with path.open('xb') as stream:
                    stream.write(data);stream.flush();os.fsync(stream.fileno())
            return True
        except (OSError,ValueError,TypeError,KeyError):
            with self._lock:self._failures+=1
            return False

    def restore_binding(self, *, request_id, input_revision, source_revision):
        try:
            digest,identity=self._binding_key(request_id,input_revision,source_revision)
            path=self._link_directory()/(digest+'.json')
            if not path.exists():return {}
            if path.is_symlink() or path.stat().st_nlink!=1 or path.stat().st_size>8192:
                raise ValueError('diagnostic binding is linked or oversized')
            value=json.loads(path.read_text(encoding='utf-8'))
            if (type(value) is not dict or set(value)!={'schema_version','identity','metadata'} or
                    value['schema_version']!='1.0' or value['identity']!=identity or type(value['metadata']) is not dict or
                    metadata(value['metadata'])!=value['metadata']):
                raise ValueError('invalid diagnostic binding')
            refs=value['metadata'];execution=refs.get('evidence_id')
            if type(execution) is not str or not _ID.fullmatch(execution):raise ValueError('invalid diagnostic binding evidence')
            detail=self.detail(execution)
            merged={**detail['manifest']['metadata']}
            for span in detail['spans']:merged.update(span['metadata'])
            if (detail['manifest']['stage']!='scene_generation' or merged.get('request_id')!=request_id or
                    merged.get('input_revision')!=input_revision or merged.get('draft_revision')!=source_revision or
                    any(refs.get(key)!=item for key,item in identity.items()) or
                    refs.get('evidence_kind')!='generation_execution' or
                    any(refs.get(key)!=item for key,item in detail['manifest']['metadata'].items())):
                raise ValueError('diagnostic binding evidence mismatch')
            return refs
        except (OSError,ValueError,TypeError,KeyError):
            with self._lock:self._failures+=1
            return {}

    def _edit_binding_key(self, *, request_id, input_revision, source_revision,
                          operation_id, history_digest, result_revision):
        _, identity = self._binding_key(request_id, input_revision, source_revision)
        if (type(operation_id) is not str or not _SAFE.fullmatch(operation_id) or
                type(history_digest) is not str or not _DIGEST.fullmatch(history_digest) or
                type(result_revision) is not str or not _DIGEST.fullmatch(result_revision)):
            raise ValueError('invalid diagnostic edit binding identity')
        identity.update(evidence_kind='scene_edit_execution', operation_id=operation_id,
                        scene_change_sha256=history_digest, scene_edit_revision=result_revision)
        digest=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return digest, identity

    def _edit_binding_refs(self, execution_id, identity):
        detail=self.detail(execution_id)
        root=next((span for span in detail['spans']
                   if span['span_id']==detail['manifest']['root_span_id']), {})
        refs={**detail['manifest']['metadata'], **root.get('metadata', {})}
        if (detail['manifest']['stage'] not in {'scene_edit_apply','scene_edit_undo'} or
                any(refs.get(key)!=value for key,value in identity.items()
                    if key not in {'evidence_kind','project_id'}) or
                not any(span.get('stage')=='scene_edit_validate_and_save' and
                        span.get('status')=='succeeded' for span in detail['spans'])):
            raise ValueError('diagnostic edit binding evidence mismatch')
        # A committed edit can have a failed review-registration/root outcome.
        # This reference records that fact; it never grants review or movement.
        return {'scene_edit_execution_id':execution_id,
                  'scene_edit_revision':identity['scene_edit_revision'],
                  'scene_change_sha256':identity['scene_change_sha256'],
                  **{key:refs[key] for key in ('feedback_execution_id','feedback_operation_id','feedback_request_id',
                      'feedback_approval_id','feedback_response_sha256','feedback_context_sha256','feedback_preview_execution_id',
                      'sensor_execution_id','sensor_map_id','sensor_binding_sha256','sensor_raw_sha256',
                      'sensor_evidence_sha256','sensor_alignment_sha256') if key in refs}}

    def remember_edit_binding(self, execution_id, **selectors):
        """Exact committed-history sidecar; independent of generation bindings."""
        try:
            digest,identity=self._edit_binding_key(**selectors)
            refs=self._edit_binding_refs(execution_id,identity)
            data=json.dumps({'schema_version':'1.0','identity':identity,'metadata':refs},
                            sort_keys=True,separators=(',',':')).encode()
            if len(data)>8192:raise ValueError('diagnostic edit binding exceeds limit')
            with self._write_guard():
                directory=self._link_directory();directory.mkdir(parents=True,exist_ok=True)
                path=directory/(digest+'.json')
                if path.exists():
                    if self.restore_edit_binding(**selectors)!=refs:
                        raise ValueError('diagnostic edit binding conflict')
                    return True
                if len(list(islice(directory.iterdir(),4096)))>=4096:
                    raise ValueError('diagnostic binding count exceeds limit')
                self._budget('0'*32,len(data))
                with path.open('xb') as stream:
                    stream.write(data);stream.flush();os.fsync(stream.fileno())
            return True
        except (OSError,ValueError,TypeError,KeyError):
            with self._lock:self._failures+=1
            return False

    def restore_edit_binding(self, **selectors):
        try:
            digest,identity=self._edit_binding_key(**selectors)
            path=self._link_directory()/(digest+'.json')
            if not path.exists():return {}
            if path.is_symlink() or path.stat().st_nlink!=1 or path.stat().st_size>8192:
                raise ValueError('diagnostic edit binding is linked or oversized')
            value=json.loads(path.read_text(encoding='utf-8'))
            if (type(value) is not dict or set(value)!={'schema_version','identity','metadata'} or
                    value['schema_version']!='1.0' or value['identity']!=identity or
                    type(value['metadata']) is not dict or
                    metadata(value['metadata'])!=value['metadata']):
                raise ValueError('invalid diagnostic edit binding')
            execution=value['metadata'].get('scene_edit_execution_id')
            if type(execution) is not str or not _ID.fullmatch(execution):
                raise ValueError('invalid diagnostic edit evidence')
            refs=self._edit_binding_refs(execution,identity)
            if value['metadata']!=refs:raise ValueError('diagnostic edit binding evidence mismatch')
            return refs
        except (OSError,ValueError,TypeError,KeyError):
            with self._lock:self._failures+=1
            return {}

    def list(self, limit=50, *, query='', status='', cursor=None):
        """Read-only bounded pages, ordered by immutable manifest write time + ID.

        Cursors select positions, never paths or access rights. New executions
        above the first-page watermark require an explicit first-page refresh.
        Status/evidence of an already running execution may still change.
        """
        import base64
        import binascii
        import heapq
        if (type(limit) is not int or not 1 <= limit <= 100 or
                type(query) is not str or not re.fullmatch(r'[A-Za-z0-9_.:/ -]{0,160}', query) or
                type(status) is not str or status not in _STATUSES | {''}):
            raise DiagnosticQueryError('invalid diagnostic list query')
        query=query.strip()
        watermark=before=None
        if cursor is not None:
            try:
                if type(cursor) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,1024}',cursor):
                    raise ValueError('invalid cursor')
                value=json.loads(base64.b64decode(cursor+'='*(-len(cursor)%4),altchars=b'-_',validate=True))
                def checked_position(position):
                    return (type(position) is list and len(position)==2 and type(position[0]) is int and
                            0 <= position[0] < 2**63 and type(position[1]) is str and _ID.fullmatch(position[1]))
                if (type(value) is not dict or set(value)!={'version','project_id','query','status','watermark','before'} or
                        type(value['version']) is not int or value['version']!=1 or value['project_id']!=self.project_id or
                        value['query']!=query or value['status']!=status or
                        not checked_position(value['watermark']) or not checked_position(value['before']) or
                        tuple(value['before'])>tuple(value['watermark'])):
                    raise ValueError('invalid cursor scope')
                watermark,before=tuple(value['watermark']),tuple(value['before'])
            except (ValueError,TypeError,KeyError,binascii.Error):
                raise DiagnosticQueryError('invalid diagnostic list cursor') from None
        unavailable=scanned=0
        health=dict(self.health)
        results=[]
        next_cursor=None
        if self.root.exists():
            self._directory('0'*32)
            def entries_with_time():
                nonlocal unavailable
                for path in self.root.iterdir():
                    if not _ID.fullmatch(path.name):continue
                    try:
                        checked=self._directory(path.name)/'manifest.json'
                        if checked.is_symlink() or checked.stat().st_nlink!=1:
                            raise ValueError('linked diagnostic manifest')
                        key=(checked.stat().st_mtime_ns,path.name)
                        if (watermark is None or key<=watermark) and (before is None or key<before):
                            yield key
                    except (OSError,ValueError):unavailable+=1
            # Scan at most 100 execution bodies, with 101 keys to detect more.
            entries=heapq.nlargest(101,entries_with_time())
            if entries and watermark is None:watermark=entries[0]
            last=None
            for key in entries[:100]:
                scanned+=1;last=key
                try:
                    value=self.detail(key[1]);root=value['manifest']
                    for field in ('storage_errors','dropped_events','malformed_events','missing_chunks','duplicate_events'):
                        health[field]=max(health.get(field,0),value['health'].get(field,0))
                    health['diagnostics_degraded'] |= value['health']['diagnostics_degraded']
                    searchable=[key[1],root['stage'],value['status'],root['at'],*root['metadata'].values(),
                                *(value['first_error'] or {}).values()]
                    for span in value['spans']:searchable.extend(span['metadata'].values())
                    if (not status or value['status']==status) and (not query or any(
                            query.casefold() in str(item).casefold() for item in searchable)):
                        results.append({'execution_id':key[1],'at':root['at'],'stage':root['stage'],
                            'status':value['status'],'duration_s':value['duration_s'],
                            'metadata':root['metadata'],'first_error':value['first_error']})
                except (OSError,ValueError,KeyError):unavailable+=1
                if len(results)>=limit:break
            if last is not None and len(entries)>scanned:
                payload=dict(version=1,project_id=self.project_id,query=query,status=status,
                             watermark=watermark,before=last)
                next_cursor=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('=')
        health.update(unavailable_executions=unavailable)
        health['diagnostics_degraded'] |= bool(unavailable)
        return {'executions':results,'health':health,'next_cursor':next_cursor,'has_more':next_cursor is not None,
                'scanned_count':scanned,'page_size':limit,'order_basis':'manifest_write_time_then_id',
                'project_id':self.project_id}

    def graph(self, identity):
        """One-hop recorded references only; never infer causality from shared IDs.

        Reverse lookup is explicitly incomplete beyond the newest 100 of at
        most 4096 directory entries, 8 MiB total and 1 MiB per event body.
        Files remain project-scoped, link-checked and unmodified. Missing and
        foreign-project references have the same unavailable representation.
        """
        import heapq
        _, selected_manifest = self._manifest(identity)  # Unknown selection is 404.
        byte_budget = 8 * 1024 * 1024 - 8193  # Initial selection validation.
        nodes, edges, cache = {}, set(), {}
        partial = False
        checked = unavailable = 0

        def read_record(record_id):
            nonlocal byte_budget, partial, checked, unavailable
            if record_id in cache:
                return cache[record_id]
            checked += 1
            if byte_budget < 16386:
                partial = True
                cache[record_id] = dict(execution_id=record_id, available=False,
                                       stage=None, status='unknown', at=None), []
                return cache[record_id]
            byte_budget -= 16386  # Both manifest reads, including oversized sentinel.
            try:
                directory, manifest = self._manifest(record_id)
                # Reserve the bounded reader's allowance, not just a racy stat.
                size = sum(path.stat().st_size for path in self._event_paths(directory))
                allowance = size + 8192
                value = None
                if allowance <= 1024 * 1024 and allowance + 8193 <= byte_budget:
                    byte_budget -= allowance + 8193  # One bounded over-budget line.
                    value = self.detail(record_id, read_limit=allowance)
                    partial |= bool(value['events_truncated'] or value['health']['diagnostics_degraded'])
                else:
                    partial = True
                refs = [manifest['metadata']]
                if value is not None:
                    refs.extend(span['metadata'] for span in value['spans'])
                    refs.extend(event['metadata'] for event in value['events'])
                record = dict(execution_id=record_id, available=True, stage=manifest['stage'],
                              status=value['status'] if value else 'unknown', at=manifest['at'])
                cache[record_id] = record, refs
            except (OSError, ValueError, KeyError):
                partial = True
                unavailable += 1
                cache[record_id] = dict(execution_id=record_id, available=False,
                                       stage=None, status='unknown', at=None), []
            return cache[record_id]

        def references(refs):
            for values in refs:
                fields = ['launch_execution_id', 'scene_edit_execution_id', 'command_execution_id', 'retry_of',
                          'feedback_execution_id','feedback_preview_execution_id','sensor_execution_id']
                if values.get('evidence_kind') == 'generation_execution':
                    fields.append('evidence_id')
                for field in fields:
                    target = values.get(field)
                    if type(target) is str and _ID.fullmatch(target):
                        yield target, field

        def add_edge(source, target, relation):
            nonlocal partial
            if source == target:
                return
            if len(edges) >= 128 or len(set(nodes) | {source, target}) > 32:
                partial = True
                return
            for record_id in (source, target):
                if record_id not in nodes:
                    nodes[record_id] = read_record(record_id)[0]
            edges.add((source, target, relation))

        nodes[identity], refs = read_record(identity)
        # A concurrently damaged selection must never look like a valid graph.
        if not nodes[identity]['available']:
            raise ValueError('selected diagnostic unavailable')
        for target, relation in references(refs):
            add_edge(identity, target, relation)

        def entries():
            nonlocal partial, unavailable
            for index, path in enumerate(self.root.iterdir()):
                if index >= 4096:
                    partial = True
                    break
                if not _ID.fullmatch(path.name):
                    continue
                try:
                    directory = self._directory(path.name)
                    manifest_path = directory / 'manifest.json'
                    if manifest_path.is_symlink() or manifest_path.stat().st_nlink != 1:
                        raise ValueError('linked diagnostic manifest')
                    yield manifest_path.stat().st_mtime_ns, path.name
                except (OSError, ValueError):
                    partial = True
                    unavailable += 1

        candidates = heapq.nlargest(101, entries())
        partial |= len(candidates) > 100
        reverse_scanned = 0
        for _, record_id in candidates[:100]:
            if byte_budget < 16386:
                partial = True
                break
            reverse_scanned += 1
            _, refs = read_record(record_id)
            for target, relation in references(refs):
                if target == identity:
                    add_edge(record_id, identity, relation)
        return dict(schema_version='1.0', project_id=selected_manifest['project_id'],
                    execution_id=identity, scope='recorded_one_hop_references',
                    nodes=list(nodes.values()),
                    edges=[dict(source=source, target=target, relation=relation)
                           for source, target, relation in sorted(edges)],
                    partial=partial, checked_count=checked, reverse_scanned_count=reverse_scanned,
                    unavailable_count=unavailable,
                    limits=dict(nodes=32, edges=128, reverse_records=100, directory_entries=4096,
                                total_read_bytes=8*1024*1024, record_read_bytes=1024*1024),
                    raw_included=False, physical_authority=False)

    def export(self, identity):
        value = self.detail(identity)
        value["export_scope"] = "redacted_metadata_only"
        payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        return {"diagnostics": value, "export_sha256": hashlib.sha256(payload).hexdigest()}


def profile_call(trace, stage, function, *args, enabled=False, timer_basis='thread_cpu', **kwargs):
    """Explicit profiling of one bounded PURE call; no replay, network or motors.

    Caller must constrain inputs with existing schema bounds. Only 30 stripped
    function rows are retained; arguments, locals, paths and pstats binaries are
    never exported. Thread CPU is deliberately not labelled as elapsed time.
    Owner-thread filtering prevents CPython 3.12's global monitoring callbacks
    from mixing thread clocks. Profiling is optional and never waits for another
    profiler or replays work. Instrumented time is not an unprofiled benchmark.
    """
    if timer_basis not in {'wall', 'thread_cpu'}:
        raise ValueError('unsupported profiling timer')
    with trace.span(stage, timer_basis=timer_basis if enabled else 'wall') as child:
        if not enabled:
            return function(*args, **kwargs)
        import cProfile
        import pstats
        import sys
        timer = time.thread_time_ns if timer_basis == 'thread_cpu' else time.perf_counter_ns
        started = timer()
        kind = 'thread_filtered_cprofile'
        # CPython 3.12 cProfile installs interpreter-wide monitoring callbacks.
        # Feeding those callbacks thread_time mixes unrelated thread clocks and
        # corrupts its stack/totals. Filter BEFORE entering its C stack/timer.
        # Never replace an existing diagnostic tool or retry the product call.
        if sys.getprofile() is not None:
            child.bind(profiler_kind=kind, profile_status='SKIPPED', profile_valid=False,
                       error_code='PROFILE_OTHER_TOOL_ACTIVE')
            return function(*args, **kwargs)
        if not _PROFILE_GUARD.acquire(blocking=False):
            child.bind(profiler_kind=kind, profile_status='SKIPPED', profile_valid=False,
                       error_code='PROFILE_TOOL_BUSY')
            return function(*args, **kwargs)
        profiler = None
        try:
            callbacks = ('_pystart_callback', '_pyreturn_callback', '_ccall_callback', '_creturn_callback')
            if hasattr(sys, 'monitoring'):
                if not all(hasattr(cProfile.Profile, name) for name in callbacks):
                    raise ValueError('unsupported monitoring callbacks')
                owner = get_ident()
                # The stdlib C profiler registers these via getattr(self, name).
                # Its global stack receives ONLY the original calling thread.
                methods = {}
                for name in callbacks:
                    original = getattr(cProfile.Profile, name)
                    def filtered(self, *values, _original=original):
                        if get_ident() == owner:
                            return _original(self, *values)
                    methods[name] = filtered
                factory = type('OwnerThreadProfile', (cProfile.Profile,), methods)
            else:
                factory = cProfile.Profile  # Pre-monitoring runtimes are thread-local.
            profiler = factory(timer=timer, timeunit=1e-9)
            profiler.enable()
        except Exception:
            _PROFILE_GUARD.release()
            child.bind(profiler_kind=kind, profile_status='FAILED', profile_valid=False,
                       error_code='PROFILE_SETUP_FAILED')
            return function(*args, **kwargs)
        try:
            return function(*args, **kwargs)
        finally:
            try:
                profiler.disable()
                elapsed = (timer() - started) / 1e9
                # Validate every row before truncation; an invalid low-ranked
                # function must not make a plausible top-30 appear trustworthy.
                stats = pstats.Stats(profiler).stats
                valid = math.isfinite(elapsed) and elapsed >= 0
                valid &= all(math.isfinite(v[2]) and math.isfinite(v[3])
                    and 0 <= v[2] <= v[3] + 1e-6 and v[3] <= elapsed + 1e-6
                    for v in stats.values())
                rows = sorted(stats.items(),
                              key=lambda r: r[1][3], reverse=True)[:30]
                child.bind(profiler_kind=kind, profiled_elapsed_s=elapsed,
                    profile_status='VALID' if valid else 'INVALID', profile_valid=valid,
                    profile_row_count=len(stats),
                    error_code=None if valid else 'PROFILE_TIMING_INVALID')
                for (filename, line, name), (primitive, calls, self_time, cumulative, callers) in rows:
                    source = re.sub(r'[^A-Za-z0-9_.-]', '_', Path(filename).name)[:100]
                    function_name = re.sub(r'[^A-Za-z0-9_.-]', '_', name)[:100]
                    child.store.emit(child, 'profile_row', dict(source_file=source, function=function_name,
                        source_line=line, calls=calls, self_s=self_time, cumulative_s=cumulative, timer_basis=timer_basis,
                        profiler_kind=kind, profile_id=child.span_id, profile_valid=valid))
            except Exception:
                child.bind(profiler_kind=kind, profiled_elapsed_s=(timer() - started) / 1e9,
                           profile_status='FAILED', profile_valid=False, error_code='PROFILE_STATS_FAILED')
            finally:
                _PROFILE_GUARD.release()
