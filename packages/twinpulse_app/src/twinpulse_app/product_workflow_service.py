# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Product-facing adapter over the UI-independent ApplicationService."""

from __future__ import annotations

import asyncio
import base64
import binascii
from dataclasses import dataclass, replace
from copy import deepcopy
import hashlib
import json
import math
from pathlib import PurePath
import re
import shutil
from threading import RLock, Thread, current_thread
from typing import TYPE_CHECKING, Callable, Mapping
from uuid import uuid4

from twinpulse_core import COMPACT_2WD_PROFILE_ID, GeneratedDraftRecord, canonical_sha256
from twinpulse_provider import (
    GenerationCancelledError,
    ImageInput,
    InvalidProviderResponseError,
    MeasurementConstraint,
    MeasurementConstraintError,
    ProviderAuthenticationError,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    parse_measurement_constraints,
)

from .application import ApplicationService, GenerationContext, GenerationGateway, PreparedInput
from .command_broker import BrokerError, CommandBroker, RegisteredArtifact, RegisteredSiteScene
from .site_draft import SiteDraftRecord
from .scene_changes import SceneChangeHistory, SceneChangeStore
from .dependency_patch import public_progressive
from .scene_edit_proposals import (checked_furniture_proposal, furniture_edit_context,
    feedback_edit_context,checked_feedback_proposal)
from twinpulse_core.presentation import DEFAULT_PRESENTATION, checked_presentation
from .image_validation import ImageValidationError, decode_image


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_SIDECAR_BYTES = 128 * 1024
INPUT_KINDS = frozenset({"auto", "photo", "drawing"})
WORKFLOW_MODES = frozenset({"live_provider", "explicit_fixture", "replay", "simulation_offline"})

if TYPE_CHECKING:
    from .replay import ReplayFixture


@dataclass(frozen=True, slots=True)
class ProductInput:
    revision: str
    prompt: str
    input_kind: str
    image_name: str | None
    media_type: str | None
    image_bytes: bytes | None
    image_sha256: str | None
    width: int | None
    height: int | None
    image_dimensions_px: tuple[int, int] | None
    sidecar_name: str | None
    sidecar_sha256: str | None
    measurement_constraints: tuple[MeasurementConstraint, ...]
    measurement_count: int
    prepared: PreparedInput


class ProductWorkflow:
    """Presentation and acknowledgement state; generation stays in ApplicationService."""

    @property
    def conversation_path(self):
        self._application._project_store._check_location()
        return self._application._project_store.path.with_suffix(".conversation.json")

    def robot_report_snapshot(self):
        return self._application.robot_reports.snapshot()

    def import_robot_report(self, report):
        return self._application.robot_reports.import_report(report)

    @property
    def scan_review(self):
        return self._application.scan_review

    @property
    def native_scan_review(self):
        return self._application.native_scan_review

    def __init__(
        self,
        application: ApplicationService,
        broker: CommandBroker,
        *,
        mode: str = "live_provider",
        generation_settings_getter: Callable[[], Mapping[str, str]],
        provider_state_getter: Callable[[], Mapping[str, object]] | None = None,
        gateway_factory: Callable[[], GenerationGateway] | None = None,
        profile_id: str = COMPACT_2WD_PROFILE_ID,
    ) -> None:
        if mode not in WORKFLOW_MODES:
            raise ValueError("workflow mode is unsupported")
        self._application = application
        self._broker = broker
        broker.diagnostics = application.diagnostics
        self._mode = mode
        self._generation_settings_getter = generation_settings_getter
        self._provider_state_getter = provider_state_getter or (lambda: {})
        # Display-only observation, not authentication or generation identity.
        # Never read credential/configuration files in the hot snapshot lock.
        self._provider_refresh_serial = 0
        self._provider_observation_error = None
        try:
            self._provider_state = dict(self._provider_state_getter())
            self._provider_configuration_state = 'observed'
        except Exception as error:
            self._provider_state = {'configured':False,'label':'Provider state unavailable'}
            self._provider_configuration_state = 'unconfirmed'
            self._provider_observation_error = error
        self._gateway_factory = gateway_factory
        self.render_review_port_factory = None
        from .model_recipe_store import ModelRecipeStore
        folder=application._project_store.path.parent
        state_root=folder.parent.parent if folder.parent.name=='projects' else folder
        self.model_recipe_store=ModelRecipeStore(state_root)
        # Explicit fixture injection only; live services come from approved
        # ordinary stage settings and the same audited planner transport.
        self.scene_edit_proposal_service = None
        self.scene_sensor_review = None
        self._profile_id = profile_id
        self._lock = RLock()
        self._input: ProductInput | None = None
        self._phase = "restore_review_required" if (
            application.record is not None or application.site_draft is not None or application.restore_error is not None
        ) else "empty"
        self._generation_id: str | None = None
        self._acknowledged_identity: tuple[str, str] | None = None
        self._artifact: RegisteredArtifact | None = None
        self._site_artifact: RegisteredSiteScene | None = None
        self._derived_revision: str | None = None
        self._scene_changes: SceneChangeHistory | None = None
        self._site_summary_cache = None
        if application.restore_error is not None:
            code, message = application.restore_error
            self._error: dict[str, str] | None = {"code": code, "message": message}
        elif application.record is not None or application.site_draft is not None:
            self._error = {"code": "restore_review_required", "message": "Stored draft requires current input review"}
        else:
            self._error = None
        self._connected = False
        self._workers: set[Thread] = set()
        from .scene_edit_transaction import SceneEditTransaction
        self.scene_edit_transaction=SceneEditTransaction(self)
        broker.scene_mutation_guard=self.scene_edit_transaction.guard

    def select_input(self, value: Mapping[str, object]) -> dict[str, object]:
        expected = {
            "name", "input_kind", "prompt", "media_type", "content_base64",
            "sidecar_name", "sidecar_content_base64",
        }
        if set(value) != expected:
            raise BrokerError("input_shape_invalid", "Input request shape is invalid", status=400)
        prompt = value.get("prompt")
        input_kind = value.get("input_kind")
        if not isinstance(prompt, str) or len(prompt) > 8_000:
            raise BrokerError("prompt_invalid", "Prompt is invalid", status=400)
        if input_kind not in INPUT_KINDS:
            raise BrokerError("input_kind_invalid", "Input kind is unsupported", status=400)
        name = value.get("name")
        media_type = value.get("media_type")
        encoded = value.get("content_base64")
        image_bytes: bytes | None = None
        sidecar_bytes: bytes | None = None
        measurements: tuple[MeasurementConstraint, ...] = ()
        width = height = None
        image_sha256: str | None = None
        if encoded is None:
            if name is not None or media_type is not None:
                raise BrokerError("image_fields_invalid", "Image fields must be supplied together", status=400)
        else:
            if not isinstance(name, str) or not _safe_name(name):
                raise BrokerError("image_name_invalid", "Image name is invalid", status=400)
            if media_type not in {"image/png", "image/jpeg", "image/webp"}:
                raise BrokerError("image_media_type_invalid", "Image media type is unsupported", status=415)
            if not isinstance(encoded, str) or len(encoded) > MAX_IMAGE_BYTES * 2:
                raise BrokerError("image_payload_invalid", "Image payload is invalid", status=413)
            try:
                image_bytes = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as error:
                raise BrokerError("image_base64_invalid", "Image encoding is invalid", status=400) from error
            if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
                raise BrokerError("image_size_invalid", "Image exceeds the 10 MiB limit", status=413)
            try:
                decoded = decode_image(image_bytes, max_pixels=MAX_IMAGE_PIXELS)
            except ImageValidationError as error:
                status = 413 if error.code == "image_dimensions_invalid" else 400
                raise BrokerError(error.code, str(error), status=status) from error
            width, height = decoded.width, decoded.height
            if decoded.media_type != media_type:
                raise BrokerError("image_type_mismatch", "Image content does not match its media type", status=400)
            image_sha256 = hashlib.sha256(image_bytes).hexdigest()
        sidecar_name = value.get("sidecar_name")
        sidecar_encoded = value.get("sidecar_content_base64")
        if sidecar_encoded is None:
            if sidecar_name is not None:
                raise BrokerError("sidecar_fields_invalid", "Sidecar fields must be supplied together", status=400)
        else:
            if image_bytes is None:
                raise BrokerError("sidecar_image_required", "A measurement sidecar requires an image", status=400)
            if not isinstance(sidecar_name, str) or not _safe_name(sidecar_name) or not sidecar_name.endswith(".json"):
                raise BrokerError("sidecar_name_invalid", "Sidecar name is invalid", status=400)
            if not isinstance(sidecar_encoded, str) or len(sidecar_encoded) > MAX_SIDECAR_BYTES * 2:
                raise BrokerError("sidecar_payload_invalid", "Sidecar payload is invalid", status=413)
            try:
                sidecar_bytes = base64.b64decode(sidecar_encoded, validate=True)
                if not sidecar_bytes or len(sidecar_bytes) > MAX_SIDECAR_BYTES:
                    raise ValueError("sidecar size")
                payload = json.loads(sidecar_bytes.decode("utf-8"))
                measurements = parse_measurement_constraints(
                    payload,
                    image_name=str(name),
                    image_sha256=image_sha256,
                    image_dimensions=(width, height) if width is not None and height is not None else None,
                )
            except (binascii.Error, UnicodeError, json.JSONDecodeError, ValueError, MeasurementConstraintError) as error:
                raise BrokerError("sidecar_invalid", f"Measurement sidecar is invalid: {error}", status=400) from error
        if not prompt.strip() and image_bytes is None:
            raise BrokerError("input_empty", "Attach a site image or describe the scene", status=400)

        sidecar_sha256 = hashlib.sha256(sidecar_bytes).hexdigest() if sidecar_bytes is not None else None
        images = () if image_bytes is None else (ImageInput(str(name), str(media_type), image_bytes),)
        resolved_kind = "drawing" if input_kind == "drawing" else ("photo" if images else "text")
        try:
            prepared = self._application.prepare_input(
                prompt=prompt,
                images=images,
                measurement_constraints=measurements,
                generation_settings=dict(self._generation_settings_getter()),
                input_kind=resolved_kind,
                profile_id=self._profile_id,
            )
            self._application.select_input(prepared)
        except OSError as error:
            self._error={'code':'input_persistence_failed',
                'message':'Input was not saved. Previous project data is unchanged; no generation started.'}
            raise BrokerError(self._error['code'],self._error['message'],status=503) from error
        except (TypeError, ValueError) as error:
            raise BrokerError("input_revision_invalid", str(error), status=400) from error

        selected = ProductInput(
            revision=prepared.revision.digest,
            prompt=prompt,
            input_kind=resolved_kind,
            image_name=name if isinstance(name, str) else None,
            media_type=media_type if isinstance(media_type, str) else None,
            image_bytes=image_bytes,
            image_sha256=image_sha256,
            width=width,
            height=height,
            image_dimensions_px=(width, height) if width is not None and height is not None else None,
            sidecar_name=sidecar_name if isinstance(sidecar_name, str) else None,
            sidecar_sha256=sidecar_sha256,
            measurement_constraints=measurements,
            measurement_count=len(measurements),
            prepared=prepared,
        )
        with self._lock:
            self._input = selected
            self._derived_revision = None
            self._scene_changes = None
            self._generation_id = None
            self._acknowledged_identity = None
            self._artifact = None
            self._site_artifact = None
            self._error = None
            self._connected = False
            record = self._application.record
            if record is not None and record.build_allowed_for(prepared.revision):
                self._artifact = self._register(record)
                self._phase = "draft_ready"
            elif (self._application.site_draft is not None and
                  self._application.site_draft.input_revision.digest == prepared.revision.digest):
                source = self._application.site_draft
                self._scene_changes = self._application.scene_change_store().load()
                self._site_artifact = (self._register_scene_change(source, self._scene_changes)
                                       if self._scene_changes.operations else self._register_site(source))
                self._phase = "draft_ready"
            else:
                self._phase = "input_ready"
            return self.snapshot()

    def continue_room_recipe(self) -> dict[str, object]:
        """Compatibility wrapper for the original room-only review action."""
        with self._lock:
            draft = self._application.site_draft
            if self._phase != "restore_review_required" or draft is None:
                raise BrokerError("room_recipe_restore_unavailable", "No saved room recipe needs review", status=409)
            if draft.provider_name != "local-room-recipe":
                raise BrokerError("room_recipe_restore_unavailable", "Saved draft is not a local room recipe", status=409)
            return self.resume_saved_scene(self._application.project_id, draft.site.scene.revision,
                                           draft.input_revision.digest)

    def resume_saved_scene(self, project_id: str, scene_revision: str,
                           input_revision: str) -> dict[str, object]:
        """Reopen original saved bytes for review, without provider/Build authority."""
        with self._lock:
            draft = self._application.site_draft or self._application.record
            if project_id != self._application.project_id or draft is None or draft.input_revision is None:
                raise BrokerError("saved_scene_unavailable", "No saved scene belongs to this project", status=409)
            actual_scene = (draft.site.scene.revision if isinstance(draft, SiteDraftRecord) else
                            draft.validation_receipt.bundle_sha256 if draft.validation_receipt is not None else draft.plan_sha256)
            if scene_revision != actual_scene or input_revision != draft.input_revision.digest:
                raise BrokerError("saved_scene_stale", "Saved scene revision changed", status=409)
            # Reopening a retained transaction is read-only: it restores review
            # data while the journal still blocks all geometry and Run commands.
            transaction_pending = self.scene_edit_transaction.locked()
            if self._phase == "generating" or self._workers or (self._broker.has_pending_operations() and not transaction_pending):
                raise BrokerError("generation_busy", "Active generation or scene command must finish before reopening a scene", status=409)
            try:
                prepared = self._application.restored_saved_input()
                image = prepared.images[0] if prepared.images else None
                decoded = decode_image(image.content, max_pixels=MAX_IMAGE_PIXELS) if image else None
                if image and decoded.media_type != image.mime_type:
                    raise ValueError("saved image MIME changed")
                if isinstance(draft, SiteDraftRecord):
                    edits = self._application.scene_change_store().load()
                    if edits.operations:
                        artifact = self._register_scene_change(draft, edits)
                    else:
                        artifact = self._register_site(draft)
                else:
                    artifact = self._register(draft)
                self._application.adopt_saved_review(prepared, actual_scene)
            except FileNotFoundError as error:
                raise BrokerError("saved_input_missing", "Original saved input is missing; reattach the identical source", status=409) from error
            except (OSError, UnicodeError, ValueError, ImageValidationError) as error:
                raise BrokerError("saved_scene_restore_invalid", "Saved input or scene failed validation", status=409) from error
            self._input = ProductInput(
                revision=prepared.revision.digest, prompt=prepared.revision.prompt,
                input_kind=prepared.revision.input_kind,
                image_name=image.name if image else None, media_type=image.mime_type if image else None,
                image_bytes=image.content if image else None,
                image_sha256=hashlib.sha256(image.content).hexdigest() if image else None,
                width=decoded.width if decoded else None, height=decoded.height if decoded else None,
                image_dimensions_px=(decoded.width, decoded.height) if decoded else None,
                sidecar_name=None, sidecar_sha256=None,
                measurement_constraints=prepared.measurement_constraints,
                measurement_count=len(prepared.measurement_constraints), prepared=prepared,
            )
            self._derived_revision = None
            self._scene_changes = edits if isinstance(draft, SiteDraftRecord) else None
            self._generation_id = None
            self._acknowledged_identity = None
            self._artifact = None
            self._artifact = artifact if isinstance(draft, GeneratedDraftRecord) else None
            self._site_artifact = artifact if isinstance(draft, SiteDraftRecord) else None
            self._error = None
            self._connected = False
            self._phase = "draft_ready"
            return self.snapshot()

    def reattach_saved_source(self, project_id: str, scene_revision: str, input_revision: str,
                              name: object, mime: object, encoded: object) -> dict[str, object]:
        with self._lock:
            draft = self._application.site_draft or self._application.record
            actual_scene = (draft.site.scene.revision if isinstance(draft, SiteDraftRecord) else
                            draft.validation_receipt.bundle_sha256 if draft is not None and draft.validation_receipt else
                            draft.plan_sha256 if draft is not None else None)
            if (project_id != self._application.project_id or draft is None or
                    draft.input_revision is None or scene_revision != actual_scene or
                    input_revision != draft.input_revision.digest or self._workers):
                raise BrokerError("saved_scene_stale", "Saved scene changed or is busy", status=409)
            content = None
            if encoded is not None:
                if (not isinstance(encoded, str) or len(encoded) > MAX_IMAGE_BYTES * 2 or
                        not isinstance(name, str) or not _safe_name(name) or
                        not isinstance(mime, str) or mime not in {"image/png", "image/jpeg", "image/webp"}):
                    raise BrokerError("image_payload_invalid", "Original image upload is invalid", status=400)
                try:
                    content = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError) as error:
                    raise BrokerError("image_base64_invalid", "Original image encoding is invalid", status=400) from error
                if not content or len(content) > MAX_IMAGE_BYTES:
                    raise BrokerError("image_size_invalid", "Original image exceeds the limit", status=413)
                try:
                    decoded = decode_image(content, max_pixels=MAX_IMAGE_PIXELS)
                except ImageValidationError as error:
                    raise BrokerError(error.code, "Original image is invalid", status=400) from error
                if decoded.media_type != mime:
                    raise BrokerError("image_type_mismatch", "Original image MIME changed", status=400)
            elif name is not None or mime is not None:
                raise BrokerError("image_fields_invalid", "Original image fields must match", status=400)
            try:
                self._application.reattach_saved_source(name, mime, content)
            except (OSError, UnicodeError, ValueError) as error:
                raise BrokerError("saved_source_mismatch", "Original bytes do not match the saved scene", status=409) from error
            return self.resume_saved_scene(project_id, scene_revision, input_revision)

    @property
    def current_input(self) -> ProductInput:
        with self._lock:
            if self._input is None:
                raise BrokerError("input_required", "Select the current input first")
            return self._input

    def start_generation(self, *, correlation=None, inference_scope=None, continuation_checkpoint=None, owner=None) -> dict[str, object]:
        with self._lock:
            if self._provider_configuration_state != 'observed':
                raise BrokerError('provider_configuration_unconfirmed',
                    'Provider settings are not applied. Save or refresh them before starting a new model request.',status=409)
            if self._mode == "replay":
                raise BrokerError("replay_generation_forbidden", "Stored replay cannot perform provider generation")
            if self._mode == "simulation_offline":
                raise BrokerError("generation_unavailable_offline", "Offline simulation cannot perform provider generation")
            if self._application.site_draft is not None:
                raise BrokerError(
                    "existing_scene_protected",
                    "A saved site scene cannot be replaced by a new full-scene generation. Create a new project; add/change modes require a reviewed change-set.",
                    status=409,
                )
            if self._input is None:
                raise BrokerError("input_required", "Select the current input before generation")
            if self._phase == "generating" or self._workers:
                raise BrokerError("generation_busy", "A generation job is already running")
            try:
                free=shutil.disk_usage(self._application._project_store.path.parent).free
            except OSError as error:
                raise BrokerError('local_storage_unavailable',
                    'Local project storage cannot be checked. Input is retained; no model request was sent.',status=503) from error
            if free < 256*1024*1024:
                raise BrokerError('local_storage_low',
                    'Less than 256 MiB is free for generation evidence and checkpoints. Free disk space first. '
                    'Input is retained; no model request was sent.',status=503)
            retry_of = self._application.last_execution_id if self._phase in {'generation_failed', 'cancelled'} else None
            self._phase = "generating"
            self._application.clear_derived_review()
            self._derived_revision = None
            self._scene_changes = None
            self._generation_id = str(uuid4())
            self._acknowledged_identity = None
            self._artifact = None
            self._site_artifact = None
            self._error = None
            generation_id = self._generation_id
            context = self._application.generation_context()
            trace = self._application.diagnostics.begin('scene_generation',
                **(correlation or {}), generation_id=generation_id, mode=self._mode,
                retry_of=retry_of,
                input_revision=context.prepared.revision.digest,
                input_kind='photo' if context.prepared.images else 'text')
            self._application.last_execution_id = trace.execution_id
            context = replace(context, diagnostics=trace, inference_scope=inference_scope,
                model_library_port=self.model_recipe_store,
                              continuation_checkpoint=continuation_checkpoint)
            if owner and self.render_review_port_factory:
                context = replace(context, render_review_port=self.render_review_port_factory(owner,
                    context.prepared.revision, lambda: self._generation_id == generation_id and self._phase == 'generating'))
            snapshot = self.snapshot()
        worker = Thread(
            target=self._complete_generation,
            args=(generation_id, context),
            name="TwinPulseGeneration",
            daemon=True,
        )
        with self._lock:
            self._workers.add(worker)
        worker.start()
        return snapshot

    def _complete_generation(self, generation_id: str, context: GenerationContext) -> None:
        try:
            try:
                outcome = asyncio.run(self._application.generate(context))
                artifact = self._register(outcome.record) if isinstance(outcome.record, GeneratedDraftRecord) else None
                site_artifact = self._register_site(outcome.record) if isinstance(outcome.record, SiteDraftRecord) else None
                registered = artifact or site_artifact
                if registered is not None:
                    self._broker.bind_artifact_diagnostics(registered.artifact_id,
                        generation_id=generation_id, evidence_kind='generation_execution',
                        evidence_id=context.diagnostics.execution_id)
            except Exception as error:
                context.diagnostics.finish('cancelled' if self._phase == 'cancelled' else 'failed', error=error)
                with self._lock:
                    if self._generation_id != generation_id or self._phase == "cancelled":
                        return
                    self._phase = "generation_failed"
                    self._error = _public_generation_error(error)
                    self._connected = False
                return
            with self._lock:
                if self._generation_id != generation_id or self._phase != "generating":
                    context.diagnostics.finish('cancelled', error_code='superseded_result')
                    return
                selected = self._input
                if selected is None or outcome.record.input_revision is None or outcome.record.input_revision.digest != selected.revision:
                    self._phase = "cancelled"
                    self._error = {"code": "superseded_result", "message": "Older generation result was ignored"}
                    context.diagnostics.finish('cancelled', error_code='superseded_result')
                    return
                self._artifact = artifact
                self._site_artifact = site_artifact
                self._phase = "draft_ready"
                self._connected = self._mode == "live_provider"
                if not outcome.persisted:
                    self._error = {
                        "code": outcome.persistence_error_code or "project_persistence_failed",
                        "message": "Draft is valid in memory but could not be persisted",
                    }
                context.diagnostics.finish('succeeded' if outcome.persisted else 'failed',
                    persisted=outcome.persisted, error_code=outcome.persistence_error_code)
                if outcome.persisted and registered is not None:
                    self._application.diagnostics.remember_binding(context.diagnostics.execution_id,
                        request_id=outcome.record.request_id,
                        input_revision=outcome.record.input_revision.digest,
                        source_revision=registered.revision)
        finally:
            with self._lock:
                self._workers.discard(current_thread())

    def cancel(self) -> dict[str, object]:
        self._application.cancel_generation()
        with self._lock:
            if self._phase == "generating":
                self._phase = "cancelled"
            self._acknowledged_identity = None
            return self.snapshot()

    def load_replay(self, replay: "ReplayFixture") -> dict[str, object]:
        """Promote one revalidated stored result without provider or image-byte access."""
        if self._mode != "replay" or replay.source != "replay":
            raise BrokerError("replay_mode_required", "Stored replay requires replay mode")
        checked = GeneratedDraftRecord.from_dict(replay.record.to_dict())
        if checked.input_revision != replay.input_revision:
            raise BrokerError("replay_input_mismatch", "Replay input identity does not match its draft")
        image_ref = replay.input_revision.images[0]
        prepared = PreparedInput(replay.input_revision, (), ())
        selected = ProductInput(
            revision=replay.input_revision.digest,
            prompt=replay.input_revision.prompt,
            input_kind=replay.input_revision.input_kind,
            image_name=image_ref["name"],
            media_type=image_ref.get("mime_type"),
            image_bytes=None,
            image_sha256=image_ref["sha256"],
            width=None,
            height=None,
            image_dimensions_px=None,
            sidecar_name=None,
            sidecar_sha256=None,
            measurement_constraints=(),
            measurement_count=0,
            prepared=prepared,
        )
        self._application.set_draft(checked, persist=False)
        artifact = self._register(checked)
        with self._lock:
            self._input = selected
            self._phase = "draft_ready"
            self._generation_id = None
            self._acknowledged_identity = None
            self._artifact = artifact
            self._error = None
            self._connected = False
            return self.snapshot()

    def shutdown(self, timeout_s: float = 2.0) -> None:
        """Cancel owned generation and briefly join its worker before teardown."""
        if getattr(self,'library_workspace',None) is not None:self.library_workspace.shutdown()
        self.cancel()
        with self._lock:
            workers = tuple(self._workers)
        for worker in workers:
            if worker is not current_thread():
                worker.join(max(0.0, timeout_s))
        # Generation can finish while its asynchronous diagnostic writes are
        # still queued. Drain only this workflow's local sink before teardown;
        # physical STOP/watchdog paths do not enter this developer flush.
        if not self._application.diagnostics.flush(timeout=max(0.0,timeout_s)):
            self._application.diagnostics.note_storage_error()

    def provider_settings_changed(self) -> dict[str, object]:
        if self._gateway_factory is None:
            raise BrokerError("provider_gateway_unavailable", "Provider gateway cannot be refreshed", status=503)
        with self._lock:
            self._provider_refresh_serial += 1
            serial = self._provider_refresh_serial
            self._provider_configuration_state = 'refreshing'
        try:
            gateway=self._gateway_factory()
            provider_state=dict(self._provider_state_getter())
        except Exception as error:
            # Legacy settings save may already have changed the disk. Retain
            # the original exception and old input/gateway, but do not execute
            # a new model request as if the new configuration were confirmed.
            with self._lock:
                if serial == self._provider_refresh_serial:
                    self._provider_configuration_state = 'unconfirmed'
                    self._provider_observation_error = error
            raise
        with self._lock:
            if serial != self._provider_refresh_serial:
                raise BrokerError('provider_refresh_superseded','Newer provider settings superseded this refresh.',status=409)
            try:self._application.set_generation_gateway(gateway)
            except Exception as error:
                self._provider_configuration_state = 'unconfirmed'
                self._provider_observation_error = error
                raise
            self._provider_state = provider_state
            self._provider_configuration_state = 'observed'
            self._provider_observation_error = None
            self._input = None
            self._artifact = None
            self._site_artifact = None
            self._generation_id = None
            self._acknowledged_identity = None
            self._scene_changes = None
            saved = self._application.record is not None or self._application.site_draft is not None
            self._phase = "restore_review_required" if saved else "empty"
            self._error = ({"code": "restore_review_required", "message": "Saved scene requires current review"}
                           if saved else {"code": "input_reselection_required", "message": "Provider settings changed; select input again"})
            self._connected = False
            return self.snapshot()

    def acknowledge(self, revision: str) -> dict[str, object]:
        with self._lock:
            self._assert_draft_persisted()
            self._invalidate_stale_derived()
            artifact = self._artifact or self._site_artifact
            if self._phase != "draft_ready" or artifact is None or self._input is None:
                raise BrokerError("draft_revision_stale", "Draft revision is not current")
            if revision != artifact.revision:
                raise BrokerError("draft_revision_stale", "Draft revision is not current")
            self._acknowledged_identity = (self._input.revision, revision)
            return self.snapshot()

    def assert_build_allowed(self, artifact_id: object, revision: object) -> None:
        with self._lock:
            self._assert_draft_persisted()
            identity = None if self._input is None or self._artifact is None else (
                self._input.revision, self._artifact.revision,
            )
            if (
                self._phase != "draft_ready" or self._artifact is None
                or artifact_id != self._artifact.artifact_id or revision != self._artifact.revision
                or self._acknowledged_identity != identity
            ):
                raise BrokerError("draft_acknowledgement_required", "Acknowledge the current input and draft before Build")

    def assert_site_build_allowed(self, artifact_id: object, revision: object) -> None:
        with self._lock:
            self._assert_draft_persisted()
            self._invalidate_stale_derived()
            artifact = self._site_artifact
            identity = None if self._input is None or artifact is None else (self._input.revision, artifact.revision)
            if (self._phase != "draft_ready" or artifact is None
                    or artifact_id != artifact.artifact_id or revision != artifact.revision
                    or self._acknowledged_identity != identity):
                raise BrokerError("draft_acknowledgement_required", "Acknowledge the current site scene before Build")
            if not self._broker.site_scene_capable():
                raise BrokerError("site_scene_capability_missing", "Connected Isaac engine cannot build site scenes")

    def _assert_draft_persisted(self):
        if self._error and self._error.get('code') == 'project_persistence_failed':
            raise BrokerError('project_persistence_failed',
                'Validated draft is only in memory; save failure must be resolved before Build or Run')

    def simulation_plan(self, body) -> dict:
        from twinpulse_core.site_simulation import make_plan
        from .simulation_assets import burger_inventory
        if type(body) is not dict or set(body) != {'scene_revision', 'start', 'goal', 'yaw_rad'}:
            raise BrokerError('simulation_plan_invalid', 'Supply the current scene, start, goal and yaw', status=400)
        with self._lock:
            self._invalidate_stale_derived()
            self._assert_room_inventory_complete()
            artifact = self._site_artifact
            if artifact is None or artifact.revision != body['scene_revision'] or self._phase != 'draft_ready':
                raise BrokerError('simulation_scene_stale', 'Reopen or generate the current scene first')
            self._assert_draft_persisted()
            try:
                plan = make_plan(artifact.scene, body['start'], body['goal'], burger_inventory(), yaw_rad=body['yaw_rad'])
            except (ValueError, OSError) as error:
                raise BrokerError('simulation_plan_rejected', str(error)[:320], status=400) from error
            return self._broker.register_simulation_plan(artifact.scene, plan)

    def simulation_preview(self):
        """Prepare a checked illustrative spawn/route for the current SIM draft."""
        from twinpulse_core.simulation_goal import preview_review
        from .simulation_assets import burger_inventory
        with self._lock:
            self._invalidate_stale_derived()
            self._assert_room_inventory_complete()
            artifact = self._site_artifact
            if artifact is None or self._phase != 'draft_ready':
                raise BrokerError('simulation_scene_stale', 'A current v2 scene is required for a SIM preview')
            self._assert_draft_persisted()
            try:
                review = preview_review(artifact.scene, burger_inventory())
            except (ValueError, OSError) as error:
                raise BrokerError('simulation_preview_rejected', str(error)[:320], status=400) from error
            review['plan'] = self._broker.register_simulation_plan(artifact.scene, review['plan'])
            self._simulation_seed = (artifact.revision, review['plan']['start'], review['plan']['yaw_rad'])
            return {**review, 'scene_revision': artifact.revision, 'start_source': 'planned_sim_spawn'}

    def simulation_goal(self, text, *, expected_revision=None, selection=None):
        trace=self._edit_trace('simulation_goal_review',str(uuid4()))
        try:
            result=self._simulation_goal(text,expected_revision=expected_revision,selection=selection)
        except Exception as error:
            self._goal_trace_summary(trace,getattr(error,'goal_diagnostic',None))
            trace.finish('failed',error=error)
            raise
        self._goal_trace_summary(trace,result.get('approach_diagnostic'))
        trace.finish()
        return result

    @staticmethod
    def _goal_trace_summary(trace,diagnostic):
        if not diagnostic:return
        trace.bind(diagnostic_sha256=canonical_sha256(diagnostic),
            termination_code=diagnostic['termination_code'],
            candidate_count=len(diagnostic['attempts']),
            accepted_count=sum(row['accepted'] for row in diagnostic['attempts']))
        for code,count in diagnostic['reason_counts'].items():
            child=trace.child('goal_candidate_rejection',error_code=code,calls=count)
            child.finish('failed',error_code=code)

    def _simulation_goal(self, text, *, expected_revision=None, selection=None):
        """Read-only SIM planning, no Build/Run or physical authority."""
        from twinpulse_core.simulation_goal import goal_review, coordinates
        from .simulation_assets import burger_inventory
        import math
        with self._lock:
            self._invalidate_stale_derived()
            self._assert_room_inventory_complete()
            artifact = self._site_artifact
            if artifact is None or self._phase != 'draft_ready' or (expected_revision and expected_revision != artifact.revision):
                raise BrokerError('simulation_scene_stale', 'Reopen the current scene before planning a SIM goal')
            view = self._broker.supervisor_state()
            snap = view['snapshot']
            start, yaw, source = None, 0., 'explicit_start'
            try:
                if snap and snap.get('run_id') and snap.get('applied_revision') == artifact.revision:
                    if (not view['engine_connected'] or not snap.get('telemetry_available') or snap.get('safety_state')
                            or snap['runtime_state'] not in {'paused', 'completed'}):
                        raise BrokerError('simulation_pose_unavailable', 'Stop and observe a fresh idle simulated pose before planning')
                    start, yaw, source = snap['position_m'][:2], snap['yaw_rad'], 'current_sim_pose'
                else:
                    start, _ = coordinates(text)
                    record = self._application.site_draft
                    if start is None and record.provider_name == 'local-room-recipe' and self._broker.project_id != 'default':
                        from .room_recipe import load_project_room_visual
                        visual = load_project_room_visual(self._application._project_store.path.parent.parent.parent, self._broker.project_id, record)
                        if visual:
                            placement = visual[0]['robot_placement']
                            start, yaw, source = placement['position_m'][:2], math.radians(placement['yaw_deg']), 'saved_sim_placement'
                    seed = getattr(self, '_simulation_seed', None)
                    if start is None and seed and seed[0] == artifact.revision:
                        start, yaw, source = seed[1], seed[2], 'planned_sim_spawn'
                context = self.scene_edit_context(text, None)
                furniture = {c['arguments']['id']: c['arguments']['kind'] for c in context['furniture_calls']}
                # Room props have many visual/keepout child prims too. Resolve
                # their semantic type from this saved revision, not part names
                # or a known room/photo. Visual-only parts remain excluded by
                # the core target/collision checks.
                current = self._site_draft_summary(self._application.site_draft)
                inventory = current['room_inventory']
                if inventory['scene_revision'] != artifact.revision:
                    raise BrokerError('simulation_scene_stale', 'Current room inventory changed; reopen the scene')
                furniture.update({item['id']: item['kind'] for item in inventory['items']
                                  if item['placement_status'] == 'represented'})
                for call in current['editable_calls']:
                    if call['tool'] in {'create_rack_row', 'place_pallet_stack'}:
                        furniture[call['arguments']['id']] = 'rack' if call['tool'] == 'create_rack_row' else 'pallet'
                review = goal_review(artifact.scene, text, start, burger_inventory(), yaw=yaw,
                    furniture=furniture, selection=selection, placement_contract=current['placement_contract'])
            except (ValueError, OSError) as error:
                rejected = BrokerError('simulation_goal_rejected', str(error)[:320], status=400)
                import re
                code=str(error).split(':',1)[0]
                rejected.goal_error_code=code if re.fullmatch('[A-Z][A-Z0-9_]{0,159}',code) else 'PLANNER_INTERNAL_ERROR'
                rejected.goal_diagnostic = getattr(error, 'goal_diagnostic', None)
                raise rejected from error
            if review['plan']:
                review['plan'] = self._broker.register_simulation_plan(artifact.scene, review['plan'])
            return {**review, 'scene_revision': artifact.revision, 'start_source': source}

    def assert_run_not_site_draft(self, simulation_id=None, revision=None) -> None:
        """A v2 review card cannot authorize Run of an older applied scene."""
        with self._lock:
            if simulation_id is not None:
                self._invalidate_stale_derived()
                self._assert_room_inventory_complete()
                artifact = self._site_artifact
                if (artifact is None or artifact.revision != revision
                        or self._acknowledged_identity is None
                        or self._acknowledged_identity[1] != revision):
                    raise BrokerError('simulation_scene_stale', 'Simulation must use the currently acknowledged scene')
                return
            if self._application.site_draft is not None:
                raise BrokerError("site_draft_review_only", "Site plan 2.0 is review-only; Run is unavailable")

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            self._invalidate_stale_derived()
            selected = self._input
            record = self._application.record
            draft = self._draft_summary(record) if (
                record is not None
                and self._phase in {"draft_ready", "restore_review_required"}
                and (self._phase == "restore_review_required" or self._artifact is not None)
            ) else None
            site_record = self._application.site_draft
            saved_record = site_record or record
            site_draft = self._site_draft_summary(site_record) if (
                site_record is not None and self._phase in {"draft_ready", "restore_review_required"}
                and (self._phase == "restore_review_required" or
                     selected is not None and selected.revision == site_record.input_revision.digest)
            ) else None
            provider = dict(self._provider_state)
            provider['configuration_state'] = self._provider_configuration_state
            provider['state_basis'] = 'startup_or_explicit_settings_refresh_not_authentication'
            if self._provider_observation_error is not None:provider['observation_error_type'] = type(self._provider_observation_error).__name__[:80]
            if self._provider_configuration_state != 'observed':provider['configured'] = False
            provider.setdefault("configured", False)
            provider.setdefault("label", "Explicit deterministic fixture" if self._mode == "explicit_fixture" else "Provider")
            provider["connected"] = self._connected and self._provider_configuration_state == 'observed'
            active_artifact = self._artifact or self._site_artifact
            identity = None if selected is None or active_artifact is None else (
                selected.revision, active_artifact.revision,
            )
            from twinpulse_core.room_photo_inventory import inventory_coverage
            photo = None  # No image hash selects a fixed inventory.
            return {
                "schema_version": "1.2",
                "mode": self._mode,
                "provider": provider,
                "phase": self._phase,
                "generation_id": self._generation_id,
                "execution_id": self._application.last_execution_id,
                "generation_progress": _public_generation_diagnostics(self._application.generation_diagnostics())
                    if self._generation_id is not None else None,
                "input": None if selected is None else {
                    "revision": selected.revision, "input_kind": selected.input_kind,
                    "prompt_length": len(selected.prompt), "image_name": selected.image_name,
                    "media_type": selected.media_type, "image_sha256": selected.image_sha256,
                    "width": selected.width, "height": selected.height,
                    "sidecar_name": selected.sidecar_name, "sidecar_sha256": selected.sidecar_sha256,
                    "measurement_count": selected.measurement_count,
                },
                "draft": draft,
                "site_draft": site_draft,
                "scene_edit_transaction": self.scene_edit_transaction.snapshot(),
                "photo_inventory": inventory_coverage(photo, site_draft['room_inventory'] if site_draft and
                    selected is not None and selected.revision == site_record.input_revision.digest else None),
                "presentation": None if site_record is None else self._presentation_snapshot(site_record),
                "saved_site_scene_protected": site_record is not None,
                "saved_input": None if saved_record is None or saved_record.input_revision is None else {
                    "input_kind": saved_record.input_revision.input_kind,
                    "image_name": saved_record.input_revision.images[0]["name"]
                        if saved_record.input_revision.images else None,
                    "media_type": saved_record.input_revision.images[0].get("mime_type")
                        if saved_record.input_revision.images else None,
                },
                "acknowledged_revision": self._acknowledged_identity[1] if self._acknowledged_identity else None,
                "build_allowed": bool(identity is not None and self._acknowledged_identity == identity and
                                      (self._artifact is not None or self._broker.site_scene_capable())),
                "error": self._error,
            }

    def _presentation_snapshot(self, record: SiteDraftRecord) -> dict[str, object]:
        stored = self._application.presentation_store().load(record.site.scene.revision)
        return {**(stored or DEFAULT_PRESENTATION), "saved": stored is not None,
                "source_scene_revision": record.site.scene.revision,
                "applies_on_next_build": True}

    def save_presentation(self, expected_source_scene_revision: str, value: object) -> dict[str, object]:
        with self._lock:
            source = self._application.site_draft
            if (self._phase != "draft_ready" or source is None or self._site_artifact is None
                    or self._workers or self._broker.has_pending_operations()
                    or expected_source_scene_revision != source.site.scene.revision):
                raise BrokerError("presentation_stale", "Reopen the current saved scene before changing its view", status=409)
            try:
                checked = checked_presentation(value)
                self._application.presentation_store().save(source.site.scene.revision, checked)
                if self._scene_changes is not None and self._scene_changes.operations:
                    self._site_artifact = self._register_scene_change(source, self._scene_changes)
                else:
                    self._site_artifact = self._register_site(source)
            except (ValueError, OSError, UnicodeError) as error:
                raise BrokerError("presentation_invalid", str(error), status=400) from error
            return self.snapshot()

    def inspection_room(self, root, project_id):
        """Current chat scene only; never substitute the historical bedroom."""
        from twinpulse_core.revisions import canonical_sha256
        with self._lock:
            self._invalidate_stale_derived()
            self._assert_room_inventory_complete()
            draft=self._application.site_draft;scene=self._site_artifact
            if draft and draft.draft_refinement:
                raise BrokerError('photo_alignment_unverified','Photo refinement remains incomplete; it is not current REAL geometry or pose authority.',status=409)
            if (project_id!=self._broker.project_id or draft is None or scene is None
                    or self._phase!='draft_ready' or self._workers):
                raise ValueError('CURRENT_CHAT_ROOM_UNAVAILABLE')
            body={'project_id':project_id,'input_revision':draft.input_revision.digest,
                  'scene_revision':scene.revision,'objects':__import__('json').loads(__import__('json').dumps(scene.scene.to_dict()['objects'])),
                  'adapter':'current-chat-room-1.0',
                  'photo_revision':draft.input_revision.images[0]['sha256'] if draft.input_revision.images else None}
            return {**body,'revision':canonical_sha256(body)}

    def inspection_scene(self, root, project_id):
        """Immutable current-chat scene, never the preserved bedroom fallback."""
        with self._lock:
            self.inspection_room(root, project_id)
            return __import__('json').loads(__import__('json').dumps(self._site_artifact.scene.to_dict()))

    def inspection_source_token(self):
        # Atomic immutable identities, no disk/image hashing on the heartbeat.
        draft=self._application.site_draft;scene=self._site_artifact
        return (self._phase,draft.input_revision.digest if draft else None,scene.revision if scene else None)

    def has_active_generation(self) -> bool:
        with self._lock:
            return bool(self._workers) or (getattr(self,'library_workspace',None) is not None and self.library_workspace.active())

    def generation_settling(self, generation_id: str | None) -> bool:
        """Process-local cancellation hint; never a persisted retry authority."""
        with self._lock:
            return bool(generation_id and generation_id == self._generation_id
                        and self._phase == 'cancelled' and self._workers)

    def _register(self, record: GeneratedDraftRecord) -> RegisteredArtifact:
        if record.validation_receipt is None:
            raise InvalidProviderResponseError("Generated draft has no validation receipt")
        artifact = self._broker.register_artifact(
            f"draft-{record.validation_receipt.bundle_sha256[:24]}", record.bundle,
        )
        self._restore_artifact_diagnostics(record,artifact)
        return artifact

    def _register_site(self, record: SiteDraftRecord) -> RegisteredSiteScene:
        checked = SiteDraftRecord.from_dict(record.to_dict())
        visual = self._application.room_visual_descriptor(checked)
        artifact = self._broker.register_site_scene(
            f"site-{checked.site.scene.revision[:24]}", checked.site.scene,
            visual_preview=visual,
            presentation=self._application.presentation_store().load(record.site.scene.revision),
        )
        self._restore_artifact_diagnostics(record,artifact)
        return artifact

    def _register_scene_change(self, record: SiteDraftRecord,
                               history: SceneChangeHistory) -> RegisteredSiteScene:
        _, site = history.replay(record)
        visual = self._application.room_visual_descriptor(record)
        if visual is not None:
            visual = {**visual, "scene_change_revision": site.scene.revision}
        artifact = self._broker.register_site_scene(
            f"edited-{site.scene.revision[:24]}", site.scene,
            visual_preview=visual,
            presentation=self._application.presentation_store().load(record.site.scene.revision),
        )
        self._restore_artifact_diagnostics(record,artifact)
        if history.operations:
            refs=self._application.diagnostics.restore_edit_binding(
                request_id=record.request_id,input_revision=record.input_revision.digest,
                source_revision=record.site.scene.revision,
                operation_id=history.operations[-1].operation_id,
                history_digest=canonical_sha256(history.to_dict()),result_revision=artifact.revision)
            if refs:self._broker.bind_artifact_diagnostics(artifact.artifact_id,**refs)
        return artifact

    def _restore_artifact_diagnostics(self, record, artifact):
        if record.input_revision is None:return
        source_revision=(record.site.scene.revision if isinstance(record,SiteDraftRecord)
                         else record.validation_receipt.bundle_sha256)
        refs=self._application.diagnostics.restore_binding(request_id=record.request_id,
            input_revision=record.input_revision.digest,source_revision=source_revision)
        if refs:
            self._broker.bind_artifact_diagnostics(artifact.artifact_id,**refs,
                **({'scene_edit_revision':artifact.revision} if artifact.revision!=source_revision else {}))

    def _scene_edit_store(self) -> SceneChangeStore:
        source = self._application.site_draft
        blocked=[code for code,failed in (
            ('CURRENT_REVIEW_REQUIRED',self._phase!='draft_ready'),
            ('CURRENT_SOURCE_REQUIRED',source is None),
            ('CURRENT_INPUT_REQUIRED',self._input is None),
            ('CURRENT_INPUT_MISMATCH',source is not None and self._input is not None
                and self._input.revision!=source.input_revision.digest),
            ('CURRENT_ARTIFACT_REQUIRED',self._site_artifact is None),
            ('CURRENT_GENERATION_PENDING',bool(self._workers)),
            ('CURRENT_ENGINE_COMMAND_PENDING',self._broker.has_pending_operations()),
            ('DERIVED_REVIEW_BRANCH_ACTIVE',self._derived_revision is not None)) if failed]
        if blocked:
            message=('The current Isaac command is still pending. Keep your message draft and send it after the command ACK; '
                'no model request or scene edit was sent.' if blocked==['CURRENT_ENGINE_COMMAND_PENDING'] else
                'Open the current saved v2 room review and finish pending work; no model request or scene edit was sent.')
            raise BrokerError('scene_edit_unavailable',message+' ['+', '.join(blocked)+']',status=409)
        if self.scene_edit_transaction.locked():
            raise BrokerError('engine_state_unknown','Resolve the current scene transaction before another edit.',status=409)
        return self._application.scene_change_store()

    def preview_scene_edit(self, *, operation_id: str, mode: str,
                           target_call_id: str | None, tool_call: Mapping[str, object] | None,
                           _diagnostics=None) -> dict[str, object]:
        trace=_diagnostics or self._edit_trace('scene_edit_preview',operation_id)
        try:
            with trace.span('scene_edit_validation'):
                value=self._preview_scene_edit(operation_id=operation_id,mode=mode,
                    target_call_id=target_call_id,tool_call=tool_call)
            if _diagnostics is None:trace.finish()
            return value
        except Exception as error:
            if _diagnostics is None:trace.finish('failed',error=error)
            raise

    def _edit_trace(self,stage,operation_id,*,feedback_lineage=None):
        with self._lock:
            source=self._application.site_draft
            prior=self._broker.artifact_diagnostic_refs(self._site_artifact.artifact_id) if self._site_artifact else {}
            related={key:prior[key] for key in ('evidence_kind','evidence_id','scene_edit_execution_id') if key in prior}
            return self._application.diagnostics.begin(stage,component='app',operation_id=operation_id,
                request_id=source.request_id if source else None,
                input_revision=self._input.revision if self._input else None,
                source_scene_revision=source.site.scene.revision if source else None,
                draft_revision=self._site_artifact.revision if self._site_artifact else None,**related,
                **(feedback_lineage or {}))

    def _preview_scene_edit(self, *, operation_id: str, mode: str,
                           target_call_id: str | None, tool_call: Mapping[str, object] | None) -> dict[str, object]:
        with self._lock:
            store = self._scene_edit_store()
            try:
                if store.project_store is not None:
                    current_project = store.project_store.load()
                    if (current_project is None or current_project.project_id != store.project_id
                            or current_project.site_draft != store.source):
                        raise ValueError("saved original project changed; reopen the scene")
                history = store.load()
                if history.current_scene_revision != self._site_artifact.revision:
                    raise ValueError("saved edit revision changed; reopen the scene")
                return history.preview(store.source, operation_id=operation_id, mode=mode,
                                       target_call_id=target_call_id, tool_call=tool_call)
            except (OSError, ValueError) as error:
                raise BrokerError("scene_edit_invalid", str(error), status=409) from error

    def scene_edit_context(self, request_text: str, selected_call_id: str | None, *, dependency=False) -> dict[str, object]:
        with self._lock:
            store = self._scene_edit_store()
            try:
                if store.project_store is not None:
                    current_project = store.project_store.load()
                    if (current_project is None or current_project.project_id != store.project_id
                            or current_project.site_draft != store.source):
                        raise ValueError("saved original project changed; reopen the scene")
                history = store.load()
                if history.current_scene_revision != self._site_artifact.revision:
                    raise ValueError("saved edit revision changed; reopen the scene")
                return (feedback_edit_context if dependency else furniture_edit_context)(
                    store.project_id,store.source,history,request_text,selected_call_id)
            except (OSError, ValueError) as error:
                raise BrokerError("scene_edit_context_invalid", str(error), status=409) from error

    def preview_scene_edit_proposal(self, *, operation_id: str, request_text: str,
                                    selected_call_id: str | None, expected_revision: str,
                                    proposal: Mapping[str, object],_feedback_lineage=None) -> dict[str, object]:
        from .scene_edit_transaction import checked_feedback_lineage
        lineage=checked_feedback_lineage(_feedback_lineage)
        trace=self._edit_trace('scene_edit_proposal',operation_id,
            feedback_lineage={key:value for key,value in (lineage or {}).items() if key!='feedback_preview_execution_id'})
        if lineage:
            lineage['feedback_preview_execution_id']=trace.execution_id
            trace.bind(**lineage)
        try:
            with trace.span('scene_edit_proposal_validation'):
                value=self._preview_scene_edit_proposal(operation_id=operation_id,request_text=request_text,
                    selected_call_id=selected_call_id,expected_revision=expected_revision,proposal=proposal,_diagnostics=trace)
            if lineage and value['preview'] is not None:value['preview']['feedback_lineage']=lineage
            trace.finish()
            return value
        except Exception as error:
            trace.finish('failed',error=error)
            raise

    def _preview_scene_edit_proposal(self, *, operation_id: str, request_text: str,
                                    selected_call_id: str | None, expected_revision: str,
                                    proposal: Mapping[str, object],_diagnostics=None) -> dict[str, object]:
        with self._lock:
            dependency=proposal.get('schema_version')=='scene-edit-proposal-1.1'
            context = self.scene_edit_context(request_text, selected_call_id,dependency=dependency)
            if context["current_scene_revision"] != expected_revision:
                raise BrokerError("scene_edit_proposal_stale", "Saved scene revision changed; request a new proposal", status=409)
            try:
                mode, target, call, explanation = (checked_feedback_proposal if dependency else
                    checked_furniture_proposal)(context, proposal)
            except (ValueError, TypeError, KeyError) as error:
                raise BrokerError("scene_edit_proposal_invalid", str(error), status=409) from error
            if mode == "clarify":
                return {"status": "clarify", "explanation": explanation,
                        "context_sha256": context["context_sha256"], "preview": None}
            preview = self.preview_scene_edit(operation_id=operation_id, mode=mode,
                                              target_call_id=target, tool_call=call,_diagnostics=_diagnostics)
            return {"status": "preview", "explanation": explanation,
                    "context_sha256": context["context_sha256"], "preview": preview}

    def apply_scene_edit(self, operation: Mapping[str, object], preview_digest: str) -> dict[str, object]:
        stage='scene_edit_undo' if operation.get('mode')=='undo' else 'scene_edit_apply'
        trace=self._edit_trace(stage,operation.get('operation_id'))
        try:
            # Legacy remains save/review-only. Its durable history still feeds
            # REAL revision guards, so share admission before taking _lock.
            with self.scene_edit_transaction.admission(''):
                value=self._apply_scene_edit(operation,preview_digest,_diagnostics=trace)
            trace.finish()
            return value
        except Exception as error:
            trace.finish('failed',error=error)
            raise

    def _apply_scene_edit(self, operation: Mapping[str, object], preview_digest: str,_diagnostics=None) -> dict[str, object]:
        with self._lock:
            store = self._scene_edit_store()
            # Response loss and duplicate Apply return the already committed state.
            from .scene_changes import SceneChange
            checked=SceneChange.from_dict(operation)
            prior=next((item for item in store.load().operations if item.operation_id==checked.operation_id),None)
            if prior is not None:
                if prior!=checked or preview_digest!=canonical_sha256(checked.to_dict()):
                    raise BrokerError('scene_edit_duplicate_conflict','Operation ID was used for a different edit.',status=409)
                return self.snapshot()
            if operation.get("parent_revision") != self._site_artifact.revision:
                raise BrokerError("scene_edit_stale_or_invalid", "Review revision changed; reopen the scene", status=409)
            # A rejected/stale request leaves the currently reviewed scene intact.
            # A committed edit then invalidates review even if registration fails.
            try:
                with _diagnostics.span('scene_edit_validate_and_save'):
                    history = store.apply(operation, preview_digest)
            except (OSError, ValueError) as error:
                raise BrokerError("scene_edit_stale_or_invalid", str(error), status=409) from error
            # Persist correlation after the mandatory history commit, before
            # optional 3D registration can fail. Never modify the saved history.
            history_digest=canonical_sha256(history.to_dict())
            _diagnostics.bind(scene_edit_revision=history.current_scene_revision,
                              scene_change_sha256=history_digest)
            self._application.diagnostics.flush()
            self._application.diagnostics.remember_edit_binding(_diagnostics.execution_id,
                request_id=store.source.request_id,input_revision=store.source.input_revision.digest,
                source_revision=store.source.site.scene.revision,
                operation_id=history.operations[-1].operation_id,
                history_digest=history_digest,result_revision=history.current_scene_revision)
            self._acknowledged_identity = None
            self._site_artifact = None
            self._scene_changes = history
            self._derived_revision = None
            self._application.clear_derived_review()
            try:
                with _diagnostics.span('scene_edit_register_review'):
                    self._site_artifact = self._register_scene_change(store.source, history)
                _diagnostics.bind(scene_edit_revision=self._site_artifact.revision,
                    artifact_id=self._site_artifact.artifact_id)
                self._broker.bind_artifact_diagnostics(self._site_artifact.artifact_id,
                    scene_edit_execution_id=_diagnostics.execution_id)
            except (OSError, ValueError) as error:
                raise BrokerError("scene_edit_saved_review_unavailable",
                                  "Edit was saved, but 3D review could not be registered; reopen this scene", status=409) from error
            return self.snapshot()

    def _publish_scene_change(self,store,history):
        with self._lock:
            self._acknowledged_identity=None
            self._scene_changes=history
            self._derived_revision=None
            self._application.clear_derived_review()
            self._site_artifact=self._register_scene_change(store.source,history)

    def _invalidate_stale_derived(self) -> None:
        if self._derived_revision is None:
            return
        record = self._application.derived_review
        if (record is None or record.revision != self._derived_revision or self._input is None
                or self._input.revision != record.source.input_revision.digest):
            self._site_artifact = None
            self._acknowledged_identity = None
            self._derived_revision = None

    def adopt_derived_review(self, input_revision: str, source_revision: str,
                             workspace_revision: str | None, *, restore: bool = False) -> dict[str, object]:
        with self._lock:
            if self._application.site_draft is not None and self._application.scene_change_store().load().operations:
                raise BrokerError("scene_edit_branch_conflict",
                                  "Saved scene edits and scan-derived review are separate branches", status=409)
            # Failed selection never falls back to an acknowledged older scene.
            self._acknowledged_identity = None
            self._site_artifact = None
            self._derived_revision = None
            if (self._phase != "draft_ready" or self._input is None or self._workers
                    or self._input.revision != input_revision):
                self._application.clear_derived_review()
                raise BrokerError("derived_review_stale", "Select the current original site draft first")
            try:
                record = self._application.adopt_derived_review(
                    input_revision, source_revision, workspace_revision, restore=restore)
                artifact = self._broker.register_site_scene(
                    f"derived-{record.revision[:24]}", record.site.scene)
            except (ValueError, OSError) as error:
                self._application.clear_derived_review()
                raise BrokerError("derived_review_unavailable", "Derived review could not be validated or saved") from error
            self._site_artifact = artifact
            self._derived_revision = record.revision
            return self.snapshot()

    def _assert_room_inventory_complete(self):
        if self.scene_edit_transaction.locked():
            raise BrokerError('engine_state_unknown','The scene transaction needs current engine reconciliation.',status=409)
        record = self._application.site_draft
        if record is not None:
            from twinpulse_core.progressive_twin import require_task_context
            try:
                # Current SIM/REAL adapters do not yet supply a checked full
                # vertical envelope for pending objects. Fail closed for tasks,
                # not for viewing/building the valid draft. G2/G5 add context.
                current = (self._scene_changes.effective(record).progressive(record)
                    if self._scene_changes is not None and self._scene_changes.schema_version=='scene-changes-1.2'
                    else record.progressive_twin)
                if current and current['schema_version']=='progressive-twin-1.1' and current['unresolved']:
                    raise ValueError('PROGRESSIVE_TASK_UNRESOLVED: '+', '.join(r['id'] for r in current['unresolved']))
                require_task_context(current)
            except ValueError as error:
                raise BrokerError('progressive_task_unresolved',str(error),status=409) from error
            inventory = self._site_draft_summary(record).get('photo_inventory')
            if inventory and not inventory['route_inventory_complete']:
                raise BrokerError('room_inventory_incomplete',
                    'Photo hazards still require placement: ' + ', '.join(inventory['missing_route_items']), status=409)

    def _site_draft_summary(self, record: SiteDraftRecord) -> dict[str, object]:
        # All callers use the workflow lock. Polling must not recompile the
        # same immutable scene/history every 750 ms and starve unrelated reads.
        # Full content digests (not mtime/object identity or geometry alone)
        # also bind pending-only changes. This memo is a deterministic summary,
        # not permission/validation authority; goal/preview/Tx retain their
        # independent current-context and durable-state admission checks.
        derived=self._application.derived_review if self._derived_revision is not None else None
        edits=self._scene_changes if derived is None else None
        artifact=self._site_artifact
        selected=self._input
        acknowledged=self._acknowledged_identity
        derived_selection=self._derived_revision
        capable=self._broker.site_scene_capable()
        material=dict(record=record.to_dict(),
            edits=edits.to_dict() if edits is not None else None,
            derived=derived.to_dict() if derived is not None else None,
            derived_selection=derived_selection,
            artifact=None if artifact is None else [artifact.artifact_id,artifact.revision],
            input_revision=selected.revision if selected is not None else None,
            acknowledged=acknowledged,capable=capable)
        # Lease/ACK observations change independently of immutable geometry.
        # Do not replay all scene edits merely because a lease became valid.
        # Build permission is recalculated from the SAME fresh captures below;
        # a cached geometry summary never supplies control authority.
        key=canonical_sha256({k:v for k,v in material.items() if k not in {'acknowledged','capable'}})
        identity=None if selected is None or artifact is None else (selected.revision,artifact.revision)
        build_allowed=bool(artifact is not None and identity==acknowledged and capable)
        cached=self._site_summary_cache
        if cached is not None and cached[0]==key:
            result=deepcopy(cached[1])
            result['build_allowed']=build_allowed
            return result
        result=self._compute_site_draft_summary(record,site_capable=capable,derived=derived,edits=edits,
            artifact=artifact,selected=selected,acknowledged=acknowledged,derived_selection=derived_selection)
        result['build_allowed']=build_allowed
        # One entry per workflow, no persistent validation/permission cache.
        # Metadata readers consume only an already-published summary. Bind its
        # full source/history/input (including pending-only changes), without
        # giving that display snapshot any mutation/ACK authority.
        metadata_identity=canonical_sha256(dict(source=material['record'],history=material['edits'],
            input_revision=material['input_revision'],derived_selection=material['derived_selection'],
            artifact=material['artifact']))
        self._site_summary_cache=(key,deepcopy(result),metadata_identity)
        return result

    def _compute_site_draft_summary(self, record: SiteDraftRecord, *, site_capable: bool,
                                   derived, edits, artifact, selected, acknowledged, derived_selection) -> dict[str, object]:
        from .site_review_provenance import site_review_provenance
        edited_plan, edited_site = edits.replay(record) if edits is not None else (None, None)
        effective = edits.effective(record) if edits is not None and edits.schema_version=='scene-changes-1.2' else None
        # A fresh draft has no sidecar/cache yet. Its exact state is still
        # available in memory; hashing it must not create history or write disk.
        state_history = (edits or SceneChangeHistory.empty(self._application.project_id, record)) if derived_selection is None else None
        state_digest = (state_history.state_sha256(effective if effective is not None else state_history.effective(record))
                        if state_history is not None else None)
        site = derived.site if derived is not None else edited_site or record.site
        original_objects = {item.id: item for item in record.site.scene.objects}
        identity = None if selected is None or artifact is None else (selected.revision, artifact.revision)
        allowed = bool(artifact is not None and identity == acknowledged
                       and site_capable)
        from twinpulse_core.room_items import room_inventory
        from twinpulse_core.room_photo_inventory import inventory_coverage
        inventory = room_inventory(edited_plan or record.plan, site.scene)
        photo = None  # Inventory comes from this generated plan, never a known-photo lookup.
        from twinpulse_core.progressive_twin import summary as progressive_summary
        from twinpulse_core.draft_refinement import public_refinement
        from .dependency_patch import initial_state
        original_context=initial_state(record)
        pending_context_current=(effective is None or (effective.inventory==original_context.inventory and
            effective.placement==original_context.placement))
        return {
            "schema_version": "2.0", "revision": site.scene.revision,
            "placement_contract": deepcopy(effective.placement if effective is not None else record.placement_contract),
            "scene_state_sha256": state_digest,
            "draft_acceptance":dict(status='saved_editable_prior',positions='estimated',
                sensor_correction='not_verified',physical_trial='not_run',physical_authority=False,
                unresolved_count=len((record.progressive_twin or {}).get('unresolved',[]))),
            "draft_refinement":public_refinement(record.draft_refinement,
                (edited_plan or record.plan).to_dict() if derived is None else None,
                pending_context_current=pending_context_current),
            "progressive_twin":(public_progressive(record,effective)
                if effective is not None else progressive_summary(record.progressive_twin,
                current_plan_sha256=canonical_sha256((edited_plan or record.plan).to_dict())) if derived is None else
                progressive_summary(record.progressive_twin,current_plan_sha256='derived')),
            "room_inventory": inventory, "photo_inventory": inventory_coverage(photo, inventory),
            "derived_review_revision": derived.revision if derived is not None else None,
            "scene_edit_revision": site.scene.revision if edits is not None and edits.operations else None,
            "scene_edit_count": len(edits.operations) if edits is not None else 0,
            "editable_calls": [item.to_dict() for item in (edited_plan or record.plan).calls
                               if item.tool not in {"create_floor", "place_predefined_agv", "create_navigation_task"}],
            "original_scene_revision": record.site.scene.revision,
            "geometry_provenance": "offline_review_unverified" if derived is not None or edits is not None and edits.operations else "original_tool_plan",
            "review_provenance": site_review_provenance(
                record, edited_plan or record.plan, site.scene.revision,
                len(edits.operations) if edits is not None else 0),
            "artifact_id": artifact.artifact_id if artifact is not None else None,
            "input_revision": record.input_revision.digest, "plan_sha256": record.plan_sha256,
            "request_id": record.request_id, "provider_name": record.provider_name,
            "model_id": record.model_id, "scene_id": site.scene.id,
            "summary": ("Derived offline review; original retained; alignment unverified" if derived else record.plan.summary), "source": site.scene.source,
            "tool_count": len((edited_plan or record.plan).calls), "object_count": len(site.scene.objects),
            "robot_profile_id": site.robot.profile_id if site.robot else None,
            "mission_id": site.mission.id if site.mission else None,
            "navigation_map_ready": site.navigation_map is not None,
            "review_required": True, "build_allowed": allowed, "run_allowed": False,
            "objects": [_object_summary(item, "offline_review_unverified" if derived else
                                        "user_local_edit" if edited_site is not None and
                                        item != original_objects.get(item.id) else record.provider_name)
                        for item in site.scene.objects],
        }

    def _draft_summary(self, record: GeneratedDraftRecord) -> dict[str, object]:
        bundle = record.bundle
        artifact = self._artifact
        revision = artifact.revision if artifact is not None else (
            record.validation_receipt.bundle_sha256 if record.validation_receipt is not None else record.plan_sha256
        )
        objects = [_object_summary(item, record.provider_name) for item in bundle.scene.objects]
        return {
            "artifact_id": artifact.artifact_id if artifact is not None else "restore-review-required",
            "revision": revision,
            "input_revision": record.input_revision.digest if record.input_revision is not None else None,
            "plan_sha256": record.plan_sha256, "request_id": record.request_id,
            "provider_name": record.provider_name, "model_id": record.model_id,
            "provider_provenance": dict(record.provider_provenance),
            "scene_id": bundle.scene.id, "robot_profile_id": bundle.robot.id,
            "task_id": bundle.task.id, "object_count": len(objects),
            "tool_count": len(record.plan.calls), "objects": objects,
            "source": (
                "fixture" if self._mode == "explicit_fixture"
                else "replay" if self._mode == "replay"
                else "generated"
            ),
            "approximate": True,
        }


def _public_generation_error(error: Exception) -> dict[str, object]:
    mappings: tuple[tuple[type[Exception], str], ...] = (
        (GenerationCancelledError, "generation_cancelled"),
        (ProviderTimeoutError, "provider_timeout"),
        (ProviderAuthenticationError, "provider_authentication_failed"),
        (ProviderRateLimitError, "provider_rate_limited"),
        (ProviderUnavailableError, "provider_unavailable"),
        (ProviderRequestError, "provider_request_failed"),
        (ProviderCapabilityError, "provider_capability_unsupported"),
        (ProviderConfigurationError, "provider_not_configured"),
        (InvalidProviderResponseError, "provider_response_invalid"),
    )
    from twinpulse_provider.generation_policy import GenerationBudgetError
    code = getattr(error, 'code') if isinstance(error, GenerationBudgetError) else next(
        (value for kind, value in mappings if isinstance(error, kind)), "generation_failed")
    message = re.sub(r"\s+", " ", str(error)).strip() or "Generation failed"
    result = {"code": code, "message": message[:320]}
    diagnostic = getattr(error, "diagnostics", None)
    if isinstance(diagnostic, dict):
        # A provider object must not leak arbitrary bodies or credentials into
        # the product journal. Only small typed operational facts are public.
        result["diagnostics"] = _public_generation_diagnostics(diagnostic)
    return result


def _public_generation_diagnostics(diagnostic):
    if not isinstance(diagnostic, dict):return {}
    allowed = {}
    output=diagnostic.get('output_diagnostics')
    if isinstance(output,dict):
        safe={k:v for k,v in output.items() if k in {'visible_chars','visible_nonwhitespace_chars',
            'visible_trailing_whitespace_chars','reasoning_chars','reasoning_nonwhitespace_chars','reasoning_tokens'}
            and type(v) is int and 0<=v<=10000000}
        if type(output.get('final_empty')) is bool:safe['final_empty']=output['final_empty']
        if output.get('output_pattern') in {'hidden_reasoning_without_final_at_limit','visible_whitespace_dominated_at_limit',
                'incomplete_final_at_limit','empty_final_without_length','final_output_present'}:
            safe['output_pattern']=output['output_pattern']
        allowed['output_diagnostics']=safe
    activity=diagnostic.get('generation_activity')
    if isinstance(activity,dict) and activity.get('schema_version')=='generation-activity-1.0':
        if (isinstance(activity.get('stage'),str) and re.fullmatch(r'[a-z_]{1,40}',activity['stage'])
                and activity.get('phase') in ('waiting_model','validating','building','awaiting_frame','ready','blocked')):
            public={k:activity[k] for k in ('schema_version','stage','phase')}
            for key in ('batch_index','batch_total'):
                if type(activity.get(key)) is int and 0<=activity[key]<=2**53-1:public[key]=activity[key]
            for key,pattern in (('affected_ids',r'[A-Za-z][A-Za-z0-9_-]{0,31}'),('reason_codes',r'[A-Z][A-Z0-9_]{0,79}')):
                values=activity.get(key)
                if isinstance(values,list) and len(values)<=64 and all(isinstance(v,str) and re.fullmatch(pattern,v) for v in values):
                    public[key]=list(values)
            allowed['generation_activity']=public
    def public_checks(report):
        from twinpulse_core.geometry_checks import CHECK_REVISION, PHASES
        if not isinstance(report,dict) or report.get('check_ledger_version')!=CHECK_REVISION:return {}
        rows=[]
        for item in report.get('checks',[])[:len(PHASES)]:
            if not isinstance(item,dict) or item.get('check_id') not in PHASES or item.get('status') not in ('passed','partial','failed','blocked','not_run','error'):continue
            row={'check_id':item['check_id'],'status':item['status'],
                 'blocked_by':[v for v in item.get('blocked_by',[]) if v in PHASES]}
            revision=item.get('candidate_revision')
            if isinstance(revision,str) and re.fullmatch(r'[a-f0-9]{64}',revision):row['candidate_revision']=revision
            rows.append(row)
        complete=(report.get('checks_complete') is True and len(rows)==len(PHASES)
            and {r['check_id'] for r in rows}==set(PHASES) and all(r['status']=='passed' for r in rows))
        return {'checks':rows,'checks_complete':complete,
                'checks_truncated':report.get('checks_truncated') is True}
    checks=public_checks(diagnostic.get('geometry_checks'))
    if checks:allowed['geometry_checks']=checks
    inventory=diagnostic.get('inventory_progress')
    if isinstance(inventory,dict) and inventory.get('schema_version')=='inventory-work-progress-1.0':
        counts=('observed_instances','inventory_count','parameterized_count','pending_count','parameter_batch_size')
        flags=('inventory_planned','parameters_complete','checkpoint_saved')
        if (all(type(inventory.get(k)) is int and 0<=inventory[k]<=2**53-1 for k in counts)
                and all(type(inventory.get(k)) is bool for k in flags)
                and inventory['parameterized_count']<=inventory['inventory_count']
                and (not inventory['inventory_planned'] or inventory['pending_count']==
                    inventory['inventory_count']-inventory['parameterized_count'])
                and inventory['parameters_complete']==(inventory['inventory_planned'] and inventory['pending_count']==0)):
            allowed['inventory_progress']={k:inventory[k] for k in ('schema_version',*counts,*flags)}
            for key in ('observation_saved','draft_saved'):
                if type(inventory.get(key)) is bool:
                    allowed['inventory_progress'][key]=inventory[key]
            allowed['inventory_progress'].update(automatic_resume=False,physical_authority=False)
    preview=diagnostic.get('generation_preview')
    if isinstance(preview,dict) and preview.get('schema_version')=='generation-preview-1.0':
        counts=('rendered_count','pending_count','inventory_count')
        if (preview.get('state') in ('building','ready','blocked')
                and all(type(preview.get(k)) is int and 0<=preview[k]<=2**53-1 for k in counts)
                and preview['rendered_count']+preview['pending_count']==preview['inventory_count']
                and all(preview.get(k) is None or isinstance(preview.get(k),str) and
                    re.fullmatch(r'[a-f0-9]{64}',preview[k]) for k in ('candidate_revision','scene_revision'))):
            allowed['generation_preview']={k:preview.get(k) for k in ('schema_version','state',*counts,
                'candidate_revision','scene_revision')}
            allowed['generation_preview'].update(preview_only=True,physical_authority=False)
            pending=preview.get('pending_objects')
            if isinstance(pending,list) and len(pending)==preview['pending_count'] and all(
                    isinstance(row,dict) and set(row)<={'id','reason_code','blocked_by'}
                    and isinstance(row.get('id'),str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',row['id'])
                    and isinstance(row.get('reason_code'),str) and 1<=len(row['reason_code'])<=100
                    and isinstance(row.get('blocked_by',[]),list)
                    and all(isinstance(identity,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',identity)
                        for identity in row.get('blocked_by',[])) for row in pending):
                allowed['generation_preview']['pending_objects']=deepcopy(pending)
            if isinstance(preview.get('error_code'),str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',preview['error_code']):
                allowed['generation_preview']['error_code']=preview['error_code']
    instances=diagnostic.get('instance_grounding')
    if isinstance(instances,dict) and instances.get('schema_version') in (
            'observed-instance-expansion-1.0','observed-instance-expansion-1.1',
            'observed-instance-expansion-1.2','observed-instance-expansion-1.3','observed-instance-expansion-1.4','observed-instance-expansion-1.5'):
        count=instances.get('effective_object_count')
        status=instances.get('status')
        if type(count) is int and 0<=count<=2**53-1 and status in (
                'count_preserved','count_partially_unverified','legacy_count_unverified'):
            allowed['instance_grounding']={'status':status,'effective_object_count':count,
                'expanded_groups':len(instances.get('groups',[])) if isinstance(instances.get('groups'),list) else 0,
                'unresolved_counts':len(instances.get('unresolved_counts',[])) if isinstance(instances.get('unresolved_counts'),list) else 0,
                'individual_pose_verified':False}
    retention=diagnostic.get('retention_revalidation')
    if (isinstance(retention,dict) and retention.get('gate')=='exact_plan_and_support_witness'
            and retention.get('validation') in ('passed','failed')
            and all(type(retention.get(k)) is bool for k in ('same_plan','same_witness'))
            and retention.get('physical_authority') is False
            and (retention['validation']=='passed')==(retention['same_plan'] and retention['same_witness'])):
        allowed['retention_revalidation']={k:retention[k] for k in
            ('validation','gate','same_plan','same_witness','physical_authority')}
    rollback=diagnostic.get('rollback_revalidation')
    if isinstance(rollback,dict) and rollback.get('validation') in ('passed','failed'):
        failed=rollback.get('failed_diagnosis')
        failed_rows=failed.get('issues',[]) if isinstance(failed,dict) else []
        if not isinstance(failed_rows,list):failed_rows=[]
        allowed['rollback_revalidation']={
            'validation':rollback['validation'],'external_call':False,
            **{k:rollback[k] for k in ('candidate_revision','failed_candidate_revision')
                if isinstance(rollback.get(k),str) and re.fullmatch(r'[0-9a-f]{64}',rollback[k])},
            'failed_codes':sorted({row['code'] for row in failed_rows[:64]
                if isinstance(row,dict) and isinstance(row.get('code'),str)
                and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',row['code'])})}
        if rollback.get('quality_status') in ('needs_revision','uncertain','not_applicable','not_run'):
            allowed['rollback_revalidation']['quality_status']=rollback['quality_status']
        allowed['rollback_revalidation'].update(public_checks(rollback.get('checks') or rollback.get('diagnosis')))
    decision=diagnostic.get('repair_decision')
    if isinstance(decision,dict) and decision.get('decision') in ('initial','progress','advanced_checks','no_progress',
        'rollback','exploring','repeated_candidate','evidence_insufficient','stage_complete'):
        from twinpulse_core.geometry_checks import PHASES
        allowed['repair_decision']={'decision':decision['decision'],
            'advanced_checks':[v for v in decision.get('advanced_checks',[]) if v in PHASES],
            **{k:decision[k] for k in ('progressed','regressed','stage_complete','branch_abandoned') if type(decision.get(k)) is bool}}
        if decision.get('repair_kind') in ('geometry','quality'):
            allowed['repair_decision']['repair_kind']=decision['repair_kind']
    scope=diagnostic.get('scope_decision')
    if isinstance(scope,dict) and scope.get('schema_version') in ('geometry-scope-1.0','geometry-scope-1.1'):
        rows=scope.get('accepted',[])
        if isinstance(rows,list):
            accepted=[{k:row[k] for k in ('id','anchor_id','reason_code')}
                for row in rows[:32] if isinstance(row,dict) and
                all(isinstance(row.get(k),str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,32}',row[k])
                    for k in ('id','anchor_id')) and
                row.get('reason_code') in ('packing_neighbor','support_alternative')]
            allowed['scope_decision']={'schema_version':scope['schema_version'],'accepted':accepted,
                'physical_authority':False}
    acceptance=diagnostic.get('stage_acceptance')
    if isinstance(acceptance,dict):
        allowed['stage_acceptance']={k:v for k,v in acceptance.items() if k in
            ('approximate_draft','photo_quality','Isaac_Build','SIM_Run_Stop','physical_alignment','physical_mission')
            and v in ('passed','partial','failed','not_run','blocked','uncertain','not_applicable','needs_revision','preview_passed','consistent')}
    quality=diagnostic.get('quality_review')
    if isinstance(quality,dict) and quality.get('schema_version') in ('candidate-quality-review-1.0','current-render-review-1.0','current-render-review-1.1','current-render-review-1.2','current-render-review-1.3'):
        values={k:v for k,v in quality.items() if k in ('status','render_comparison','support_relations','metric_scale','review_scope','visual_completeness')
            and v in ('not_applicable','needs_revision','needs_refinement','uncertain','not_run','unverified_against_photo','estimated_not_measured','consistent','reviewed','materialized_subset','complete_candidate')}
        for key in ('candidate_revision','plan_sha256','frame_key'):
            value=quality.get(key)
            if isinstance(value,str) and re.fullmatch(r'[a-f0-9]{64}',value):values[key]=value
        values['issue_count']=len(quality.get('issues',[])) if isinstance(quality.get('issues'),list) else 0
        prior=quality.get('relative_layout')
        if (isinstance(prior,dict) and prior.get('schema_version')=='relative-layout-prior-1.0'
                and prior.get('status') in ('needs_revision','uncertain','consistent_materialized_anchors')):
            values['relative_layout']={'status':prior['status'],'metric_scale':'estimated_not_measured',
                'sensor_alignment':'not_run','physical_authority':False}
            for key in ('anchor_ids','reviewed_anchor_ids','contradicted_anchor_ids',
                        'uncertain_anchor_ids','deferred_object_ids'):
                rows=prior.get(key)
                if isinstance(rows,list) and all(isinstance(v,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',v) for v in rows):
                    values['relative_layout'][key]=list(rows)
        allowed['quality_review']=values
    for key in ('request_id','attempt_id','input_kind','stage','model_id','status','finish_reason','remote_outcome','started_at','validation','error_type', 'checkpoint_id', 'parent_checkpoint_id', 'semantic_revision', 'policy_sha256'):
        value=diagnostic.get(key)
        if isinstance(value,str):allowed[key]=value[:256]
    for key in ('max_tokens','elapsed_s','timeout_s','repair_count','max_repairs','sequence'):
        value=diagnostic.get(key)
        if type(value) in (int,float) and math.isfinite(value) and value>=0:allowed[key]=value
    if isinstance(diagnostic.get('attempts'),list):
        allowed['attempts']=[{k:v for k,v in _public_generation_diagnostics(item).items() if k!='attempts'}
                             for item in diagnostic['attempts'][:32] if isinstance(item,dict)]
        allowed['attempts_total']=len(diagnostic['attempts'])
        allowed['attempts_truncated']=len(diagnostic['attempts'])>32
    for key in ('patch_shape','patch_effect','candidate_validation'):
        if diagnostic.get(key) in ('passed','failed','pending','changed','no_change'):
            allowed[key]=diagnostic[key]
    if diagnostic.get('role') in ('initial','repair','final_review'):
        allowed['role']=diagnostic['role']
    if type(diagnostic.get('repair')) is bool:
        allowed['repair']=diagnostic['repair']
    code=diagnostic.get('validation_code')
    if type(code) is str and re.fullmatch(r'[A-Z][A-Z0-9_]{1,80}',code):
        allowed['validation_code']=code
    if type(diagnostic.get('repair_no_progress')) is bool:
        allowed['repair_no_progress']=diagnostic['repair_no_progress']
    budget=diagnostic.get('budget')
    if isinstance(budget,dict):
        values={}
        for key in ('requests','max_requests','repairs','max_repairs','stalled_repairs','elapsed_s','remaining_s', 'cumulative_requests', 'cumulative_active_s'):
            value=budget.get(key)
            if type(value) in (int,float) and math.isfinite(value) and value>=0:values[key]=value
        for key in ('stop_reason','financial_scope'):
            value=budget.get(key)
            if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_]{1,80}',value):values[key]=value
        allowed['budget']=values
        usage=budget.get('usage')
        if budget.get('financial_scope')=='usage_only' and isinstance(usage,dict):
            safe={key:usage[key] for key in ('attempts','prompt_tokens','completion_tokens','usage_missing')
                if type(usage.get(key)) is int and usage[key]>=0}
            if len(safe)==4:values['usage']={**safe,'invoice_verified':False}
        cost=budget.get('cost')
        if isinstance(cost,dict) and cost.get('currency')=='USD' and cost.get('invoice_verified') is False:
            from decimal import Decimal, InvalidOperation
            normalized={}
            for key in ('limit_usd','estimated_usage_usd','reserved_unknown_usd'):
                value=cost.get(key)
                try:
                    number=Decimal(value) if type(value) is str and len(value)<=40 else None
                    if number is not None and number.is_finite() and number>=0:normalized[key]=str(number)
                except InvalidOperation:pass
            if len(normalized)==3:
                values['cost']={**normalized,'currency':'USD','invoice_verified':False}
        cumulative=budget.get('cumulative_cost')
        if isinstance(cumulative,dict) and cumulative.get('currency')=='USD' and cumulative.get('invoice_verified') is False:
            from decimal import Decimal, InvalidOperation
            normalized={}
            for key in ('estimated_usage_usd','reserved_unknown_usd'):
                value=cumulative.get(key)
                try:
                    number=Decimal(value) if type(value) is str and len(value)<=40 else None
                    if number is not None and number.is_finite() and number>=0:normalized[key]=str(number)
                except InvalidOperation:pass
            if len(normalized)==2 and type(cumulative.get('history_complete')) is bool:
                values['cumulative_cost']={**normalized,'currency':'USD','invoice_verified':False,
                    'history_complete':cumulative['history_complete']}
    if type(diagnostic.get('observation_cache_hit')) is bool:
        allowed['observation_cache_hit']=diagnostic['observation_cache_hit']
    contract=diagnostic.get('scene_contract')
    if isinstance(contract,dict):
        # Only host codes/JSON paths and bounded numeric counts are exposed. No quotes, model bodies,
        # arbitrary issue details or credentials from provider diagnostics.
        issues=[]
        for item in contract.get('issues',[])[:64] if isinstance(contract.get('issues'),list) else []:
            if not isinstance(item,dict):continue
            code=item.get('code');path=item.get('path')
            if not isinstance(code,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{1,80}',code):continue
            row={'code':code}
            if code in {'OBSERVER_INSTANCE_LIMIT_EXCEEDED','OBSERVER_DERIVED_CAPACITY_EXCEEDED'}:
                for key in ('actual_count','maximum','structural_metadata_count'):
                    count=item.get(key)
                    if type(count) is int and 0<=count<=4096:row[key]=count
            if isinstance(path,str) and re.fullmatch(r'\$(?:\.[A-Za-z_][A-Za-z0-9_-]*|\[[0-9]{1,3}\])*',path):row['path']=path[:160]
            targets=item.get('target_ids')
            if isinstance(targets,list):
                row['target_ids']=[v for v in targets[:32] if isinstance(v,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',v)]
            actual=item.get('actual')
            if type(actual) in (int,float) and math.isfinite(actual):row['actual_m']=actual
            expected=item.get('expected')
            if isinstance(expected,dict):
                bounds={k:v for k,v in expected.items() if k in ('min_m','max_m','max_top_m','max_height_m','min_bottom_m')
                    and type(v) in (int,float) and math.isfinite(v)}
                if bounds:row['expected_bounds_m']=bounds
            if isinstance(actual,dict):
                values={k:v for k,v in actual.items() if k in ('height_m','support_top_m','bottom_m')
                    and type(v) in (int,float) and math.isfinite(v)}
                if values:row['geometry_values_m']=values
            violation=item.get('violation_m')
            if type(violation) in (int,float) and math.isfinite(violation):row['violation_m']=violation
            issues.append(row)
        allowed['scene_contract']={'issues':issues,'issue_count':len(issues),
            'issues_truncated':contract.get('issues_truncated') is True,
            'blocked_checks':[v.get('check') if isinstance(v,dict) else v for v in contract.get('blocked_checks',[]) if (v.get('check') if isinstance(v,dict) else v) in
                ('geometry','bounds','overlap','support','packing','photo_relations')][:8]
                if isinstance(contract.get('blocked_checks'),list) else [],'physical_authority':False}
        allowed['scene_contract'].update(public_checks(contract))
        if contract.get('category_validation') in ('TYPED_OBSERVATION','UNVERIFIED_LEGACY_OBSERVATION'):
            allowed['scene_contract']['category_validation']=contract['category_validation']
    if isinstance(diagnostic.get('photo_quality'),dict):
        from twinpulse_core.photo_quality import public_photo_quality
        quality=public_photo_quality(diagnostic['photo_quality'])
        if quality:allowed['photo_quality']=quality
    return allowed


def _safe_name(value: str) -> bool:
    return bool(value and len(value) <= 255 and PurePath(value).name == value and "/" not in value and "\\" not in value)


def _object_summary(item: object, provenance: str) -> dict[str, object]:
    return {
        "id": item.id, "kind": item.kind, "position_m": list(item.transform.position_m),
        "shape": item.shape.type, "dimensions_m": list(item.shape.dimensions_m),
        "rotation_rpy_deg": list(item.transform.rotation_rpy_deg),
        "provenance": provenance,
    }
