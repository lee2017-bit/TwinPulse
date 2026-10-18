# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Checked pending-support evidence, never whole-scene or photo acceptance."""
from copy import deepcopy

from twinpulse_core import canonical_sha256
from twinpulse_core.geometry_checks import CHECK_REVISION, PHASES
from twinpulse_core.progressive_twin import checked_envelope


def checked_support_subset(candidate, plan, report):
    from .semantic_scene import layout_for, revision
    draft=deepcopy(candidate)
    if isinstance(draft.get('objects'),list):
        draft['objects']={r['id']:{k:v for k,v in r.items() if k!='id'} for r in draft['objects']}
    witness=checked_envelope(report['progressive_twin'],plan)
    targets={r['id'] for r in witness['inventory']}
    rows=report['checks']
    if (not witness['unresolved'] or report.get('candidate_revision')!=revision(draft) or
            witness['source_sha256']!=canonical_sha256(layout_for(draft)) or
            report.get('check_ledger_version')!=CHECK_REVISION or
            report.get('mandatory_checks')!=list(PHASES) or
            report.get('checks_complete') is not False or report.get('checks_truncated') is not False or
            report.get('materialized_subset_checked') is not True or report.get('inventory_complete') is not False or
            [r['check_id'] for r in rows]!=list(PHASES) or any(
                r.get('status')!=('partial' if r['check_id']=='support_packing' else 'passed') or
                r.get('candidate_revision')!=revision(draft) or r.get('checker_revision')!=CHECK_REVISION or
                set(r.get('target_ids',[]))!=targets for r in rows)):
        raise ValueError('SUPPORT_SUBSET_EVIDENCE_INVALID')
    refs=[r['evidence']['issue_id'] for r in witness['unresolved']]
    support=next(r for r in rows if r['check_id']=='support_packing')
    if set(support['issue_refs'])!=set(refs):
        raise ValueError('SUPPORT_SUBSET_ISSUES_INVALID')
    return witness


def support_refinement_quality(candidate, plan, report):
    witness=checked_support_subset(candidate,plan,report)
    from twinpulse_core.geometry_diagnostics import geometry_issue
    from .semantic_scene import revision
    from twinpulse_core.progressive_twin import pending_root
    pending_by_id={r['id']:r for r in witness['unresolved']}
    materialized={c['arguments']['id'] for c in plan['calls']}
    issues=[]
    for pending in witness['unresolved']:
        # A distinct wrapper addresses the materialized direct parent. Keep the
        # original pending ID/risk/diagnosis unchanged, rather than rewriting it.
        anchor=pending_root(pending['id'],pending_by_id,materialized)
        issue=geometry_issue('PHOTO_PENDING_SUPPORT_NEEDS_REVISION',anchor,
            path='$.progressive_twin.unresolved.'+pending['id'],
            actual={'pending_id':pending['id'],'reason':pending['reason'],
                **({'waiting_parent_id':pending['parent_id'],'materialized_anchor_id':anchor}
                    if anchor!=pending['parent_id'] else {})},
            expected={'support_placement':'requires_revision'},repairable=True)
        issue['source_issue']=deepcopy(pending)
        issues.append(issue)
    return dict(schema_version='candidate-quality-review-1.0',status='needs_revision',
        candidate_revision=revision(candidate),plan_sha256=canonical_sha256(plan),issues=issues,
        comparison_basis='checked_pending_support_diagnostics',progressive_sha256=witness['sha256'],
        render_comparison='not_run',photo_comparison='not_run',metric_scale='estimated_not_measured',
        physical_authority=False)


def same_support_witness(left, right):
    """Only runtime telemetry may differ on exact local revalidation.

    A time-limited failed search can execute a different number of geometry
    probes at the SAME deadline. That count is not a geometry result. Other
    termination causes retain exact counts; domains, limits, IDs, risks, issue
    identities, search outcome and all geometry stay exact. Only comparison
    copies are normalized; the original witness and telemetry are retained.
    """
    def comparison(value):
        result=deepcopy(value)
        result.pop('sha256',None)
        for row in result.get('unresolved',[]):
            expected=row.get('evidence',{}).get('expected')
            if isinstance(expected,dict) and isinstance(expected.get('bounded_search'),dict):
                search=expected['bounded_search']
                search.pop('elapsed_s',None)
                if (search.get('schema_version')=='photo-support-bounded-search-1.0'
                        and search.get('status')=='BOUNDED_SEARCH_FAILED'
                        and search.get('termination_code')=='TIME_BUDGET_EXHAUSTED'):
                    count,limit=search.get('geometry_checks'),search.get('max_geometry_checks')
                    if (type(count) is not int or type(limit) is not int
                            or not 0<=count<=limit):
                        return None
                    search.pop('geometry_checks')
        return result
    first,second=comparison(left),comparison(right)
    return first is not None and second is not None and first==second
