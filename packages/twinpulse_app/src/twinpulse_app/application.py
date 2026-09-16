"""UI-independent generation, persistence, and simulation-command policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from twinpulse_core import (
    COMPACT_2WD_PROFILE_ID,
    CommandEnvelope,
    CommandReceipt,
    GeneratedDraftRecord,
    GeneratedDraftStore,
    InputArtifactStore,
    InputRevision,
    SimulationPort,
    SpecBundle,
    generation_result_is_current,
)
from twinpulse_provider import GenerationRequest, GenerationResult, ImageInput, MeasurementConstraint

from .project_store import ProjectRecord, ProjectStore


APPLICATION_STATE_VERSION = "1.0"
APPLICATION_PHASES = frozenset({
    "empty", "input_ready", "generating", "draft_ready", "generation_failed", "cancelled",
})


class GenerationGateway(Protocol):
    def cancel_active(self) -> None: ...
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...


@dataclass(frozen=True, slots=True)
class PreparedInput:
    revision: InputRevision
    images: tuple[ImageInput, ...]
    measurement_constraints: tuple[MeasurementConstraint, ...]


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    sequence: int
    kind: str
    phase: str
    code: str
    input_revision: str | None
    draft_revision: str | None
    persisted: bool | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if self.phase not in APPLICATION_PHASES:
            raise ValueError("application phase is unsupported")
        if self.sequence < 0 or not self.kind or not self.code:
            raise ValueError("application event identity is invalid")
        if len(self.message) > 320:
            raise ValueError("application event message is too long")


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    project_id: str
    phase: str
    input_revision: str | None
    persisted_input_revision: str | None
    draft_revision: str | None
    build_allowed: bool
    generation_epoch: int
    event_sequence: int
    schema_version: str = APPLICATION_STATE_VERSION


@dataclass(frozen=True, slots=True)
class GenerationOutcome:
    record: GeneratedDraftRecord
    event: ApplicationEvent
    persisted: bool
    persistence_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class BuildCandidate:
    project_id: str
    input_revision: InputRevision
    record: GeneratedDraftRecord
    bundle: SpecBundle


class ApplicationService:
    """Single-project application state machine shared by every UI."""

    def __init__(
        self,
        generation_gateway: GenerationGateway,
        *,
        project_store: ProjectStore | None = None,
        artifact_store: InputArtifactStore | None = None,
        legacy_draft_store: GeneratedDraftStore | None = None,
        project_id: str = "default",
    ) -> None:
        self._generation_gateway = generation_gateway
        self._project_store = project_store or ProjectStore()
        self._project, self._legacy_imported = self._project_store.load_or_import_legacy(
            legacy_draft_store, project_id=project_id,
        )
        self._artifact_store = artifact_store or InputArtifactStore(self._project_store.path.parent / "inputs")
        self._prepared: PreparedInput | None = None
        self._epoch = 0
        self._sequence = 0
        self._phase = "draft_ready" if self._project.draft is not None else "empty"
        self._last_event = self._event(
            "restored", "legacy_imported" if self._legacy_imported else "project_loaded",
            "Stored project state loaded",
        )

    @property
    def record(self) -> GeneratedDraftRecord | None:
        return self._project.draft

    @property
    def project_id(self) -> str:
        return self._project.project_id

    @property
    def last_event(self) -> ApplicationEvent:
        return self._last_event

    def set_generation_gateway(self, value: GenerationGateway) -> None:
        self._generation_gateway.cancel_active()
        self._generation_gateway = value
        self.invalidate_input("provider_changed")

    @staticmethod
    def prepare_input(
        *,
        prompt: str,
        images: Sequence[ImageInput],
        measurement_constraints: Sequence[MeasurementConstraint],
        generation_settings: Mapping[str, str],
        input_kind: str | None = None,
        profile_id: str = COMPACT_2WD_PROFILE_ID,
    ) -> PreparedInput:
        image_tuple = tuple(images)
        constraints = tuple(measurement_constraints)
        revision = InputRevision.create(
            prompt=prompt,
            images=tuple((image.name, image.content) for image in image_tuple),
            measurement_constraints=constraints,
            profile_id=profile_id,
            generation_settings=generation_settings,
            input_kind=input_kind,
        )
        return PreparedInput(revision, image_tuple, constraints)

    def select_input(self, value: PreparedInput) -> ApplicationEvent:
        self._generation_gateway.cancel_active()
        self._epoch += 1
        self._prepared = value
        self._phase = "input_ready"
        self._project = ProjectRecord(
            self._project.project_id, latest_input=value.revision,
            draft=self._project.draft,
        )
        self._project_store.save(self._project)
        self._last_event = self._event("input", "input_selected", "Input revision selected")
        return self._last_event

    def invalidate_input(self, code: str = "input_changed") -> ApplicationEvent:
        self._generation_gateway.cancel_active()
        self._epoch += 1
        self._prepared = None
        self._phase = "cancelled" if code == "cancelled" else "input_ready"
        self._last_event = self._event("input", code, "Current input selection invalidated")
        return self._last_event

    def cancel_generation(self) -> ApplicationEvent:
        return self.invalidate_input("cancelled")

    async def generate(self) -> GenerationOutcome:
        prepared = self._prepared
        if prepared is None:
            raise RuntimeError("No current input revision is selected")
        if not prepared.revision.prompt and not prepared.images:
            raise ValueError("Attach an image or describe the warehouse before generating")
        self._artifact_store.save(
            prepared.revision,
            tuple((image.name, image.content) for image in prepared.images),
        )
        ticket = self._epoch
        request_id = str(uuid4())
        self._phase = "generating"
        self._last_event = self._event("generation", "generation_started", "Generation started")
        try:
            result = await self._generation_gateway.generate(GenerationRequest(
                request_id=request_id,
                prompt=prepared.revision.prompt,
                images=prepared.images,
                image_detail=prepared.revision.generation_settings.get("image_detail", "auto"),
                measurement_constraints=prepared.measurement_constraints,
            ))
            current_digest = self._prepared.revision.digest if self._prepared is not None else ""
            if not generation_result_is_current(
                ticket=ticket, current_ticket=self._epoch,
                requested_input_digest=prepared.revision.digest,
                current_input_digest=current_digest,
            ):
                self._phase = "cancelled"
                self._last_event = self._event(
                    "generation", "superseded_result", "Superseded generation result ignored",
                )
                raise ValueError("Generation result belongs to a superseded input")
            record = GeneratedDraftRecord.create(
                request_id=result.request_id,
                provider_name=result.provider_name,
                model_id=result.model_id,
                image_count=result.image_count,
                plan=result.plan,
                input_revision=prepared.revision,
            )
            candidate = ProjectRecord(self._project.project_id, prepared.revision, record)
            persisted = True
            persistence_error_code = None
            try:
                self._project_store.save(candidate)
            except OSError:
                persisted = False
                persistence_error_code = "project_persistence_failed"
            self._project = candidate
            self._phase = "draft_ready"
            self._last_event = self._event(
                "generation", "draft_ready" if persisted else "draft_ready_unpersisted",
                "Validated draft is ready", persisted=persisted,
            )
            return GenerationOutcome(record, self._last_event, persisted, persistence_error_code)
        except Exception:
            if self._phase not in {"cancelled", "draft_ready"}:
                self._phase = "generation_failed"
                self._last_event = self._event(
                    "generation", "generation_failed", "Generation failed; previous draft retained",
                )
            raise

    def set_draft(self, record: GeneratedDraftRecord, *, persist: bool = False) -> ApplicationEvent:
        """Compatibility hook for existing validated records and tests."""
        checked = GeneratedDraftRecord.from_dict(record.to_dict())
        self._project = ProjectRecord(
            self._project.project_id,
            latest_input=checked.input_revision or self._project.latest_input,
            draft=checked,
        )
        if persist:
            self._project_store.save(self._project)
        self._phase = "draft_ready"
        self._last_event = self._event("draft", "draft_selected", "Validated draft selected", persisted=persist)
        return self._last_event

    def build_candidate(self, revision: InputRevision) -> BuildCandidate:
        record = self._project.draft
        if record is None:
            raise RuntimeError("No validated generated tool plan is available")
        if not record.build_allowed_for(revision):
            raise RuntimeError("Input revision does not match the validated draft")
        return BuildCandidate(self._project.project_id, revision, record, record.bundle)

    def snapshot(self, revision: InputRevision | None = None) -> ApplicationSnapshot:
        record = self._project.draft
        selected = revision or (self._prepared.revision if self._prepared is not None else None)
        allowed = bool(record is not None and selected is not None and record.build_allowed_for(selected))
        return ApplicationSnapshot(
            project_id=self._project.project_id,
            phase=self._phase,
            input_revision=selected.digest if selected is not None else None,
            persisted_input_revision=(
                self._project.latest_input.digest if self._project.latest_input is not None else None
            ),
            draft_revision=(record.validation_receipt.bundle_sha256 if record and record.validation_receipt else None),
            build_allowed=allowed,
            generation_epoch=self._epoch,
            event_sequence=self._sequence,
        )

    def dispatch(
        self,
        port: SimulationPort,
        command_type: str,
        *,
        engine_session_id: str,
        stage_epoch: str,
        control_lease_id: str,
        current_input: InputRevision | None = None,
        expected_applied_revision: str | None = None,
        ttl_s: float = 30.0,
    ) -> CommandReceipt:
        payload: dict[str, Any] = {}
        expected = expected_applied_revision
        if command_type == "build_scene":
            if current_input is None:
                raise RuntimeError("Build requires the current input revision")
            candidate = self.build_candidate(current_input)
            expected = current_input.digest
            payload = {
                "draft": candidate.record.to_dict(),
                "bundle": candidate.bundle.to_dict(),
            }
        command = CommandEnvelope(
            command_id=str(uuid4()), command_type=command_type,
            project_id=self._project.project_id, engine_session_id=engine_session_id,
            stage_epoch=stage_epoch, control_lease_id=control_lease_id,
            expected_applied_revision=expected, payload=payload, ttl_s=ttl_s,
        )
        receipt = CommandReceipt.from_dict(port.execute(command).to_dict())
        if (
            receipt.command_id != command.command_id
            or receipt.command_type != command.command_type
            or receipt.project_id != command.project_id
            or receipt.engine_session_id != command.engine_session_id
        ):
            raise RuntimeError("Engine receipt identity does not match the command")
        if command_type == "build_scene" and receipt.status == "succeeded" and receipt.applied_revision != expected:
            raise RuntimeError("Engine build receipt does not match the requested revision")
        return receipt

    def _event(
        self, kind: str, code: str, message: str, *, persisted: bool | None = None,
    ) -> ApplicationEvent:
        self._sequence += 1
        record = self._project.draft
        selected = self._prepared.revision if self._prepared is not None else None
        return ApplicationEvent(
            sequence=self._sequence, kind=kind, phase=self._phase, code=code,
            input_revision=selected.digest if selected is not None else None,
            draft_revision=(record.validation_receipt.bundle_sha256 if record and record.validation_receipt else None),
            persisted=persisted, message=message,
        )
