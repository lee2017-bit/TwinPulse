# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Persisted v2 site draft; only its reviewed SceneRevision may become a Build artifact."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from typing import Any, Mapping

from twinpulse_core import (InputRevision, SitePlan, SiteToolPlan, canonical_sha256,
                            execute_site_tool_plan)


SITE_DRAFT_VERSION = "2.0"


@dataclass(frozen=True, slots=True)
class SiteDraftRecord:
    request_id: str
    provider_name: str
    model_id: str
    image_count: int
    input_revision: InputRevision
    plan: SiteToolPlan
    site: SitePlan
    plan_sha256: str
    schema_version: str = SITE_DRAFT_VERSION
    placement_contract: Mapping[str, Any] | None = None
    progressive_twin: Mapping[str, Any] | None = None
    draft_refinement: Mapping[str, Any] | None = None

    @classmethod
    def create(cls, *, request_id: str, provider_name: str, model_id: str,
               image_count: int, input_revision: InputRevision, plan: SiteToolPlan,
               placement_contract: Mapping[str, Any] | None = None,
               progressive_twin: Mapping[str, Any] | None = None,
               draft_refinement: Mapping[str, Any] | None = None) -> "SiteDraftRecord":
        if not all(isinstance(item, str) and 1 <= len(item) <= 128
                   for item in (request_id, provider_name, model_id)):
            raise ValueError("site draft identity is invalid")
        if type(image_count) is not int or image_count != len(input_revision.images):
            raise ValueError("site draft image count is invalid")
        checked_input = InputRevision.from_dict(input_revision.to_dict())
        checked_plan = SiteToolPlan.from_dict(plan.to_dict())
        source = "drawing" if checked_input.input_kind == "drawing" else (
            "photo" if checked_input.images else "manual")
        site = execute_site_tool_plan(checked_plan, source=source, source_ref=checked_input.digest)
        from twinpulse_core.photo_placement import checked_placement_contract, validate_placement_plan
        contract=checked_placement_contract(placement_contract) if placement_contract is not None else None
        validate_placement_plan(checked_plan,contract)
        from twinpulse_core.progressive_twin import checked_envelope
        progressive=checked_envelope(progressive_twin,checked_plan.to_dict()) if progressive_twin is not None else None
        from twinpulse_core.draft_refinement import checked_refinement
        refinement=checked_refinement(draft_refinement,checked_plan.to_dict(),request_id=request_id,progressive=progressive) if draft_refinement is not None else None
        if refinement is not None and progressive is None:raise ValueError('DRAFT_REFINEMENT_PROGRESSIVE_REQUIRED')
        return cls(request_id, provider_name, model_id, image_count, checked_input,
                   checked_plan, site, canonical_sha256(checked_plan.to_dict()),
                   '2.4' if checked_plan.plan_version=='2.4' else '2.3' if refinement is not None else '2.2' if progressive is not None else '2.1' if contract is not None else SITE_DRAFT_VERSION,
                   contract,progressive,refinement)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "request_id": self.request_id,
                "provider_name": self.provider_name, "model_id": self.model_id,
                "image_count": self.image_count, "input_revision": self.input_revision.to_dict(),
                "plan": self.plan.to_dict(), "site": self.site.to_dict(),
                "plan_sha256": self.plan_sha256,
                **({'placement_contract':deepcopy(self.placement_contract)} if self.placement_contract is not None else {}),
                **({'progressive_twin':deepcopy(self.progressive_twin)} if self.progressive_twin is not None else {}),
                **({'draft_refinement':deepcopy(self.draft_refinement)} if self.draft_refinement is not None else {})}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SiteDraftRecord":
        expected = {"schema_version", "request_id", "provider_name", "model_id", "image_count",
                    "input_revision", "plan", "site", "plan_sha256"}
        version=value.get('schema_version') if isinstance(value,Mapping) else None
        if version=='2.1':expected|={'placement_contract'}
        if version in ('2.2','2.3'):
            expected|={'progressive_twin'}
            if 'placement_contract' in value:expected|={'placement_contract'}
        if version=='2.3':expected|={'draft_refinement'}
        if not isinstance(value, Mapping) or set(value) != expected or version not in (SITE_DRAFT_VERSION,'2.1','2.2','2.3','2.4'):
            raise ValueError("site draft shape or version is unsupported")
        if not all(isinstance(value[field], Mapping) for field in ("input_revision", "plan", "site")):
            raise ValueError("site draft records are invalid")
        record = cls.create(request_id=value["request_id"], provider_name=value["provider_name"],
                            model_id=value["model_id"], image_count=value["image_count"],
                            input_revision=InputRevision.from_dict(value["input_revision"]),
                            plan=SiteToolPlan.from_dict(value["plan"]),
                            placement_contract=value.get('placement_contract'),
                            progressive_twin=value.get('progressive_twin'),draft_refinement=value.get('draft_refinement'))
        if record.schema_version!=value['schema_version']:
            raise ValueError('stored site draft placement version mismatch')
        if value["plan_sha256"] != record.plan_sha256 or canonical_sha256(value["site"]) != canonical_sha256(record.site.to_dict()):
            raise ValueError("stored site draft does not match deterministic expansion")
        return record
