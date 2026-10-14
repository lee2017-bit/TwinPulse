# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""UI-independent generation, persistence, and simulation-command policy."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import RLock
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
    SCENE_TOOL_CATALOG_REVISION,
    SpecBundle,
    generation_result_is_current,
)
from twinpulse_provider import GenerationRequest, GenerationResult, SiteGenerationResult, ImageInput, MeasurementConstraint, ProviderConfigurationError

from .project_store import ProjectRecord, ProjectStore
from .site_draft import SiteDraftRecord
from .robot_reports import RobotReports
from .scan_review import ScanReview
from .native_scan_review import NativeScanReview
from .derived_site_review import DerivedSiteReview, DerivedReviewStore
from twinpulse_core.execution_diagnostics import ExecutionStore, profile_call


APPLICATION_STATE_VERSION = "1.0"
APPLICATION_PHASES = frozenset({
    "empty", "input_ready", "generating", "draft_ready", "generation_failed", "cancelled",
})


class GenerationGateway(Protocol):
    def cancel_active(self) -> None: ...
    async def generate(self, request: GenerationRequest) -> GenerationResult | SiteGenerationResult: ...


@dataclass(frozen=True, slots=True)
class PreparedInput:
    revision: InputRevision
    images: tuple[ImageInput, ...]
    measurement_constraints: tuple[MeasurementConstraint, ...]


@dataclass(frozen=True, slots=True)
class GenerationContext:
    prepared: PreparedInput
    epoch: int
    diagnostics: Any = field(default=None, repr=False, compare=False)
    inference_scope: Any = field(default=None, repr=False, compare=False)
    continuation_checkpoint: str | None = None
    render_review_port: Any = field(default=None, repr=False, compare=False)


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
    record: GeneratedDraftRecord | SiteDraftRecord
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
        allow_invalid_restore: bool = False,
        profile_generation: bool = False,
        launch_execution_id: str | None = None,
        launch_id: str | None = None,
    ) -> None:
        self._generation_gateway = generation_gateway
        self.robot_reports = RobotReports()
        self.scan_review = ScanReview()
        self.native_scan_review = NativeScanReview()
        self._project_store = project_store or ProjectStore()
        self.diagnostics = ExecutionStore(self._project_store.path.parent / 'diagnostics', project_id,
            default_refs={'launch_execution_id':launch_execution_id,'launch_id':launch_id})
        self.last_execution_id = None
        self._profile_generation = profile_generation
        self._derived_store = DerivedReviewStore(self._project_store.path.with_suffix(".derived-review.json"))
        self._derived_lock = RLock()
        self._derived_selection = None
        self._restore_error_code: str | None = None
        self._restore_error_message: str | None = None
        self._restore_blocked = False
        try:
            self._project, self._legacy_imported = self._project_store.load_or_import_legacy(
                legacy_draft_store, project_id=project_id,
            )
        except (OSError, UnicodeError, ValueError) as error:
            if not allow_invalid_restore:
                raise
            self._project = ProjectRecord(project_id=project_id)
            self._legacy_imported = False
            self._restore_error_code = "project_restore_invalid"
            self._restore_error_message = "Stored project could not be validated; select the current input again"
            self._restore_blocked = project_id != "default"
            if self._restore_blocked:
                self._restore_error_message = "Saved project or room asset is invalid; repair its source before reopening"
        self._artifact_store = artifact_store or InputArtifactStore(self._project_store.input_root())
        self._prepared: PreparedInput | None = None
        self._epoch = 0
        self._sequence = 0
        self._phase = "draft_ready" if self._project.draft is not None or self._project.site_draft is not None else "empty"
        self._last_event = self._event(
            "restored",
            self._restore_error_code or ("legacy_imported" if self._legacy_imported else "project_loaded"),
            self._restore_error_message or "Stored project state loaded",
        )

    @property
    def record(self) -> GeneratedDraftRecord | None:
        return self._project.draft

    @property
    def site_draft(self) -> SiteDraftRecord | None:
        return self._project.site_draft

    def scene_change_store(self):
        """The one project-local edit sidecar, bound to the immutable v2 draft."""
        if self._restore_blocked or self._project.site_draft is None:
            raise ValueError("saved v2 site draft is required for editing")
        self._project_store._check_location()
        from .scene_changes import SceneChangeStore
        return SceneChangeStore(
            self._project_store.path.with_suffix(".scene-changes.json"),
            project_id=self._project.project_id,
            source=self._project.site_draft,
            project_store=self._project_store,
        )

    def presentation_store(self):
        """Project-local view settings, separate from immutable scene geometry."""
        if self._restore_blocked or self._project.site_draft is None:
            raise ValueError("saved v2 site draft is required for presentation")
        from .presentation_store import PresentationStore
        return PresentationStore(self._project_store)

    def clear_derived_review(self) -> None:
        # No disk deletion: retained evidence never carries selection/approval.
        self._derived_selection = None

    @property
    def derived_review(self) -> DerivedSiteReview | None:
        selected = self._derived_selection
        if selected is None:
            return None
        epoch, record = selected
        if (epoch != self._epoch or self._prepared is None
                or self._phase not in {"input_ready", "draft_ready"}
                or self._prepared.revision.digest != record.source.input_revision.digest
                or self.site_draft != record.source):
            return None
        return record

    def adopt_derived_review(self, input_revision: str, source_revision: str,
                             workspace_revision: str | None, *, restore: bool = False) -> DerivedSiteReview:
        """Explicit selection only; no build/acknowledgement and no original mutation.

        A concurrent input/generation change can leave a valid archive on disk,
        but cannot make that archive an eligible selection. Recheck on every use.
        Restoring requires an explicit call and revalidates source and all edits.
        """
        with self._derived_lock:
            self.clear_derived_review()
            source = self.site_draft
            epoch = self._epoch
            def current():
                return (source is not None and self.site_draft == source and self._epoch == epoch
                        and self._phase in {"input_ready", "draft_ready"} and self._prepared is not None
                        and self._prepared.revision.digest == input_revision == source.input_revision.digest
                        and source.site.scene.revision == source_revision)
            if not current():
                raise ValueError("derived review requires the current input and original site draft")
            if restore:
                record = self._derived_store.load()
                if record is None or record.source != source:
                    raise ValueError("no saved derived review for the current original draft")
            else:
                text = self.scan_review.download_archive(workspace_revision)["archive_text"]
                record = DerivedSiteReview.create(source, text)
                if not current() or self.scan_review.snapshot()["workspace_revision"] != workspace_revision:
                    raise ValueError("input or scan workspace changed during derived review")
                self._derived_store.save(record)
            if not current() or (not restore and self.scan_review.snapshot()["workspace_revision"] != workspace_revision):
                raise ValueError("input or scan workspace changed while storing derived review")
            self._derived_selection = (epoch, record)
            if self.derived_review is None:
                raise ValueError("derived selection was superseded")
            return record

    @property
    def project_id(self) -> str:
        return self._project.project_id

    @property
    def restore_error(self) -> tuple[str, str] | None:
        if self._restore_error_code is None or self._restore_error_message is None:
            return None
        return self._restore_error_code, self._restore_error_message

    @property
    def last_event(self) -> ApplicationEvent:
        return self._last_event

    def set_generation_gateway(self, value: GenerationGateway) -> None:
        self._generation_gateway.cancel_active()
        self._generation_gateway = value
        self.invalidate_input("provider_changed")

    def generation_diagnostics(self):
        return getattr(self._generation_gateway, 'diagnostic_snapshot', lambda: {})()

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
        settings = dict(generation_settings)
        settings.setdefault("tool_catalog_revision", SCENE_TOOL_CATALOG_REVISION)
        revision = InputRevision.create(
            prompt=prompt,
            images=tuple((image.name, image.mime_type, image.content) for image in image_tuple),
            measurement_constraints=constraints,
            profile_id=profile_id,
            generation_settings=settings,
            input_kind=input_kind,
        )
        return PreparedInput(revision, image_tuple, constraints)

    def restored_room_input(self) -> PreparedInput:
        """Read the current named photo recipe again; do not restore approval or Build authority."""
        from .room_recipe import load_project_room_recipe
        if self._project.site_draft is None or self._project.project_id == "default":
            raise ValueError("no named room recipe is stored")
        draft, photo = load_project_room_recipe(
            self._project_store.path.parent.parent.parent, self._project.project_id)
        if draft != self._project.site_draft:
            raise ValueError("stored room recipe changed")
        reference = draft.input_revision.images[0]
        return PreparedInput(draft.input_revision,
                             (ImageInput(reference["name"], reference["mime_type"], photo),), ())

    def restored_saved_input(self) -> PreparedInput:
        """Validate a saved scene's original input, never the current provider settings."""
        draft = self._project.site_draft or self._project.draft
        if draft is None or draft.input_revision is None or self._restore_blocked:
            raise ValueError("no valid saved scene is available")
        if isinstance(draft, SiteDraftRecord) and draft.provider_name == "local-room-recipe":
            return self.restored_room_input()
        revision, archived_images = self._artifact_store.load(draft.input_revision)
        from twinpulse_provider import MeasurementConstraint
        constraints = tuple(MeasurementConstraint.from_dict(item) for item in revision.measurement_constraints)
        return PreparedInput(revision,
                             tuple(ImageInput(name, mime, content) for name, mime, content in archived_images),
                             constraints)

    def adopt_saved_review(self, prepared: PreparedInput, scene_revision: str) -> None:
        """Select validated bytes in memory only; preserve the persisted latest input."""
        draft = self._project.site_draft or self._project.draft
        if self._restore_blocked or draft is None or draft.input_revision is None:
            raise ValueError("saved scene is unavailable")
        actual = (draft.site.scene.revision if isinstance(draft, SiteDraftRecord) else
                  draft.validation_receipt.bundle_sha256 if draft.validation_receipt is not None else draft.plan_sha256)
        if actual != scene_revision or draft.input_revision != prepared.revision:
            raise ValueError("saved scene changed during review")
        self.clear_derived_review()
        self._epoch += 1
        self._prepared = prepared
        self._phase = "draft_ready"
        self._last_event = self._event("restored", "saved_review_selected", "Saved scene opened for review")

    def reattach_saved_source(self, name: str | None, mime: str | None, content: bytes | None) -> None:
        """Fill only a missing immutable archive with bytes matching the saved revision."""
        draft = self._project.site_draft or self._project.draft
        if draft is None or draft.input_revision is None or self._restore_blocked:
            raise ValueError("saved scene is unavailable")
        if isinstance(draft, SiteDraftRecord) and draft.provider_name == "local-room-recipe":
            raise ValueError("room recipe source must be repaired in its own project")
        revision = draft.input_revision
        try:
            self._artifact_store.load(revision)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("original archive is already present")
        if revision.images:
            ref = revision.images[0]
            if name != ref["name"] or mime != ref.get("mime_type") or content is None:
                raise ValueError("reattached image identity does not match the saved scene")
            images = ((name, content),)
        elif name is None and mime is None and content is None:
            images = ()
        else:
            raise ValueError("saved scene is text-only")
        self._artifact_store.save(revision, images)
        self._artifact_store.load(revision)

    def room_visual_descriptor(self, draft: SiteDraftRecord) -> dict[str, str] | None:
        """Bind an optional named-project visual to exactly its saved recipe draft."""
        if self._project.project_id == "default" or draft.provider_name != "local-room-recipe":
            return None
        from .room_recipe import load_project_room_visual
        result = load_project_room_visual(
            self._project_store.path.parent.parent.parent, self._project.project_id, draft)
        if result is None:
            return None
        manifest, _ = result
        return {"kind": "project_room_visual_v1", "manifest_sha256": manifest["manifest_sha256"]}

    def select_input(self, value: PreparedInput) -> ApplicationEvent:
        if self._restore_blocked:
            raise ValueError("stored project is invalid and cannot be overwritten")
        # Cancel older work before IO, including a failed save: restoring an
        # earlier epoch could allow an old provider result to commit afterward.
        self.clear_derived_review()
        self._generation_gateway.cancel_active()
        self._epoch += 1
        candidate = ProjectRecord(self._project.project_id, latest_input=value.revision,
            draft=self._project.draft, site_draft=self._project.site_draft)
        try:
            self._project_store.save(candidate)
        except OSError as error:
            trace=self.diagnostics.begin('input_selection',input_revision=value.revision.digest)
            self.last_execution_id=trace.execution_id
            trace.child('input_project_save').finish('failed',error=error,error_code='input_persistence_failed')
            trace.finish('failed',error_code='input_persistence_failed')
            # Preserve the previous selected input and draft, not the epoch.
            # Failed persistence must not silently replace the in-memory project.
            raise
        self._prepared = value
        self._restore_error_code = None
        self._restore_error_message = None
        self._phase = "input_ready"
        self._project = candidate
        self._last_event = self._event("input", "input_selected", "Input revision selected")
        return self._last_event

    def invalidate_input(self, code: str = "input_changed") -> ApplicationEvent:
        self.clear_derived_review()
        self._generation_gateway.cancel_active()
        self._epoch += 1
        self._prepared = None
        self._phase = "cancelled" if code == "cancelled" else "input_ready"
        self._last_event = self._event("input", code, "Current input selection invalidated")
        return self._last_event

    def cancel_generation(self) -> ApplicationEvent:
        return self.invalidate_input("cancelled")

    def generation_context(self) -> GenerationContext:
        prepared = self._prepared
        if prepared is None:
            raise RuntimeError("No current input revision is selected")
        return GenerationContext(prepared, self._epoch)

    async def generate(self, context: GenerationContext | None = None) -> GenerationOutcome:
        selected = context or self.generation_context()
        owned = selected.diagnostics is None
        trace = selected.diagnostics or self.diagnostics.begin('scene_generation',
            input_revision=selected.prepared.revision.digest,
            input_kind='photo' if selected.prepared.images else 'text')
        self.last_execution_id = trace.execution_id
        try:
            with trace.span('application_generation') as child:
                outcome = await self._generate(replace(selected, diagnostics=child))
            if owned:
                trace.finish('succeeded' if outcome.persisted else 'failed',
                             persisted=outcome.persisted, error_code=outcome.persistence_error_code)
            return outcome
        except BaseException as error:
            if owned:
                trace.finish('cancelled' if self._phase == 'cancelled' else 'failed', error=error)
            raise

    async def _generate(self, selected_context: GenerationContext) -> GenerationOutcome:
        self.clear_derived_review()
        prepared = selected_context.prepared
        trace = selected_context.diagnostics
        if not prepared.revision.prompt and not prepared.images:
            raise ValueError("Attach a site image or describe the scene before creating a draft")
        with trace.span('input_archive'):
            self._artifact_store.save(prepared.revision,
                tuple((image.name, image.content) for image in prepared.images))
        ticket = selected_context.epoch
        request_id = str(uuid4())
        trace.bind(request_id=request_id)
        self._phase = "generating"
        self._last_event = self._event("generation", "generation_started", "Generation started")
        try:
            with trace.span('provider_generation', request_id=request_id) as provider_trace:
                result = await self._generation_gateway.generate(GenerationRequest(
                    request_id=request_id,
                    prompt=prepared.revision.prompt,
                    images=prepared.images,
                    image_detail=prepared.revision.generation_settings.get("image_detail", "auto"),
                    measurement_constraints=prepared.measurement_constraints,
                    diagnostics=provider_trace,
                    inference_scope=selected_context.inference_scope,
                    continuation_checkpoint=selected_context.continuation_checkpoint,
                    render_review_port=selected_context.render_review_port,
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
            if result.request_id != request_id:
                raise ValueError("Generation response request identity mismatch")
            if isinstance(result, SiteGenerationResult):
                from twinpulse_core.photo_placement import placement_contract_from_trace
                record: GeneratedDraftRecord | SiteDraftRecord = profile_call(trace, 'site_validation_compile',
                    SiteDraftRecord.create, enabled=self._profile_generation,
                    request_id=result.request_id, provider_name=result.provider_name,
                    model_id=result.model_id, image_count=result.image_count,
                    input_revision=prepared.revision, plan=result.plan,
                    placement_contract=placement_contract_from_trace(
                        result.provider_provenance.get('photo_layout_compiler', result.provider_provenance)),
                    progressive_twin=result.provider_provenance.get('progressive_twin'),
                    draft_refinement=result.provider_provenance.get('draft_refinement'),
                )
                candidate = ProjectRecord(self._project.project_id, prepared.revision,
                                          draft=None, site_draft=record)
                review = result.provider_provenance.get('quality_review') or {}
                if review.get('render_comparison') == 'reviewed':
                    capture = review.get('capture') or {}
                    if (selected_context.render_review_port is None
                            or capture.get('plan_sha256') != record.plan_sha256
                            or capture.get('scene_revision') != record.site.scene.revision):
                        raise ProviderConfigurationError('RENDER_REVIEW_FINAL_DRAFT_MISMATCH')
                    selected_context.render_review_port.assert_current(capture)
            else:
                record = profile_call(trace, 'scene_validation_compile', GeneratedDraftRecord.create,
                    enabled=self._profile_generation,
                    request_id=result.request_id,
                    provider_name=result.provider_name,
                    model_id=result.model_id,
                    image_count=result.image_count,
                    plan=result.plan,
                    input_revision=prepared.revision,
                    provider_provenance=result.provider_provenance,
                )
                candidate = ProjectRecord(self._project.project_id, prepared.revision, draft=record)
            persisted = True
            persistence_error_code = None
            try:
                with trace.span('project_save'):
                    self._project_store.save(candidate)
            except OSError:
                persisted = False
                persistence_error_code = "project_persistence_failed"
            trace.bind(request_id=result.request_id, provider_name=result.provider_name,
                       model_id=result.model_id, draft_revision=(record.site.scene.revision if isinstance(record, SiteDraftRecord)
                           else record.validation_receipt.bundle_sha256))
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
        self.clear_derived_review()
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
        if command_type == "run" and self._project.site_draft is not None:
            raise RuntimeError("Site plan 2.0 is review-only; Run is unavailable")
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
