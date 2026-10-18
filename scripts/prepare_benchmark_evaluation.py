# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Create empty reviewer worksheets; never invent labels, measurements or reviewers."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))
from scripts.benchmark_protocol import prepare, canonical_sha, read_json
from scripts.benchmark_quality import checked_rubric


def worksheets(prepared, rubric):
    rubric = checked_rubric(rubric);drafts = []
    for case_id, packet in prepared['packets'].items():
        drafts.append(dict(schema_version='benchmark-annotation-draft-1.0', case_id=case_id,
            input_sha256=canonical_sha(packet), rubric_sha256=canonical_sha(rubric),
            coordinate_frame='room_xy_normalized_front_negative_y', coverage_complete=False,
            reviewers=[], entities=[], relations=[], room_size_m=None, room_size_authority='unknown'))
    provenance=dict(schema_version='benchmark-label-review-1.0',dataset_id=prepared['dataset_id'],
        rubric_sha256=canonical_sha(rubric),cases=[dict(case_id=case_id,input_sha256=canonical_sha(packet),
            annotations_sha256=None,reviewers=[],source='unreviewed',blinded=False,
            reviewed_before_outputs=False,reviewed_at=None) for case_id,packet in prepared['packets'].items()])
    return dict(status='PENDING_HUMAN_LABEL_REVIEW', manifest_sha256=prepared['manifest_sha256'],
        rubric_sha256=canonical_sha(rubric), HTTP=0, actual_run_authorized=False,
        human_identity_verified=False, automatic_labels=False, drafts=drafts,review_provenance_template=provenance)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--rubric', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepared = prepare(args.manifest)
    from scripts.benchmark_evaluation import selected_rubric
    result = worksheets(prepared, selected_rubric(prepared, read_json(args.rubric)))
    if any(path.is_symlink() for path in (args.output, *args.output.parents)):
        raise ValueError('BENCHMARK_LINKED_OUTPUT')
    args.output.mkdir(parents=True, exist_ok=False)
    # IDs have already passed the manifest path-safe ID contract.
    for draft in result.pop('drafts'):
        with (args.output/(draft['case_id']+'.annotation-draft.json')).open('x', encoding='utf-8') as stream:
            json.dump(draft, stream, ensure_ascii=False, indent=2, allow_nan=False)
    with (args.output/'label-review-draft.json').open('x',encoding='utf-8') as stream:
        json.dump(result.pop('review_provenance_template'),stream,ensure_ascii=False,indent=2,allow_nan=False)
    with (args.output/'readiness.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(status=result['status'], cases=len(prepared['packets']), HTTP=0)))


if __name__ == '__main__':
    main()
