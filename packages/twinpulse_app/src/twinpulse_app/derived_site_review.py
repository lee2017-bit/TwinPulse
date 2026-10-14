# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Validated derived-review persistence; never an active project or Run approval.

The original deterministic SiteDraftRecord is retained, not replaced or edited.
The scan archive must start from that EXACT plan, and every operation is replayed
through ScanReview validators. Consumers must independently review/register/build
the resulting scene; loading this record does none of those things.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
from uuid import uuid4

from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.site_contracts import SitePlan
from twinpulse_core.scan_correction import plan_revision
from .site_draft import SiteDraftRecord
from .scan_review import ScanReview, _unique, _nonfinite

MAX_DERIVED_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DerivedSiteReview:
    source: SiteDraftRecord
    archive_text: str
    site: SitePlan
    revision: str

    @classmethod
    def create(cls, source: SiteDraftRecord, archive_text: str):
        if not isinstance(source, SiteDraftRecord):
            raise ValueError("original typed site draft required")
        checked = SiteDraftRecord.from_dict(source.to_dict())
        review = ScanReview()
        review.import_archive(review.snapshot()["workspace_revision"], archive_text)
        archive = review.export_archive(review.snapshot()["workspace_revision"])
        if plan_revision(checked.site) != plan_revision(SitePlan.from_dict(archive["base_plan"])):
            raise ValueError("archive base differs from the original generated site draft")
        if not archive["actions"]:
            raise ValueError("derived review requires at least one applied operation")
        site = SitePlan.from_dict(review.export_review()["reviewed_site_plan"])
        if site.scene.revision == checked.site.scene.revision:
            raise ValueError("derived scene requires its own identity")
        # Preserve exact numbers, discard formatting differences in the envelope.
        canonical_text = json.dumps(archive, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        identity = {"policy": "derived-site-review-1.0", "source": canonical_sha256(checked.to_dict()),
                    "archive": archive["archive_digest"], "result": plan_revision(site)}
        return cls(checked, canonical_text, site, canonical_sha256(identity))

    def to_dict(self):
        return {"schema_version": "derived-site-review-1.0", "source_draft": self.source.to_dict(),
                "archive_text": self.archive_text, "derived_site": self.site.to_dict(),
                "revision": self.revision, "execution_authority": False, "source_verified": False}

    @classmethod
    def from_dict(cls, value):
        fields = {"schema_version", "source_draft", "archive_text", "derived_site", "revision",
                  "execution_authority", "source_verified"}
        if type(value) is not dict or set(value) != fields or value["schema_version"] != "derived-site-review-1.0":
            raise ValueError("unsupported derived site record")
        if value["execution_authority"] is not False or value["source_verified"] is not False:
            raise ValueError("derived review is unverified and cannot grant execution authority")
        if type(value["source_draft"]) is not dict:
            raise ValueError("original source draft required")
        record = cls.create(SiteDraftRecord.from_dict(value["source_draft"]), value["archive_text"])
        if (value["revision"] != record.revision
                or canonical_sha256(value["derived_site"]) != canonical_sha256(record.site.to_dict())):
            raise ValueError("derived record does not match recomputed history")
        return record

    def summary(self):
        return {"revision": self.revision, "source_scene_revision": self.source.site.scene.revision,
                "derived_scene_revision": self.site.scene.revision,
                "input_revision": self.source.input_revision.digest,
                "object_count": len(self.site.scene.objects), "review_required": True,
                "source_verified": False, "alignment_verified": False,
                "active_project_changed": False, "motion_authorized": False,
                "physical_validation": "NOT_RUN", "build_authorized": False,
                "notice": "Persisted derived review only. Original tool expansion and edit history revalidated. No active Twin, build, TF or execution approval."}


class DerivedReviewStore:
    """Explicit-path sidecar, independent of the active ProjectStore.

    Only the supplied sidecar path is replaced; fail-before-replace preserves
    the prior record. An interrupted save may leave its uniquely named temp file;
    loading never searches for or promotes such partial files.
    """
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self):
        if not self.path.is_file():
            return None
        with self.path.open("rb") as handle:
            data = handle.read(MAX_DERIVED_BYTES + 1)
        if len(data) > MAX_DERIVED_BYTES:
            raise ValueError("derived record exceeds 20 MiB")
        try:
            value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite)
        except (RecursionError, OverflowError) as exc:
            raise ValueError("invalid derived record nesting") from exc
        return DerivedSiteReview.from_dict(value)

    def save(self, record: DerivedSiteReview):
        checked = DerivedSiteReview.from_dict(record.to_dict())
        text = json.dumps(checked.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        data = text.encode("utf-8")
        if len(data) > MAX_DERIVED_BYTES:
            raise ValueError("derived record exceeds 20 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp-" + uuid4().hex)
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()  # Only the exact new temp file created by this save.
