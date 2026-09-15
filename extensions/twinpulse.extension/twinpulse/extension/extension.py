"""TwinPulse Extension lifecycle and Copilot-inspired playground interface."""

from __future__ import annotations

import asyncio
import gc
import mimetypes
import os
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import omni.ext
import omni.kit.app
import omni.ui as ui
from omni.kit.window.filepicker import FilePickerDialog

from .core_bootstrap import add_core_to_path

add_core_to_path()

from twinpulse_core import GeneratedDraftRecord, GeneratedDraftStore  # noqa: E402

from twinpulse_provider import (  # noqa: E402
    GenerationRequest,
    GenerationService,
    ImageInput,
    load_measurement_constraints,
    MeasurementConstraint,
    MeasurementConstraintError,
    measurement_sidecar_path,
    OpenAIResponsesProvider,
    ProviderCapabilities,
    ProviderConfig,
)

from .credential_store import WindowsCredentialStore  # noqa: E402
from .provider_settings import ProviderSettings, load_provider_settings, save_provider_settings  # noqa: E402
from .runtime import TwinPulseRuntime  # noqa: E402


_INSTANCE: "TwinPulseExtension | None" = None
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

COLORS = {
    "panel": 0xFF181818,
    "card": 0xFF252526,
    "card_alt": 0xFF202020,
    "field": 0xFF151515,
    "border": 0xFF3C3C3C,
    "accent": 0xFFFF8B5C,
    "accent_hover": 0xFFFFA477,
    "accent_pressed": 0xFFDB7348,
    "green": 0xFF8DD06C,
    "amber": 0xFF5CC7F2,
    "text": 0xFFF0F0F0,
    "muted": 0xFFA9A9A9,
    "subtle": 0xFF747474,
}

STYLE = {
    "Label": {"color": COLORS["text"], "font_size": 14},
    "Label::brand": {"color": COLORS["text"], "font_size": 24},
    "Label::eyebrow": {"color": COLORS["accent"], "font_size": 12},
    "Label::muted": {"color": COLORS["muted"], "font_size": 13},
    "Label::section": {"color": COLORS["text"], "font_size": 15},
    "Label::caption": {"color": COLORS["subtle"], "font_size": 12},
    "Label::success": {"color": COLORS["green"], "font_size": 13},
    "Label::warning": {"color": COLORS["amber"], "font_size": 13},
    "Label::stage_active": {"color": COLORS["text"], "font_size": 12},
    "Label::stage_idle": {"color": COLORS["subtle"], "font_size": 12},
    "StringField": {
        "background_color": COLORS["field"],
        "border_color": COLORS["border"],
        "border_width": 1,
        "border_radius": 7,
        "color": COLORS["text"],
        "padding": 10,
        "font_size": 14,
    },
    "Button": {
        "background_color": 0xFF303030,
        "border_radius": 6,
        "color": COLORS["text"],
        "font_size": 13,
        "padding": 7,
    },
    "Button:hovered": {"background_color": 0xFF3B3B3B},
    "Button:pressed": {"background_color": 0xFF454545},
    "Button::primary": {"background_color": COLORS["accent"], "border_radius": 7, "color": 0xFFFFFFFF},
    "Button::primary:hovered": {"background_color": COLORS["accent_hover"]},
    "Button::primary:pressed": {"background_color": COLORS["accent_pressed"]},
    "Button::ghost": {
        "background_color": COLORS["card_alt"],
        "border_color": COLORS["border"],
        "border_width": 1,
        "border_radius": 6,
    },
    "Button::ghost:hovered": {"background_color": 0xFF313131},
    "Button::disabled": {"background_color": COLORS["card_alt"], "color": COLORS["subtle"]},
    "ScrollingFrame": {"background_color": COLORS["panel"]},
}


def get_extension() -> "TwinPulseExtension | None":
    return _INSTANCE


class TwinPulseExtension(omni.ext.IExt):
    """Dockable playground with multimodal generation and safe simulation controls."""

    def on_startup(self, ext_id: str) -> None:
        global _INSTANCE
        self.ext_id = ext_id
        self.runtime = TwinPulseRuntime(self._set_status)
        self._status_label: ui.Label | None = None
        self._generation_status_label: ui.Label | None = None
        self._generate_button: ui.Button | None = None
        self._build_button: ui.Button | None = None
        self._draft_label: ui.Label | None = None
        self._provider_label: ui.Label | None = None
        self._provider_detail_label: ui.Label | None = None
        self._image_frame: ui.Frame | None = None
        self._image_path: Path | None = None
        self._measurement_constraints: tuple[MeasurementConstraint, ...] = ()
        self._measurement_sidecar_path: Path | None = None
        self._filepicker: FilePickerDialog | None = None
        self._settings_window: ui.Window | None = None
        self._warning_window: ui.Window | None = None
        self._warned_approximation = False
        self._generated_bundle = None
        self._generated_record: GeneratedDraftRecord | None = None
        self._draft_store = GeneratedDraftStore()
        self._credential_store = WindowsCredentialStore()
        self._provider_settings = load_provider_settings()
        self._prompt_model = ui.SimpleStringModel("")
        self._tasks: set[asyncio.Task] = set()
        self._busy = False
        self._provider_verified = False
        self._configure_provider()
        self._window = ui.Window("TwinPulse Copilot", width=480, height=760, visible=True)
        self._window.frame.style = STYLE
        with self._window.frame:
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                style=STYLE,
            ):
                with ui.VStack(spacing=10, height=ui.Pixel(830), style={"margin": 12}):
                    self._build_header()
                    self._build_stage_indicator()
                    self._build_prompt_card()
                    self._build_draft_card()
                    self._build_simulation_card()
                    self._build_status_bar()
        _INSTANCE = self
        self._shutdown_complete = False
        self._refresh_provider_header()
        self._restore_generated_draft()
        print(f"[twinpulse.extension] startup: {ext_id}")

    def _configure_provider(self) -> None:
        value = self._provider_settings
        config = ProviderConfig(
            base_url=value.base_url,
            endpoint_path="responses",
            model_id=value.model_id,
            api_key_env="TWINPULSE_API_KEY",
            capabilities=ProviderCapabilities(
                supports_images=True,
                supports_structured_output=True,
                max_images=1,
                accepted_mime_types=tuple(sorted(_IMAGE_MIME_TYPES)),
            ),
            timeout_s=90.0,
        )
        self._provider_service = GenerationService(
            OpenAIResponsesProvider(self._credential_store.load, reasoning_effort=value.reasoning_effort),
            config,
        )

    def _has_credential(self) -> bool:
        try:
            return bool(self._credential_store.load() or os.environ.get("TWINPULSE_API_KEY"))
        except OSError:
            return False

    def _build_header(self) -> None:
        with ui.HStack(height=ui.Pixel(54), spacing=10):
            with ui.ZStack(width=ui.Pixel(40), height=ui.Pixel(40)):
                ui.Rectangle(style={"background_color": COLORS["accent"], "border_radius": 8})
                ui.Label("TP", alignment=ui.Alignment.CENTER, style={"font_size": 16, "color": 0xFFFFFFFF})
            with ui.VStack(spacing=0, height=ui.Pixel(44)):
                ui.Label("TWINPULSE", name="eyebrow", height=ui.Pixel(16))
                ui.Label("Warehouse Copilot", name="brand", height=ui.Pixel(27))
            ui.Spacer()
            with ui.VStack(width=ui.Pixel(126), height=ui.Pixel(50), spacing=1):
                self._provider_label = ui.Label(
                    "SETUP REQUIRED", name="warning", alignment=ui.Alignment.RIGHT_CENTER, height=ui.Pixel(18)
                )
                self._provider_detail_label = ui.Label(
                    self._provider_settings.model_id,
                    name="caption",
                    alignment=ui.Alignment.RIGHT_CENTER,
                    elided_text=True,
                    height=ui.Pixel(16),
                )
                ui.Button("Settings", name="ghost", clicked_fn=self._open_settings, height=ui.Pixel(24))

    def _refresh_provider_header(self) -> None:
        configured = self._has_credential()
        if self._provider_label is not None:
            if self._provider_verified:
                self._provider_label.text = "LLM CONNECTED"
            elif configured:
                self._provider_label.text = "KEY SAVED"
            else:
                self._provider_label.text = "SETUP REQUIRED"
            self._provider_label.style = {
                "color": COLORS["green"] if self._provider_verified else COLORS["amber"],
                "font_size": 13,
            }
        if self._provider_detail_label is not None:
            self._provider_detail_label.text = self._provider_settings.model_id

    def _restore_generated_draft(self) -> None:
        try:
            record = self._draft_store.load()
        except Exception as error:
            self._set_status(f"Saved draft rejected: {type(error).__name__}: {error}")
            print(f"[twinpulse.extension] saved draft rejected: {type(error).__name__}: {error}")
            return
        if record is None:
            return
        self._set_generated_record(record, restored=True)
        print(
            "[twinpulse.extension] draft restored: "
            f"request_id={record.request_id}, images={record.image_count}, plan={record.plan_sha256[:12]}"
        )

    def _set_generated_record(self, record: GeneratedDraftRecord, *, restored: bool) -> None:
        bundle = record.bundle
        self._generated_record = record
        self._generated_bundle = bundle
        counts = Counter(call.tool for call in record.plan.calls)
        tools = ", ".join(
            f"{name} x{count}" if count > 1 else name for name, count in sorted(counts.items())
        )
        if self._draft_label is not None:
            state = "RESTORED" if restored else "DRAFT VALID"
            self._draft_label.text = (
                f"{state}  {bundle.scene.id}  |  {len(record.plan.calls)} tools -> "
                f"{len(bundle.scene.objects)} objects\n{tools}  |  images {record.image_count}"
            )
        if self._build_button is not None:
            self._build_button.text = "Build Generated Scene"
            self._build_button.enabled = True
        if restored:
            message = f"Restored validated draft - source generated plan {record.plan_sha256[:12]}"
            self._set_status(message)
            self._set_generation_status(message)

    def _build_stage_indicator(self) -> None:
        with ui.HStack(height=ui.Pixel(34), spacing=4):
            self._stage_chip("1  DESCRIBE", True)
            ui.Label(">", name="caption", width=ui.Pixel(10), alignment=ui.Alignment.CENTER)
            self._stage_chip("2  GENERATE", True)
            ui.Label(">", name="caption", width=ui.Pixel(10), alignment=ui.Alignment.CENTER)
            self._stage_chip("3  SIMULATE", False)

    def _stage_chip(self, text: str, active: bool) -> None:
        with ui.ZStack(width=ui.Pixel(124), height=ui.Pixel(30)):
            ui.Rectangle(
                style={
                    "background_color": 0xFF303030 if active else COLORS["card_alt"],
                    "border_color": COLORS["accent"] if active else COLORS["border"],
                    "border_width": 1,
                    "border_radius": 16,
                }
            )
            ui.Label(text, name="stage_active" if active else "stage_idle", alignment=ui.Alignment.CENTER)

    def _build_prompt_card(self) -> None:
        with ui.ZStack(height=ui.Pixel(380)):
            self._card_background()
            with ui.VStack(spacing=6, height=ui.Pixel(380), style={"margin": 12}):
                ui.Label("Describe the scene", name="section", height=ui.Pixel(20))
                ui.Label("Image is primary; text adds optional constraints.", name="muted", height=ui.Pixel(18))
                ui.StringField(self._prompt_model, multiline=True, height=ui.Pixel(70))
                with ui.HStack(height=ui.Pixel(28), spacing=8):
                    ui.Button("Attach image", name="ghost", clicked_fn=self._open_image_picker, width=ui.Pixel(122))
                    ui.Label("PNG, JPG or WEBP - max 10 MB", name="caption", alignment=ui.Alignment.LEFT_CENTER)
                    ui.Spacer()
                    ui.Label("Compact Diff AGV", name="caption", width=ui.Pixel(106), alignment=ui.Alignment.RIGHT_CENTER)
                self._image_frame = ui.Frame(height=ui.Pixel(92))
                self._image_frame.set_build_fn(self._build_image_preview)
                self._image_frame.rebuild()
                ui.Label(
                    "Approximate playground model. Photo scale and hidden geometry are not guaranteed.",
                    name="caption",
                    word_wrap=True,
                    height=ui.Pixel(28),
                )
                self._generate_button = ui.Button(
                    "Generate with LLM", name="primary", clicked_fn=self._request_generate, height=ui.Pixel(34)
                )
                self._generation_status_label = ui.Label(
                    "Attach an image or enter a description, then generate",
                    name="caption",
                    word_wrap=True,
                    height=ui.Pixel(20),
                )

    def _build_image_preview(self) -> None:
        if self._image_path is None:
            with ui.ZStack(height=ui.Pixel(88)):
                ui.Rectangle(style={"background_color": COLORS["card_alt"], "border_radius": 7})
                ui.Label("No reference image attached", name="caption", alignment=ui.Alignment.CENTER)
            return
        with ui.HStack(height=ui.Pixel(88), spacing=10):
            ui.Image(
                self._image_path.as_posix(),
                width=ui.Pixel(116),
                height=ui.Pixel(88),
                fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
            )
            with ui.VStack(spacing=3, height=ui.Pixel(88)):
                ui.Label(self._image_path.name, name="muted", elided_text=True, height=ui.Pixel(24))
                size_mb = self._image_path.stat().st_size / (1024 * 1024)
                measurement_text = (
                    f"{len(self._measurement_constraints)} drawing measurements enforced"
                    if self._measurement_constraints
                    else "exact dimensions unverified"
                )
                ui.Label(f"{size_mb:.2f} MB - {measurement_text}", name="caption", height=ui.Pixel(22))
                ui.Button("Remove", name="ghost", clicked_fn=self._remove_image, width=ui.Pixel(78), height=ui.Pixel(28))

    def _build_draft_card(self) -> None:
        with ui.ZStack(height=ui.Pixel(84)):
            self._card_background()
            with ui.VStack(spacing=5, height=ui.Pixel(84), style={"margin": 12}):
                with ui.HStack(height=ui.Pixel(20)):
                    ui.Label("Draft preview", name="section")
                    ui.Spacer()
                    ui.Label("SPEC 1.0", name="eyebrow", width=ui.Pixel(64), alignment=ui.Alignment.RIGHT_CENTER)
                self._draft_label = ui.Label(
                    "Configure a provider, then generate a validated scene draft.",
                    name="muted",
                    word_wrap=True,
                    height=ui.Pixel(36),
                )

    def _build_simulation_card(self) -> None:
        with ui.ZStack(height=ui.Pixel(154)):
            self._card_background()
            with ui.VStack(spacing=6, height=ui.Pixel(154), style={"margin": 12}):
                with ui.HStack(height=ui.Pixel(20)):
                    ui.Label("Simulation controls", name="section")
                    ui.Spacer()
                    ui.Label("/World/TwinPulse", name="caption", width=ui.Pixel(112), alignment=ui.Alignment.RIGHT_CENTER)
                with ui.HStack(height=ui.Pixel(32), spacing=7):
                    self._build_button = ui.Button("Build Generated Scene", name="primary", clicked_fn=self._request_build)
                    self._build_button.enabled = False
                    ui.Button("Focus", name="ghost", clicked_fn=self.focus_scene, width=ui.Pixel(88))
                with ui.HStack(height=ui.Pixel(32), spacing=7):
                    ui.Button("Run / Resume", clicked_fn=self._request_run)
                    ui.Button("Pause", clicked_fn=self.pause)
                    ui.Button("Reset", clicked_fn=self._request_reset)
                ui.Label(
                    "Build is enabled only for a validated generated tool plan.",
                    name="caption",
                    word_wrap=True,
                    height=ui.Pixel(28),
                )

    def _build_status_bar(self) -> None:
        with ui.ZStack(height=ui.Pixel(44)):
            ui.Rectangle(style={"background_color": COLORS["card_alt"], "border_radius": 8})
            with ui.HStack(height=ui.Pixel(44), spacing=8, style={"margin": 10}):
                ui.Label("READY", name="success", width=ui.Pixel(44), alignment=ui.Alignment.CENTER)
                self._status_label = ui.Label("Attach, describe, generate, then build", name="muted", word_wrap=True)

    @staticmethod
    def _card_background() -> None:
        ui.Rectangle(
            style={
                "background_color": COLORS["card"],
                "border_color": COLORS["border"],
                "border_width": 1,
                "border_radius": 8,
            }
        )

    def _open_settings(self) -> None:
        value = self._provider_settings
        self._settings_base_model = ui.SimpleStringModel(value.base_url)
        self._settings_model_model = ui.SimpleStringModel(value.model_id)
        self._settings_reasoning_model = ui.SimpleStringModel(value.reasoning_effort)
        self._settings_key_model = ui.SimpleStringModel("")
        if self._settings_window is not None:
            self._settings_window.destroy()
        self._settings_window = ui.Window("TwinPulse LLM Settings", width=560, height=420, visible=True)
        self._settings_window.frame.style = STYLE
        with self._settings_window.frame:
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                style=STYLE,
            ):
                # Keep an explicit content height so Kit does not distribute the
                # unused window height between rows and push the actions offscreen.
                with ui.VStack(spacing=8, height=ui.Pixel(360), style={"margin": 14}):
                    ui.Label("LLM Provider", name="brand", height=ui.Pixel(32))
                    ui.Label("Modern Responses API compatible endpoints only.", name="muted", height=ui.Pixel(20))
                    with ui.HStack(height=ui.Pixel(34), spacing=12):
                        ui.Label("Base URL", name="section", width=ui.Pixel(145), alignment=ui.Alignment.LEFT_CENTER)
                        ui.StringField(self._settings_base_model)
                    with ui.HStack(height=ui.Pixel(34), spacing=12):
                        ui.Label("Model ID", name="section", width=ui.Pixel(145), alignment=ui.Alignment.LEFT_CENTER)
                        ui.StringField(self._settings_model_model)
                    with ui.HStack(height=ui.Pixel(34), spacing=12):
                        ui.Label("Reasoning effort", name="section", width=ui.Pixel(145), alignment=ui.Alignment.LEFT_CENTER)
                        ui.StringField(self._settings_reasoning_model)
                    with ui.HStack(height=ui.Pixel(34), spacing=12):
                        ui.Label("API Key", name="section", width=ui.Pixel(145), alignment=ui.Alignment.LEFT_CENTER)
                        key_field = ui.StringField(self._settings_key_model)
                        if hasattr(key_field, "password_mode"):
                            key_field.password_mode = True
                    key_state = "A saved key exists. Leave blank to keep it." if self._has_credential() else "No saved key."
                    ui.Label(key_state, name="caption", height=ui.Pixel(20))
                    ui.Label("Stored in Windows Credential Manager, not Kit settings.", name="caption", height=ui.Pixel(20))
                    with ui.HStack(height=ui.Pixel(34), spacing=8):
                        ui.Button("Cancel", name="ghost", clicked_fn=self._close_settings)
                        ui.Button("Save Settings", name="primary", clicked_fn=self._save_settings)

    def _save_settings(self) -> None:
        try:
            value = ProviderSettings(
                self._settings_base_model.get_value_as_string().strip(),
                self._settings_model_model.get_value_as_string().strip(),
                self._settings_reasoning_model.get_value_as_string().strip().lower(),
            )
            ProviderConfig(
                base_url=value.base_url,
                endpoint_path="responses",
                model_id=value.model_id,
                api_key_env="TWINPULSE_API_KEY",
                capabilities=ProviderCapabilities(True, True, 1),
            ).endpoint_url()
            secret = self._settings_key_model.get_value_as_string()
            if secret.strip():
                self._credential_store.save(secret)
                self._settings_key_model.set_value("")
            save_provider_settings(value)
            self._provider_settings = value
            self._provider_service.cancel_active()
            self._configure_provider()
            self._refresh_provider_header()
            self._set_status(f"Provider saved - {value.model_id}")
            self._close_settings()
        except Exception as error:
            self._set_status(f"Settings error: {type(error).__name__}: {error}")

    def _close_settings(self) -> None:
        if self._settings_window is not None:
            self._settings_window.visible = False

    def _open_image_picker(self) -> None:
        if self._filepicker is None:
            self._filepicker = FilePickerDialog(
                "Select Reference Image",
                apply_button_label="Attach",
                click_apply_handler=self._on_image_selected,
            )
        self._filepicker.show()

    def _on_image_selected(self, filename: str, dirname: str) -> None:
        if self._filepicker is not None:
            self._filepicker.hide()
        path = Path(dirname) / filename
        mime_type = mimetypes.guess_type(path.name)[0]
        if not path.is_file() or mime_type not in _IMAGE_MIME_TYPES:
            self._set_status("Select a PNG, JPG, JPEG, or WEBP image")
            return
        if path.stat().st_size > _MAX_IMAGE_BYTES:
            self._set_status("Image exceeds the 10 MB input limit")
            return
        sidecar_path = measurement_sidecar_path(path)
        constraints: tuple[MeasurementConstraint, ...] = ()
        if sidecar_path.is_file():
            try:
                constraints = load_measurement_constraints(sidecar_path, image_path=path)
            except MeasurementConstraintError as error:
                self._set_status(f"Measurement sidecar rejected: {error}")
                return
        self._image_path = path
        self._measurement_constraints = constraints
        self._measurement_sidecar_path = sidecar_path if constraints else None
        if self._image_frame is not None:
            self._image_frame.rebuild()
        if constraints:
            self._set_status(f"Attached drawing - {path.name}; {len(constraints)} measurements will be enforced")
        else:
            self._set_status(f"Attached image - {path.name}; exact dimensions are unverified")

    def _remove_image(self) -> None:
        self._image_path = None
        self._measurement_constraints = ()
        self._measurement_sidecar_path = None
        if self._image_frame is not None:
            self._image_frame.rebuild()
        self._set_status("Reference image removed")

    @property
    def shutdown_complete(self) -> bool:
        return self._shutdown_complete and self.runtime.shutdown_complete

    def _set_status(self, message: str) -> None:
        if self._status_label is not None:
            self._status_label.text = message

    def _set_generation_status(self, message: str) -> None:
        if self._generation_status_label is not None:
            self._generation_status_label.text = message

    def _schedule(self, operation: Callable[[], object]) -> None:
        if self._busy:
            self._set_status("Please wait for the current operation")
            return
        self._busy = True
        self._track_task(asyncio.ensure_future(self._after_ui_update(operation)))

    def _track_task(self, task: asyncio.Task) -> None:
        self._tasks.add(task)

        def done(completed: asyncio.Task) -> None:
            self._tasks.discard(completed)
            self._busy = False
            if self._generate_button is not None:
                self._generate_button.text = "Generate with LLM"
                self._generate_button.enabled = True
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                self._provider_verified = False
                self._refresh_provider_header()
                message = f"Error: {type(error).__name__}: {error}"
                self._set_status(message)
                self._set_generation_status(message)
                print(f"[twinpulse.extension] UI action failed: {type(error).__name__}: {error}")

        task.add_done_callback(done)

    async def _after_ui_update(self, operation: Callable[[], object]) -> None:
        await omni.kit.app.get_app().next_update_async()
        operation()
        await omni.kit.app.get_app().next_update_async()

    def _request_generate(self) -> None:
        if self._busy:
            self._set_status("Please wait for the current operation")
            return
        prompt = self._prompt_model.get_value_as_string().strip()
        if not prompt and self._image_path is None:
            self._set_status("Attach an image or describe the warehouse before generating")
            return
        if not self._has_credential():
            self._set_status("Open Settings and save an API key first")
            self._open_settings()
            return
        self._busy = True
        message = f"Generating with {self._provider_settings.model_id} - allow up to 90 seconds..."
        self._set_status(message)
        self._set_generation_status(message)
        if self._generate_button is not None:
            self._generate_button.text = "Generating..."
            self._generate_button.enabled = False
        image_count = 1 if self._image_path is not None else 0
        print(
            f"[twinpulse.extension] generation queued: model={self._provider_settings.model_id}, "
            f"images={image_count}, measurement_constraints={len(self._measurement_constraints)}"
        )
        self._track_task(asyncio.ensure_future(self._generate_draft(prompt)))

    async def _generate_draft(self, prompt: str) -> None:
        images: tuple[ImageInput, ...] = ()
        if self._image_path is not None:
            mime_type = mimetypes.guess_type(self._image_path.name)[0]
            if mime_type not in _IMAGE_MIME_TYPES:
                raise ValueError("Attached image type is no longer supported")
            content = self._image_path.read_bytes()
            if len(content) > _MAX_IMAGE_BYTES:
                raise ValueError("Attached image now exceeds the 10 MB input limit")
            images = (ImageInput(self._image_path.name, mime_type, content),)
        request_id = str(uuid4())
        print(
            f"[twinpulse.extension] generation started: request_id={request_id}, "
            f"model={self._provider_settings.model_id}, images={len(images)}"
        )
        result = await self._provider_service.generate(
            GenerationRequest(
                request_id=request_id,
                prompt=prompt,
                images=images,
                image_detail="auto",
                measurement_constraints=self._measurement_constraints,
            )
        )
        record = GeneratedDraftRecord.create(
            request_id=result.request_id,
            provider_name=result.provider_name,
            model_id=result.model_id,
            image_count=result.image_count,
            plan=result.plan,
        )
        persistence_error: OSError | None = None
        try:
            self._draft_store.save(record)
        except OSError as error:
            # A valid paid response remains usable in memory even if local
            # persistence is unavailable. The UI and log must disclose this.
            persistence_error = error
            print(f"[twinpulse.extension] draft persistence failed: {type(error).__name__}: {error}")
        self._set_generated_record(record, restored=False)
        bundle = result.bundle
        self._provider_verified = True
        self._refresh_provider_header()
        if result.measurement_constraint_count:
            message = (
                "Draft generated; "
                f"{result.measurement_constraint_count} drawing measurements validated - "
                "click Build Generated Scene"
            )
        else:
            message = "Draft generated and validated; exact dimensions unverified - click Build Generated Scene"
        if persistence_error is not None:
            message += " (reload restore unavailable)"
        self._set_status(message)
        self._set_generation_status(message)
        print(
            f"[twinpulse.extension] generation completed: request_id={result.request_id}, "
            f"scene={bundle.scene.id}, images={result.image_count}, tools={len(result.plan.calls)}, "
            f"objects={len(bundle.scene.objects)}, measurements={result.measurement_constraint_count}, "
            f"measurement_values={result.measurement_checked_value_count}, plan={record.plan_sha256[:12]}"
        )

    def _request_build(self) -> None:
        if self._generated_bundle is None or self._generated_record is None:
            self._set_status("No generated draft - attach or describe, then Generate with LLM")
            self._set_generation_status("Build blocked: no validated generated tool plan")
            return
        if not self._warned_approximation:
            self._show_approximation_warning()
            return
        self._set_status("Building scene...")
        self._schedule(self.build_scene)

    def _show_approximation_warning(self) -> None:
        if self._warning_window is not None:
            self._warning_window.destroy()
        self._warning_window = ui.Window("Approximate Model Warning", width=500, height=300, visible=True)
        self._warning_window.frame.style = STYLE
        with self._warning_window.frame:
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                style=STYLE,
            ):
                with ui.VStack(spacing=10, height=ui.Pixel(230), style={"margin": 16}):
                    ui.Label("Approximate 3D playground model", name="brand", height=ui.Pixel(34))
                    ui.Label(
                        "The LLM draft is ready, but the 3D scene has not been built yet. "
                        "Photo scale, hidden geometry, and exact equipment placement are not guaranteed. "
                        "Use a dimensioned top-down plan or scan for accurate environments.",
                        name="muted",
                        word_wrap=True,
                        height=ui.Pixel(96),
                    )
                    with ui.HStack(height=ui.Pixel(36), spacing=8):
                        ui.Button("Cancel", name="ghost", clicked_fn=self._close_warning)
                        ui.Button("Continue and Build 3D", name="primary", clicked_fn=self._accept_warning)

    def _close_warning(self) -> None:
        if self._warning_window is not None:
            self._warning_window.visible = False

    def _accept_warning(self) -> None:
        self._warned_approximation = True
        self._close_warning()
        self._request_build()

    def _request_run(self) -> None:
        if self.runtime.compiler.bundle is None:
            self._set_status("Build the generated scene before Run")
            return
        if not self._warned_approximation:
            self._show_approximation_warning()
            return
        self._set_status("Starting simulation...")
        self._schedule(self.run)

    def _request_reset(self) -> None:
        self._set_status("Resetting simulation...")
        self._schedule(self.reset)

    def build_scene(self) -> int:
        if self._generated_bundle is None or self._generated_record is None:
            raise RuntimeError("No validated generated tool plan is available")
        count = self.runtime.build_scene(self._generated_bundle)
        record = self._generated_record
        self.runtime.compiler.set_build_metadata(
            source="generated_tool_plan",
            image_count=record.image_count,
            request_id=record.request_id,
            plan_sha256=record.plan_sha256,
        )
        source = f"generated plan {record.plan_sha256[:12]} (images {record.image_count})"
        message = f"3D scene built from {source} - {count} prims"
        self._set_status(message)
        self._set_generation_status(message)
        print(
            f"[twinpulse.extension] scene build completed: source=generated_tool_plan, "
            f"request_id={record.request_id}, images={record.image_count}, "
            f"plan={record.plan_sha256[:12]}, prims={count}"
        )
        return count

    def focus_scene(self) -> bool:
        focused = self.runtime.focus_scene()
        self._set_status("Scene focused" if focused else "No active viewport is available")
        return focused

    def run(self) -> None:
        self.runtime.run()

    def pause(self) -> None:
        self.runtime.pause()

    def reset(self) -> int:
        return self.runtime.reset()

    def on_shutdown(self) -> None:
        global _INSTANCE
        self._provider_service.cancel_active()
        for task in tuple(self._tasks):
            task.cancel()
        self._tasks.clear()
        self.runtime.shutdown()
        self._status_label = None
        self._generation_status_label = None
        self._generate_button = None
        self._build_button = None
        self._draft_label = None
        self._provider_label = None
        self._provider_detail_label = None
        self._image_frame = None
        if self._filepicker is not None:
            self._filepicker.hide()
        self._filepicker = None
        for window in (self._settings_window, self._warning_window, self._window):
            if window is not None:
                window.destroy()
        self._settings_window = None
        self._warning_window = None
        self._window = None
        self._shutdown_complete = True
        if _INSTANCE is self:
            _INSTANCE = None
        gc.collect()
        print(f"[twinpulse.extension] shutdown: {self.ext_id}")
