# SPDX-License-Identifier: Apache-2.0
"""Read-only final report/link/identity check, not another App or device trial."""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "outputs/robot-roomplan-ready-20261023"
RELEASE = "20261023T045245Z-9d9e533cef09"
SOURCE = "9d9e533cef0949b6792a0078a50790fb54997dc570a9ca2079d4bb6d6f2fd9cf"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8-sig"))


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href")


def main():
    issues = []
    records = {}

    def check(condition, issue):
        if not condition:
            issues.append(issue)

    def evidence(name):
        records[name] = digest(ROOT / name)
        return read(name)

    document = (ROOT / "report.html").read_text(encoding="utf-8")
    parser = Links()
    parser.feed(document)
    linked = {}
    for href in parser.links:
        url = urlsplit(href)
        path = (ROOT / unquote(url.path)).resolve()
        valid = not url.scheme and not url.netloc and path.is_relative_to(ROOT) and path.is_file()
        check(valid, "INVALID_OR_MISSING_REPORT_LINK:" + href)
        if valid:
            linked[href] = digest(path)
    check(bool(linked), "EMPTY_REPORT")
    for text in ("READY_FOR_SUPERVISED_POWERED_TEST", RELEASE, "실물 성공 판정이 아닙니다",
                 "NOT_RUN", "UNKNOWN", "cold 클립을 완성된cold데모라고 부르지 않았습니다"):
        check(text in document, "REPORT_SCOPE_OR_IDENTITY_MISSING:" + text)
    for name in ("gate-result12.json", "roomplan-gate-result12.json",
                 "gate-result12-independent.json", "roomplan-gate-result12-independent.json"):
        value = evidence(name)
        check(value.get("status") == "READY_FOR_SUPERVISED_POWERED_TEST" and value.get("issues") == [], name)
        check(value.get("release_id") == RELEASE and value.get("source_sha256") == SOURCE, "WRONG_IDENTITY:" + name)
    for name, count, preserved in (
            ("gate-additional-negatives12.json", 13, "original_app_result_unchanged"),
            ("roomplan-gate-negatives12.json", 4, "original_records_unchanged")):
        value = evidence(name)
        tests = value.get("tests", [])
        check(value.get("status") == "PASS" and value.get(preserved) is True and len(tests) == count
              and all(t.get("status") == "PASS_NEGATIVE_REJECTED" for t in tests), name)
    installed = evidence("installed-files12-final.json")
    check(installed.get("status") == "PASS" and installed.get("mismatches") == []
          and installed.get("file_count") == 1681 and installed.get("release_id") == RELEASE
          and installed.get("source_manifest_sha256") == SOURCE, "INSTALLED_IDENTITY")
    source = evidence("astra-source-reviewed12.json")
    native = evidence("astra-native-boundary-review12.json")
    for mapping, count in ((source["final_reviewed_files"], 41), (native["files"], 8)):
        check(len(mapping) == count, "REVIEW_FILE_COUNT")
        for name, expected in mapping.items():
            path = (REPO / name).resolve()
            check(path.is_relative_to(REPO) and path.is_file() and digest(path) == expected,
                  "CURRENT_REVIEWED_SOURCE_CHANGED:" + name)
    raw = evidence("astra-raw-review12.json")
    check(raw.get("status") == "NO_ADDITIONAL_CONFIRMED_BLOCKER_IN_REVIEWED_CURRENT_SOFTWARE_EVIDENCE"
          and raw.get("read_only") is True and raw.get("unresolved") == []
          and raw.get("release_id") == RELEASE and raw.get("source_sha256") == SOURCE, "RAW_REVIEW")
    for name, expected in raw["reviewed_raw_sha256"].items():
        check(digest(ROOT / name) == expected, "REVIEWED_RAW_CHANGED:" + name)
    media = evidence("media-checks12b.json")
    visual = evidence("media-visual-review12.json")
    check(media.get("status") == "PASS" and len(media.get("videos", [])) == 6, "MEDIA")
    check(visual.get("status") == "PASS_SCOPED_WITH_DOCUMENTED_CAPTURE_LIMITS"
          and visual.get("release_id") == RELEASE and visual.get("source_sha256") == SOURCE
          and visual.get("media_checks") == {"path": "media-checks12b.json", "sha256": records["media-checks12b.json"]}, "VISUAL_REVIEW")
    cycle = evidence("roomplan-saved-cycle12.json")
    check(cycle.get("status") == "PASS" and cycle.get("issues") == [], "SAVED_CYCLE")
    state = evidence("final-local-state12.json")
    check(state.get("source_mismatches") == [] and state.get("native_mismatches") == []
          and state.get("twinpulse_named_roots") == [] and state.get("launcher_lock_present") is False,
          "LAST_OBSERVED_LOCAL_STATE")
    docs = {}
    for name in ("README.md", "docs/planning/TWINPULSE_PROJECT_MEMORY.md",
                 "docs/planning/TWINPULSE_BASELINE.md", "docs/progress.md",
                 "docs/verification/ROBOT_FOCUSED_TEST_ACCEPTANCE_2026-10-18.md"):
        path = REPO / name
        check("v611" in path.read_text(encoding="utf-8-sig")[:5000], "MILESTONE_RECORD_MISSING:" + name)
        docs[name] = digest(path)
    result = dict(schema="twinpulse.readiness-handoff-static.v1", checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  status="PASS_STATIC_HANDOFF_VERIFICATION" if not issues else "FAIL",
                  release_id=RELEASE, source_sha256=SOURCE, issues=issues,
                  report=dict(path="report.html", sha256=digest(ROOT / "report.html")),
                  link_count=len(parser.links), unique_link_count=len(linked), linked_sha256=linked,
                  evidence_sha256=records, milestone_docs_sha256=docs,
                  source_review_count=41, native_boundary_source_count=8,
                  limitation="Static handoff closure only. Original gates own software verdicts; no new UI, physical, native capture or publication trial.")
    with (ROOT / "completion-verification12.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: result[key] for key in ("status", "issues", "link_count", "unique_link_count", "report")}))
    raise SystemExit(1 if issues else 0)


if __name__ == "__main__":
    main()
