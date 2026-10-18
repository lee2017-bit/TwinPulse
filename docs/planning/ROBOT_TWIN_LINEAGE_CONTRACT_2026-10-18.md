# Robot / conversation / Twin lineage — 2026-10-18

## Scope and ownership

Main owns all code, UI, tests, packaging and documentation. Astra xhigh is a read-only design reviewer; it performs no hardware, external inference, UI or file edits. Physical robot remains OFF: no SSH, sensor or motor invocation in this change's acceptance.

IDs are distinct: project_id + conversation_session_id → scene_revision / engine_session_id / stage_epoch → operation_id + robot_id + connection_epoch → request_id / trial_id / stream_id / frame_sequence / raw SHA. Authentication owner/session tokens are never conversation IDs or logged provenance.

## Immutable reference, not invented time synchronization

The physical operation captures a validated, content-hashed `robot-twin-context-1.0` at explicit connection. It is an immutable **operation-start Twin reference**, not proof that a later sensor acquisition or source-file export occurred against the currently displayed revision. No scene at connection is explicit `NO_CURRENT_TWIN`; missing historical linkage is `LEGACY_UNKNOWN`, never backfilled from today's Twin. A physical raw sensor frame remains native / unaligned. An operator marker is an estimate, never calibrated localization.

Every new physical transport command and robot event joins the operation reference ID. User commands also capture a separate request-time Twin context before deferred execution, never on late response. Trial context includes the actual trial command's reference. The worker's source hash / robot boot / deployment release are separate from scene_revision. Start context and both reference/command IDs are preserved in raw evidence and exports.

Changing the Twin, Undo, restarting the engine, or switching project cannot rewrite the operation reference or old command/scan records. UI displays a different/current/unavailable reference explicitly. To make a new Twin the source of a physical collection, explicitly Disconnect and Check Connection to create a new operation. This change adds no motor safety restriction and does not restart sensors automatically. SIM observations record their actual accepted engine binding on each event; a final manifest's latest binding is not substituted for historical events.

## API and storage

`source_twin_context` is an immutable object containing schema, context_id (canonical SHA256), project_id, conversation_session_id (nullable only if unavailable), scene_revision, engine_session_id, stage_epoch, association basis, and coordinate/alignment provenance. `request_twin_context` is a separate immutable snapshot on user commands. UI clients cannot supply either; the authenticated backend derives them. Conversation identity is copied after restore at App construction without acquiring the conversation lock inside fleet/worker locks.

Physical start/command/event protocol v2 requires a matching source context ID. Legacy on-disk records remain readable with explicit unknown provenance; no live v2 packet may omit or change the immutable reference. Source contexts are validated and cross-project context substitution rejected. Stop/Close keep priority and do not depend on a current scene or metadata disk write.

## Acceptance

Supplementary: canonical hash / tamper / missing scene / legacy; deferred command context freeze; cross-project and changed source rejection; scan/raw/source/trial joins; old packet compatibility and cold history; scene change/Undo/engine reset preserve old provenance; no authority restored. Actual installed Electron + Isaac: operation creation, finite commands, scans, logs/download, scene change/Undo, saved reopen and IDs. Reusing a saved Twin is allowed for this traceability test and is not a fresh generation/model-quality result. Physical acquisition is NOT_RUN while OFF. All failures and attempt IDs preserved in one report.

## User-flow findings incorporated before final freeze

Explicit MB-sized operation history reads have a separate bounded20s deadline; live fleet/viewport/state reads remain3s. Final decoded frames and all freshness guards are unchanged. ID details use a scoped display override so the chat-wide definition-list grid cannot collapse long IDs into one-character columns.

After a successful engine project-rebind ACK, the retired SIM fleet drains asynchronously with `PROJECT_SWITCH` as its end reason. Bridge ACK stays `switched/failed` within its existing protocol; duplicate ACKs reuse the completed result. Before constructing a new writer for the same project, admission waits outside workspace/robot locks up to3s for retirement completion **and actual snapshot/recorder thread termination**. A close timeout is not permission to overlap writers. The shared physical pool is not closed. Concurrent/faulted fleet closes always signal completion and do not start a new watchdog after shutdown begins.

An observed conversation503 left a flushed temporary file; the old code hid the OSError numbers. Windows error5/32/33 may retry only the same flushed atomic rename (up to5 attempts, total backoff150ms, not a wall-clock bound including filesystem calls). Other errors fail immediately and retain the original/temp and safe numeric error metadata. This is not a provider/robot/action retry, nor proof of the old error's exact cause. Fixed temp-file multi-writer ambiguity is also reduced by the project retirement fence; historical failures remain preserved.

The candidate04 90-degree SIM motion timed out at approximately85.94degrees. A separate final short10-degree traceability check does not turn that90-degree failure into PASS. Low-FPS integration/deadline behavior is a remaining independent issue; no speed, deadline or safety criterion is relaxed here.
