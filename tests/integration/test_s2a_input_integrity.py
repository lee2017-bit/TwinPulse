# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""S2a bounded image decoding and immutable measurement-binding acceptance."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import ApplicationService, BrokerError, CommandBroker, ProductWorkflow, ProjectStore  # noqa: E402
from twinpulse_core import InputArtifactStore  # noqa: E402
from twinpulse_provider import ImageInput, MeasurementConstraint  # noqa: E402


JPEG_2X4 = base64.b64decode(
    "/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYyLjI4LjEwMgD/2wBDAAgEBAQEBAUFBQUFBQYGBgYGBgYGBgYGBgYGBgYHBwcICAgHBwcGBgcHCAgICAkJCQgICAgJCQoKCgwMCwsODg4RERT/xABMAAEBAAAAAAAAAAAAAAAAAAAABgEBAQAAAAAAAAAAAAAAAAAABgcQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/wAARCAAEAAIDASIAAhEAAxEA/9oADAMBAAIRAxEAPwCLAE1/f//Z"
)
WEBP_VP8_2X4 = base64.b64decode(
    "UklGRjwAAABXRUJQVlA4IDAAAADQAQCdASoCAAQAAgA0JaACdLoB+AADsAD+8Oj3/yC5YXXI1/8gP+QH/ID/+PIAAAA="
)
WEBP_VP8L_2X4 = base64.b64decode("UklGRhwAAABXRUJQVlA4TA8AAAAvAcAAAAcQ9Y/+ByKi/wEA")


class _UnusedGateway:
    def cancel_active(self) -> None:
        pass

    async def generate(self, request):
        raise AssertionError("S2a input tests must not start generation")


def png(width: int = 2, height: int = 4, *, include_pixels: bool = True) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, content: bytes) -> bytes:
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xFFFFFFFF)

    body = chunk(b"IHDR", header)
    if include_pixels:
        rows = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))
        body += chunk(b"IDAT", zlib.compress(rows))
    return signature + body + chunk(b"IEND", b"")


class S2aInputIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.workflow = ProductWorkflow(
            ApplicationService(
                _UnusedGateway(), project_store=ProjectStore(root / "active_project.json"),
                artifact_store=InputArtifactStore(root / "inputs"),
            ), CommandBroker(), mode="explicit_fixture",
            generation_settings_getter=lambda: {
                "base_url": "https://fixture.invalid/v1/", "model_id": "input-only",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            },
        )

    def tearDown(self) -> None:
        self.workflow.shutdown()
        self.temporary.cleanup()

    @staticmethod
    def request(content: bytes, media_type: str, *, name: str = "warehouse.bin", prompt: str = "창고 통로를 구성해줘") -> dict[str, object]:
        return {
            "name": name,
            "input_kind": "drawing",
            "prompt": prompt,
            "media_type": media_type,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "sidecar_name": None,
            "sidecar_content_base64": None,
        }

    def test_normal_png_jpeg_vp8_and_vp8l_are_fully_decoded(self) -> None:
        corpus = (
            (png(), "image/png", "warehouse.png"),
            (JPEG_2X4, "image/jpeg", "warehouse.jpg"),
            (WEBP_VP8_2X4, "image/webp", "warehouse-lossy.webp"),
            (WEBP_VP8L_2X4, "image/webp", "warehouse-lossless.webp"),
        )
        for content, media_type, name in corpus:
            with self.subTest(name=name):
                result = self.workflow.select_input(self.request(content, media_type, name=name))
                self.assertEqual((result["input"]["width"], result["input"]["height"]), (2, 4))

    def test_missing_pixels_truncation_spoofing_and_oversized_dimensions_are_rejected(self) -> None:
        cases = (
            (self.request(b"", "image/png", name="empty.png"), "image_size_invalid"),
            (self.request(b"0" * (10 * 1024 * 1024 + 1), "image/png", name="oversized.png"), "image_size_invalid"),
            (self.request(png(include_pixels=False), "image/png", name="header-only.png"), "image_content_invalid"),
            (self.request(JPEG_2X4[:-2], "image/jpeg", name="truncated.jpg"), "image_content_invalid"),
            (self.request(png(), "image/jpeg", name="spoofed.jpg"), "image_type_mismatch"),
            (self.request(png(10_000, 10_000, include_pixels=False), "image/png", name="huge.png"), "image_dimensions_invalid"),
        )
        for request, code in cases:
            with self.subTest(code=code, name=request["name"]):
                with self.assertRaises(BrokerError) as raised:
                    self.workflow.select_input(request)
                self.assertEqual(raised.exception.code, code)

    def test_sidecar_v11_is_bound_to_exact_image_hash_dimensions_and_typed_constraints(self) -> None:
        content = png()
        sidecar = {
            "schema_version": "1.1",
            "source_image": "plan.png",
            "source_image_sha256": hashlib.sha256(content).hexdigest(),
            "source_image_dimensions_px": [2, 4],
            "measurement_constraints": [{
                "constraint_id": "floor_width",
                "tool": "create_floor",
                "argument_path": "size_m.0",
                "expected": 8.0,
                "tolerance": 0.01,
            }],
        }
        request = self.request(content, "image/png", name="plan.png")
        request.update({
            "sidecar_name": "plan.measurements.json",
            "sidecar_content_base64": base64.b64encode(json.dumps(sidecar).encode("utf-8")).decode("ascii"),
        })
        selected = self.workflow.select_input(request)
        current = self.workflow.current_input
        self.assertEqual(selected["input"]["measurement_count"], 1)
        self.assertEqual(current.image_sha256, sidecar["source_image_sha256"])
        self.assertEqual(current.image_dimensions_px, (2, 4))
        self.assertEqual(current.measurement_constraints[0].constraint_id, "floor_width")

        for field, wrong in (
            ("source_image_sha256", "0" * 64),
            ("source_image_dimensions_px", [4, 2]),
        ):
            bad = dict(sidecar, **{field: wrong})
            invalid = dict(request, sidecar_content_base64=base64.b64encode(json.dumps(bad).encode()).decode())
            with self.subTest(field=field), self.assertRaises(BrokerError) as raised:
                self.workflow.select_input(invalid)
            self.assertEqual(raised.exception.code, "sidecar_invalid")

    def test_revision_identity_changes_with_measurement_profile_settings_and_catalog(self) -> None:
        image = ImageInput("plan.png", "image/png", png())
        measurement = MeasurementConstraint("floor_width", "create_floor", "size_m.0", 8.0, 0.01)

        def revision(*, expected: float = 8.0, profile: str = "agv_compact_2wd_caster_v2", catalog: str = "scene-tools-1.0") -> str:
            constraint = MeasurementConstraint("floor_width", "create_floor", "size_m.0", expected, 0.01)
            return ApplicationService.prepare_input(
                prompt="치수대로 생성해줘",
                images=(image,),
                measurement_constraints=(constraint,),
                generation_settings={
                    "base_url": "https://example.test/v1/",
                    "model_id": "fake",
                    "reasoning_effort": "low",
                    "image_detail": "high",
                    "request_schema": "1.0",
                    "tool_catalog_revision": catalog,
                },
                input_kind="drawing",
                profile_id=profile,
            ).revision.digest

        original = revision()
        self.assertNotEqual(original, revision(expected=7.5))
        self.assertNotEqual(original, revision(profile="agv_compact_2wd_caster_v1"))
        self.assertNotEqual(original, revision(catalog="scene-tools-2.0"))
        self.assertEqual(measurement.expected, 8.0)


if __name__ == "__main__":
    unittest.main()
