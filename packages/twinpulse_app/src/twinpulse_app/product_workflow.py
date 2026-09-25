"""R5 product-facing input, draft review, and acknowledgement state."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePath
from threading import RLock, Thread
import time
from typing import Mapping
from uuid import uuid4

from .command_broker import BrokerError, RegisteredArtifact
from .image_validation import ImageValidationError, decode_image
from twinpulse_provider import MeasurementConstraintError, parse_measurement_constraints
from twinpulse_provider import MeasurementConstraint


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_SIDECAR_BYTES = 128 * 1024
INPUT_KINDS = frozenset({"auto", "photo", "drawing"})


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


class ProductWorkflow:
    """Single-project R5 workflow using an explicit deterministic fixture mode."""

    def __init__(self, artifact: RegisteredArtifact, *, generation_delay_s: float = 0.15) -> None:
        self._artifact = artifact
        self._lock = RLock()
        self._input: ProductInput | None = None
        self._phase = "empty"
        self._generation_id: str | None = None
        self._acknowledged_revision: str | None = None
        self._generation_delay_s = generation_delay_s

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
        measurement_count = 0
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
            detected_type, width, height = decoded.media_type, decoded.width, decoded.height
            if detected_type != media_type:
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
            measurement_count = len(measurements)
        if not prompt.strip() and image_bytes is None:
            raise BrokerError("input_empty", "Attach an image or describe the warehouse", status=400)
        sidecar_sha256 = hashlib.sha256(sidecar_bytes).hexdigest() if sidecar_bytes is not None else None
        identity = {
            "input_kind": str(input_kind),
            "prompt": prompt,
            "image": None if image_bytes is None else {
                "name": name,
                "media_type": media_type,
                "sha256": image_sha256,
                "dimensions_px": [width, height],
            },
            "sidecar": None if sidecar_bytes is None else {
                "name": sidecar_name,
                "sha256": sidecar_sha256,
                "constraints": [item.to_dict() for item in measurements],
            },
        }
        digest = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        selected = ProductInput(
            revision=digest.hexdigest(), prompt=prompt, input_kind=str(input_kind),
            image_name=name if isinstance(name, str) else None,
            media_type=media_type if isinstance(media_type, str) else None,
            image_bytes=image_bytes, image_sha256=image_sha256, width=width, height=height,
            image_dimensions_px=(width, height) if width is not None and height is not None else None,
            sidecar_name=sidecar_name if isinstance(sidecar_name, str) else None,
            sidecar_sha256=sidecar_sha256,
            measurement_constraints=measurements,
            measurement_count=measurement_count,
        )
        with self._lock:
            self._input = selected
            self._phase = "input_ready"
            self._generation_id = None
            self._acknowledged_revision = None
            return self.snapshot()

    @property
    def current_input(self) -> ProductInput:
        with self._lock:
            if self._input is None:
                raise BrokerError("input_required", "Select the current input first")
            return self._input

    def start_fixture_generation(self) -> dict[str, object]:
        with self._lock:
            if self._input is None:
                raise BrokerError("input_required", "Select the current input before generation")
            if self._phase == "generating":
                raise BrokerError("generation_busy", "A generation job is already running")
            self._phase = "generating"
            self._generation_id = str(uuid4())
            self._acknowledged_revision = None
            generation_id = self._generation_id
            snapshot = self.snapshot()
        Thread(
            target=self._complete_generation,
            args=(generation_id,),
            name="TwinPulseFixtureGeneration",
            daemon=True,
        ).start()
        return snapshot

    def _complete_generation(self, generation_id: str) -> None:
        time.sleep(self._generation_delay_s)
        with self._lock:
            if self._generation_id == generation_id and self._phase == "generating":
                self._phase = "draft_ready"

    def cancel(self) -> dict[str, object]:
        with self._lock:
            if self._phase == "generating":
                self._phase = "cancelled"
            return self.snapshot()

    def acknowledge(self, revision: str) -> dict[str, object]:
        with self._lock:
            if self._phase != "draft_ready" or revision != self._artifact.revision:
                raise BrokerError("draft_revision_stale", "Draft revision is not current")
            self._acknowledged_revision = revision
            return self.snapshot()

    def assert_build_allowed(self, artifact_id: object, revision: object) -> None:
        with self._lock:
            if (
                self._phase != "draft_ready"
                or artifact_id != self._artifact.artifact_id
                or revision != self._artifact.revision
                or self._acknowledged_revision != self._artifact.revision
            ):
                raise BrokerError(
                    "draft_acknowledgement_required",
                    "Acknowledge the current approximate draft before Build",
                )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            selected = self._input
            draft = self._draft_summary() if self._phase == "draft_ready" else None
            return {
                "schema_version": "1.0",
                "mode": "deterministic_fixture",
                "provider": {
                    "configured": False,
                    "connected": False,
                    "label": "Deterministic local fixture; live provider not invoked",
                },
                "phase": self._phase,
                "generation_id": self._generation_id,
                "input": None if selected is None else {
                    "revision": selected.revision,
                    "input_kind": selected.input_kind,
                    "prompt_length": len(selected.prompt),
                    "image_name": selected.image_name,
                    "media_type": selected.media_type,
                    "image_sha256": selected.image_sha256,
                    "width": selected.width,
                    "height": selected.height,
                    "sidecar_name": selected.sidecar_name,
                    "sidecar_sha256": selected.sidecar_sha256,
                    "measurement_count": selected.measurement_count,
                },
                "draft": draft,
                "acknowledged_revision": self._acknowledged_revision,
                "build_allowed": bool(
                    draft is not None and self._acknowledged_revision == self._artifact.revision
                ),
                "error": None,
            }

    def _draft_summary(self) -> dict[str, object]:
        bundle = self._artifact.bundle
        objects = [_object_summary(item) for item in bundle.scene.objects]
        return {
            "artifact_id": self._artifact.artifact_id,
            "revision": self._artifact.revision,
            "scene_id": bundle.scene.id,
            "robot_profile_id": bundle.robot.id,
            "task_id": bundle.task.id,
            "object_count": len(objects),
            "tool_count": len(objects) + 2,
            "objects": objects,
            "source": "deterministic_fixture",
            "approximate": True,
        }


def _safe_name(value: str) -> bool:
    return bool(
        value and len(value) <= 255 and PurePath(value).name == value
        and "/" not in value and "\\" not in value
    )


def _object_summary(item: object) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind,
        "position_m": list(item.transform.position_m),
        "shape": item.shape.type,
        "dimensions_m": list(item.shape.dimensions_m),
        "provenance": "fixture",
    }


# Compatibility import for callers that used the original module path.  The
# production implementation lives in product_workflow_service and owns no
# generation state itself; ApplicationService remains the single owner.
from .product_workflow_service import ProductWorkflow as ProductWorkflow  # noqa: E402,F811
