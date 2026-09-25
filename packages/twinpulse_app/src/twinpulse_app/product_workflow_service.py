"""Product-facing adapter over the UI-independent ApplicationService."""

from __future__ import annotations

import asyncio
import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePath
import re
from threading import RLock, Thread, current_thread
from typing import TYPE_CHECKING, Callable, Mapping
from uuid import uuid4

from twinpulse_core import COMPACT_2WD_PROFILE_ID, GeneratedDraftRecord
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
from .command_broker import BrokerError, CommandBroker, RegisteredArtifact
from .image_validation import ImageValidationError, decode_image


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_SIDECAR_BYTES = 128 * 1024
INPUT_KINDS = frozenset({"auto", "photo", "drawing"})
WORKFLOW_MODES = frozenset({"live_provider", "explicit_fixture", "replay"})

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
        self._mode = mode
        self._generation_settings_getter = generation_settings_getter
        self._provider_state_getter = provider_state_getter or (lambda: {})
        self._gateway_factory = gateway_factory
        self._profile_id = profile_id
        self._lock = RLock()
        self._input: ProductInput | None = None
        self._phase = "restore_review_required" if (
            application.record is not None or application.restore_error is not None
        ) else "empty"
        self._generation_id: str | None = None
        self._acknowledged_identity: tuple[str, str] | None = None
        self._artifact: RegisteredArtifact | None = None
        if application.restore_error is not None:
            code, message = application.restore_error
            self._error: dict[str, str] | None = {"code": code, "message": message}
        elif application.record is not None:
            self._error = {"code": "restore_review_required", "message": "Stored draft requires current input review"}
        else:
            self._error = None
        self._connected = False
        self._workers: set[Thread] = set()

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
            raise BrokerError("input_empty", "Attach an image or describe the warehouse", status=400)

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
            self._generation_id = None
            self._acknowledged_identity = None
            self._artifact = None
            self._error = None
            self._connected = False
            record = self._application.record
            if record is not None and record.build_allowed_for(prepared.revision):
                self._artifact = self._register(record)
                self._phase = "draft_ready"
            else:
                self._phase = "input_ready"
            return self.snapshot()

    @property
    def current_input(self) -> ProductInput:
        with self._lock:
            if self._input is None:
                raise BrokerError("input_required", "Select the current input first")
            return self._input

    def start_generation(self) -> dict[str, object]:
        with self._lock:
            if self._mode == "replay":
                raise BrokerError("replay_generation_forbidden", "Stored replay cannot perform provider generation")
            if self._input is None:
                raise BrokerError("input_required", "Select the current input before generation")
            if self._phase == "generating" or self._workers:
                raise BrokerError("generation_busy", "A generation job is already running")
            self._phase = "generating"
            self._generation_id = str(uuid4())
            self._acknowledged_identity = None
            self._artifact = None
            self._error = None
            generation_id = self._generation_id
            context = self._application.generation_context()
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
                artifact = self._register(outcome.record)
            except Exception as error:
                with self._lock:
                    if self._generation_id != generation_id or self._phase == "cancelled":
                        return
                    self._phase = "generation_failed"
                    self._error = _public_generation_error(error)
                    self._connected = False
                return
            with self._lock:
                if self._generation_id != generation_id or self._phase != "generating":
                    return
                selected = self._input
                if selected is None or outcome.record.input_revision is None or outcome.record.input_revision.digest != selected.revision:
                    self._phase = "cancelled"
                    self._error = {"code": "superseded_result", "message": "Older generation result was ignored"}
                    return
                self._artifact = artifact
                self._phase = "draft_ready"
                self._connected = self._mode == "live_provider"
                if not outcome.persisted:
                    self._error = {
                        "code": outcome.persistence_error_code or "project_persistence_failed",
                        "message": "Draft is valid in memory but could not be persisted",
                    }
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
        self.cancel()
        with self._lock:
            workers = tuple(self._workers)
        for worker in workers:
            if worker is not current_thread():
                worker.join(max(0.0, timeout_s))

    def provider_settings_changed(self) -> dict[str, object]:
        if self._gateway_factory is None:
            raise BrokerError("provider_gateway_unavailable", "Provider gateway cannot be refreshed", status=503)
        self._application.set_generation_gateway(self._gateway_factory())
        with self._lock:
            self._input = None
            self._artifact = None
            self._generation_id = None
            self._acknowledged_identity = None
            self._phase = "empty"
            self._error = {"code": "input_reselection_required", "message": "Provider settings changed; select input again"}
            self._connected = False
            return self.snapshot()

    def acknowledge(self, revision: str) -> dict[str, object]:
        with self._lock:
            if self._phase != "draft_ready" or self._artifact is None or self._input is None:
                raise BrokerError("draft_revision_stale", "Draft revision is not current")
            if revision != self._artifact.revision:
                raise BrokerError("draft_revision_stale", "Draft revision is not current")
            self._acknowledged_identity = (self._input.revision, revision)
            return self.snapshot()

    def assert_build_allowed(self, artifact_id: object, revision: object) -> None:
        with self._lock:
            identity = None if self._input is None or self._artifact is None else (
                self._input.revision, self._artifact.revision,
            )
            if (
                self._phase != "draft_ready" or self._artifact is None
                or artifact_id != self._artifact.artifact_id or revision != self._artifact.revision
                or self._acknowledged_identity != identity
            ):
                raise BrokerError("draft_acknowledgement_required", "Acknowledge the current input and draft before Build")

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            selected = self._input
            record = self._application.record
            draft = self._draft_summary(record) if (
                record is not None
                and self._phase in {"draft_ready", "restore_review_required"}
                and (self._phase == "restore_review_required" or self._artifact is not None)
            ) else None
            provider = dict(self._provider_state_getter())
            provider.setdefault("configured", False)
            provider.setdefault("label", "Explicit deterministic fixture" if self._mode == "explicit_fixture" else "Provider")
            provider["connected"] = self._connected
            identity = None if selected is None or self._artifact is None else (
                selected.revision, self._artifact.revision,
            )
            return {
                "schema_version": "1.1",
                "mode": self._mode,
                "provider": provider,
                "phase": self._phase,
                "generation_id": self._generation_id,
                "input": None if selected is None else {
                    "revision": selected.revision, "input_kind": selected.input_kind,
                    "prompt_length": len(selected.prompt), "image_name": selected.image_name,
                    "media_type": selected.media_type, "image_sha256": selected.image_sha256,
                    "width": selected.width, "height": selected.height,
                    "sidecar_name": selected.sidecar_name, "sidecar_sha256": selected.sidecar_sha256,
                    "measurement_count": selected.measurement_count,
                },
                "draft": draft,
                "acknowledged_revision": self._acknowledged_identity[1] if self._acknowledged_identity else None,
                "build_allowed": bool(identity is not None and self._acknowledged_identity == identity),
                "error": self._error,
            }

    def _register(self, record: GeneratedDraftRecord) -> RegisteredArtifact:
        if record.validation_receipt is None:
            raise InvalidProviderResponseError("Generated draft has no validation receipt")
        return self._broker.register_artifact(
            f"draft-{record.validation_receipt.bundle_sha256[:24]}", record.bundle,
        )

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


def _public_generation_error(error: Exception) -> dict[str, str]:
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
    code = next((value for kind, value in mappings if isinstance(error, kind)), "generation_failed")
    message = re.sub(r"\s+", " ", str(error)).strip() or "Generation failed"
    return {"code": code, "message": message[:320]}


def _safe_name(value: str) -> bool:
    return bool(value and len(value) <= 255 and PurePath(value).name == value and "/" not in value and "\\" not in value)


def _object_summary(item: object, provenance: str) -> dict[str, object]:
    return {
        "id": item.id, "kind": item.kind, "position_m": list(item.transform.position_m),
        "shape": item.shape.type, "dimensions_m": list(item.shape.dimensions_m),
        "provenance": provenance,
    }
