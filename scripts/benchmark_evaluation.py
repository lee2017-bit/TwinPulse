# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Evaluator-only selection/readiness. Human provenance is attested, not inferred."""
from copy import deepcopy
from datetime import datetime
from scripts.benchmark_protocol import canonical_sha, file_sha, read_json, _shape
from scripts.benchmark_quality import checked_annotation, checked_rubric


def selected_rubric(prepared, supplied=None):
    selected = prepared.get('evaluation')
    if selected is None:
        return supplied  # Explicitly reported as legacy selection, not v1.2.
    reference = selected['rubric']
    if file_sha(reference['path']) != reference['sha256']:
        raise ValueError('BENCHMARK_SELECTED_RUBRIC_CHANGED')
    rubric = checked_rubric(read_json(reference['path']))
    if canonical_sha(rubric) != selected['rubric_sha256'] or supplied is not None and supplied != rubric:
        raise ValueError('BENCHMARK_RUBRIC_SELECTION_CHANGED')
    return rubric


def checked_provenance(value, manifest, rubric):
    _shape(value, ('schema_version', 'dataset_id', 'rubric_sha256', 'cases'),
           'BENCHMARK_LABEL_PROVENANCE_INVALID')
    if (value['schema_version'] != 'benchmark-label-review-1.0'
            or value['dataset_id'] != manifest['dataset_id'] or value['rubric_sha256'] != canonical_sha(rubric)
            or type(value['cases']) is not list):
        raise ValueError('BENCHMARK_LABEL_PROVENANCE_BINDING_CHANGED')
    from scripts.benchmark_protocol import journey_packet
    cases = {case['case_id']: case for case in manifest['cases']}
    seen = set()
    for row in value['cases']:
        _shape(row, ('case_id', 'input_sha256', 'annotations_sha256', 'reviewers', 'source',
                     'blinded', 'reviewed_before_outputs', 'reviewed_at'), 'BENCHMARK_LABEL_REVIEW_INVALID')
        case = cases.get(row['case_id']);reference = case['annotations'] if case else None
        if (case is None or row['case_id'] in seen or row['input_sha256'] != canonical_sha(journey_packet(case))
                or row['annotations_sha256'] != (reference['sha256'] if reference else None)):
            raise ValueError('BENCHMARK_LABEL_REVIEW_BINDING_CHANGED')
        seen.add(row['case_id'])
        if (row['source'] not in ('human', 'unreviewed') or type(row['reviewers']) is not list
                or len(row['reviewers']) > 10 or any(type(r) is not str or not r.strip() or len(r)>160 for r in row['reviewers'])
                or len(set(row['reviewers'])) != len(row['reviewers'])
                or type(row['blinded']) is not bool or type(row['reviewed_before_outputs']) is not bool):
            raise ValueError('BENCHMARK_LABEL_REVIEW_INVALID')
        if row['source'] == 'human':
            try:
                date = datetime.fromisoformat(row['reviewed_at'])
                if date.utcoffset() is None:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('BENCHMARK_LABEL_REVIEW_DATE_INVALID') from None
            if not reference or not row['reviewers'] or not row['blinded'] or not row['reviewed_before_outputs']:
                raise ValueError('BENCHMARK_INDEPENDENT_LABEL_REVIEW_REQUIRED')
        elif row['reviewers'] or row['reviewed_at'] is not None or row['blinded'] or row['reviewed_before_outputs']:
            raise ValueError('BENCHMARK_UNREVIEWED_LABELS_CANNOT_CLAIM_HUMAN_REVIEW')
    if seen != set(cases):
        raise ValueError('BENCHMARK_LABEL_REVIEW_CASE_COVERAGE_CHANGED')
    return deepcopy(value)


def readiness(manifest, packets):
    evaluation = manifest.get('evaluation')
    if evaluation is None:
        return dict(status='LEGACY_EVALUATION_SELECTION', human_identity_verified=False, cases=[])
    if file_sha(evaluation['rubric']['path'])!=evaluation['rubric']['sha256']:
        raise ValueError('BENCHMARK_SELECTED_RUBRIC_CHANGED')
    rubric = checked_rubric(read_json(evaluation['rubric']['path']))
    reference = evaluation['review_provenance']
    if reference and file_sha(reference['path'])!=reference['sha256']:
        raise ValueError('BENCHMARK_REVIEW_PROVENANCE_CHANGED')
    provenance = checked_provenance(read_json(reference['path']), manifest, rubric) if reference else None
    rows = {row['case_id']: row for row in provenance['cases']} if provenance else {}
    result = []
    for case in manifest['cases']:
        status = 'PENDING_HUMAN_LABEL_REVIEW';reason = None;count = 0
        row = rows.get(case['case_id']);annotation = case['annotations']
        if annotation:
            try:
                if file_sha(annotation['path'])!=annotation['sha256']:
                    raise ValueError('BENCHMARK_ANNOTATION_SHA_CHANGED')
                labels = checked_annotation(read_json(annotation['path']), packets[case['case_id']], rubric)
                if (row and row['source'] == 'human' and row['reviewers'] == labels['reviewers']
                        and labels['coverage_complete']):
                    status = 'LABELS_REVIEWED_ATTESTED';count = len(labels['reviewers'])
                elif row and row['source'] == 'human':
                    status = 'INVALID';reason = 'BENCHMARK_REVIEWERS_OR_COVERAGE_CHANGED'
            except (ValueError, OSError) as error:
                status = 'INVALID';reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        result.append(dict(case_id=case['case_id'], split=case['split'], modality=case['modality'],
                           status=status, reason=reason, reviewer_count=count,
                           reviewed_at=row['reviewed_at'] if row and status=='LABELS_REVIEWED_ATTESTED' else None))
    return dict(status='LABELS_REVIEWED_ATTESTED' if all(r['status']=='LABELS_REVIEWED_ATTESTED' for r in result)
                else 'PENDING_OR_INVALID_LABELS', human_identity_verified=False,
                independent_visual_review='NOT_RUN', cases=result)
