# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only, bounded explanation of a reviewed site scene's recorded sources.

The plan may contain model-authored descriptions. This report labels those as
claims, never as a measurement or a validated photo/world alignment.
"""

from __future__ import annotations

from twinpulse_core import SiteToolPlan
from .site_draft import SiteDraftRecord


def site_review_provenance(record: SiteDraftRecord, current_plan: SiteToolPlan,
                           current_scene_revision: str, local_edit_count: int) -> dict[str, object]:
    original_calls = {call.call_id: call for call in record.plan.calls}
    evidence = {item.call_id: item for item in current_plan.call_evidence or ()}
    calls: list[dict[str, object]] = []
    for call in current_plan.calls:
        edited = original_calls.get(call.call_id) != call
        declared = evidence.get(call.call_id)
        calls.append({
            "call_id": call.call_id,
            "tool": call.tool,
            "origin": "user_local_edit" if edited else "original_plan",
            "basis": "user" if edited else declared.basis if declared is not None else "unprovided",
            "observation_ids": [] if edited or declared is None else list(declared.observation_ids),
        })
    local_recipe = record.provider_name == "local-room-recipe" and record.model_id == "no-provider-call"
    return {
        "schema_version": "site-review-provenance-1.0",
        "source_class": "local_recipe" if local_recipe else "saved_provider_or_fixture_plan",
        "provider_name": record.provider_name,
        "model_id": record.model_id,
        "input_kind": record.input_revision.input_kind,
        "input_revision": record.input_revision.digest,
        "source_plan_sha256": record.plan_sha256,
        "original_scene_revision": record.site.scene.revision,
        "current_scene_revision": current_scene_revision,
        "local_edit_count": local_edit_count,
        "photo_interpretation_evidence": (
            "local_import_not_performed" if local_recipe else "not_verified_by_saved_plan"),
        "world_alignment": "NOT_VERIFIED",
        "physical_validation": "NOT_RUN",
        "calls": calls,
    }
