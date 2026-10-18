# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Deterministic dependency edits of the existing saved tool plan.

Original observations remain in the draft. This state travels with the existing
scene-change history; it is neither a second project store nor motion authority.
"""
from copy import deepcopy
from dataclasses import dataclass, replace

from twinpulse_core import canonical_sha256, execute_site_tool_plan
from twinpulse_core.scene_tools import SceneToolCall
from twinpulse_core.site_tools import SiteCallEvidence, SiteToolPlan
from twinpulse_core.photo_placement import (checked_placement_contract,
    relocate_attached_children, validate_placement_plan)

PATCH_VERSION = 'scene-dependency-patch-1.0'
STRUCTURAL = {'create_floor', 'create_wall', 'place_predefined_agv', 'create_navigation_task'}


class CandidatePoseClearanceError(ValueError):
    """Only a NEW dependency candidate compile, never source replay/identity."""
    def __init__(self, error):
        super().__init__(str(error))
        self.diagnosis = deepcopy(error.diagnosis)


@dataclass(frozen=True)
class EffectiveScene:
    plan: SiteToolPlan
    site: object
    placement: dict | None
    inventory: dict
    refinement: dict | None = None

    def progressive(self, source):
        if source.progressive_twin is None and not any(
                r['status'] != 'render_pending' for r in self.inventory.values()):
            return None
        rows = list(deepcopy(self.inventory).values())
        unresolved = [dict(id=r['id'], parent_id=(r['placement'] or {}).get('parent_id'),
            code='SCENE_ITEM_REMOVED' if r['status'] == 'removed' else 'SCENE_ITEM_DEFERRED',
            reason=r['reason'], status=r['status'], impact='task_context_required')
            for r in rows if r['status'] != 'render_pending']
        # Retain original pending support evidence across common edits/Undo.
        # Re-evaluate conservative bounds against CURRENT parent geometry; if
        # that support is unavailable, uncertainty remains blocking, not safe.
        originals={r['id']:r for r in (source.progressive_twin or {}).get('unresolved',[])}
        parents={c.arguments['id']:c.arguments for c in self.plan.calls}
        by_id={r['id']:r for r in rows}
        from twinpulse_core.progressive_twin import pending_support_geometry
        for issue in unresolved:
            origin=originals.get(issue['id'])
            if origin is None:continue
            row=by_id[issue['id']]
            parameters={**row['original_parameters'],'placement':{k:v for k,v in (row['placement'] or {}).items() if k!='id'}}
            try:hazard,bounds=pending_support_geometry(parameters,parents[issue['parent_id']],parameters['placement']['part'])
            except (ValueError,KeyError,TypeError,AttributeError):hazard,bounds=origin['hazard'],[0.,8.]
            issue.update(hazard=hazard,bounds_z_m=bounds,source=deepcopy(origin['source']),evidence=deepcopy(origin['evidence']))
        body = dict(schema_version='progressive-twin-1.1', policy_version=(source.progressive_twin or {}).get(
                    'policy_version','progressive-acceptance-1.0'),
            source_sha256=canonical_sha256(source.to_dict()), plan_sha256=canonical_sha256(self.plan.to_dict()),
            inventory=rows, unresolved=unresolved,
            axes=dict(draft_ready='compiled_pending_runtime', sim_task_pass='not_run',
                real_task_ready='not_run', visual_review='needs_refinement' if unresolved else 'unmeasured_needs_review'),
            physical_authority=False)
        return {**body, 'sha256': canonical_sha256(body)}


def initial_state(source):
    relations = {r['id']:deepcopy(r) for r in (source.placement_contract or {}).get('relations', [])}
    calls = {c.arguments['id']:c for c in source.plan.calls if c.tool not in STRUCTURAL}
    inventory = {}
    for identity, call in calls.items():
        inventory[identity] = dict(id=identity, kind=call.arguments.get('kind', call.tool),
            original_parameters=deepcopy(call.arguments), tool_call=call.to_dict(),
            placement=relations.get(identity), status='render_pending', reason=None)
    if source.progressive_twin:
        issues = {r['id']:r for r in source.progressive_twin['unresolved']}
        for row in source.progressive_twin['inventory']:
            identity = row['id']; parameters = deepcopy(row['parameters'])
            placement = dict(id=identity, **parameters['placement'])
            inventory[identity] = dict(id=identity, kind=row['kind'], original_parameters=parameters,
                tool_call=calls[identity].to_dict() if identity in calls else None,
                placement=placement, status=row['status'],
                reason=issues[identity]['reason'] if identity in issues else None)
    return EffectiveScene(source.plan, source.site, deepcopy(source.placement_contract), inventory,deepcopy(source.draft_refinement))


def _compile(source, plan, placement, parent_revision):
    plan = SiteToolPlan.from_dict(plan.to_dict())
    if placement is not None:
        placement = checked_placement_contract(placement)
    validate_placement_plan(plan, placement)
    site = execute_site_tool_plan(plan, source=source.site.scene.source,
                                  source_ref=source.input_revision.digest)
    return replace(site, scene=replace(site.scene, parent_revision=parent_revision),
                   navigation_map=None, mission=None)


def with_plan(source, state, plan, parent_revision, *, placement=None):
    """Carry legacy local edits into the same current inventory and relations."""
    placement = deepcopy(state.placement if placement is None else placement)
    inventory = deepcopy(state.inventory)
    for call in plan.calls:
        if call.tool in STRUCTURAL: continue
        identity = call.arguments['id']
        if identity not in inventory:
            inventory[identity] = dict(id=identity, kind=call.arguments.get('kind', call.tool),
                original_parameters=deepcopy(call.arguments), placement=None,
                status='render_pending', reason=None, tool_call=call.to_dict())
        else:
            inventory[identity]['tool_call'] = call.to_dict()
    return EffectiveScene(plan, _compile(source, plan, placement, parent_revision), placement, inventory,deepcopy(state.refinement))


def checked_patch(value):
    if (not isinstance(value, dict) or set(value) != {'patch_version', 'edits'} or
            value['patch_version'] != PATCH_VERSION or not isinstance(value['edits'], list) or
            not 1 <= len(value['edits']) <= 16):
        raise ValueError('DEPENDENCY_PATCH_INVALID')
    seen = {}
    for index,edit in enumerate(value['edits']):
        if not isinstance(edit, dict): raise ValueError('DEPENDENCY_EDIT_INVALID')
        mode = edit.get('action')
        fields = {'action', 'target_id', 'reason'}
        if mode in {'change', 'add', 'restore', 'room'}: fields |= {'tool_call'}
        if mode in {'add', 'restore', 'reparent'}: fields |= {'placement'}
        if mode=='reparent' and 'tool_call' in edit: fields |= {'tool_call'}
        if (set(edit) != fields or mode not in {'change', 'add', 'restore', 'room', 'reparent', 'defer', 'remove'} or
                not isinstance(edit['target_id'], str) or
                not isinstance(edit['reason'], str) or not 1 <= len(edit['reason'].strip()) <= 300):
            raise ValueError('DEPENDENCY_EDIT_INVALID')
        if edit['target_id'] in seen:
            raise ValueError('DEPENDENCY_DUPLICATE_TARGET: '+edit['target_id'][:64]+' in edits['+
                str(seen[edit['target_id']])+'] and edits['+str(index)+']; one atomic final edit per target is required')
        seen[edit['target_id']]=index
        if 'tool_call' in edit:
            call = SceneToolCall.from_dict(edit['tool_call'])
            if call.arguments.get('id') != edit['target_id']:
                raise ValueError('DEPENDENCY_CALL_IDENTITY_CHANGED')
        if 'placement' in edit:
            if not isinstance(edit['placement'],dict) or edit['placement'].get('id') != edit['target_id']:
                raise ValueError('DEPENDENCY_PLACEMENT_IDENTITY_CHANGED')
    return deepcopy(value)


def _descendants(relations, targets):
    targets = set(targets)
    while True:
        additions = {r['id'] for r in relations.values() if r['parent_id'] in targets} - targets
        if not additions: return targets
        targets |= additions


def apply_patch_state(source, state, patch, parent_revision, *, candidate_compile=False):
    patch = checked_patch(patch)
    inventory = deepcopy(state.inventory)
    calls = {c.arguments['id']:c for c in state.plan.calls}
    original_calls = dict(calls)
    relations = {r['id']:deepcopy(r) for r in (state.placement or {}).get('relations', [])}
    # Include unmaterialized children when computing the dependency scope.
    all_relations = {i:deepcopy(r['placement']) for i,r in inventory.items() if r['placement']}
    explicit = {e['target_id'] for e in patch['edits']}
    affected = _descendants(all_relations, explicit)
    moved = set()
    for edit in patch['edits']:
        identity, action = edit['target_id'], edit['action']
        old = calls.get(identity)
        if action == 'room':
            call = SceneToolCall.from_dict(edit['tool_call'])
            if old is None or old.tool not in {'create_floor', 'create_wall'} or call.tool != old.tool or call.call_id != old.call_id:
                raise ValueError('DEPENDENCY_ROOM_SCOPE_INVALID')
            # A model may not silently overwrite any saved explicit measurement.
            for constraint in source.input_revision.measurement_constraints:
                if constraint.get('tool') == old.tool:
                    raise ValueError('DEPENDENCY_MEASURED_ROOM_LOCKED')
            calls[identity] = call; moved.add(identity); continue
        if old is not None and old.tool in STRUCTURAL:
            raise ValueError('DEPENDENCY_STRUCTURAL_SCOPE_REQUIRED')
        if action == 'add':
            if identity in inventory or identity in calls: raise ValueError('DEPENDENCY_ADD_ID_EXISTS')
            call = SceneToolCall.from_dict(edit['tool_call'])
            if call.tool in STRUCTURAL: raise ValueError('DEPENDENCY_ADD_STRUCTURAL_FORBIDDEN')
            inventory[identity] = dict(id=identity, kind=call.arguments.get('kind', call.tool),
                original_parameters=deepcopy(call.arguments), tool_call=call.to_dict(),
                placement=deepcopy(edit['placement']), status='render_pending', reason=None)
            calls[identity] = call
            if edit['placement']: relations[identity] = deepcopy(edit['placement'])
            continue
        if identity not in inventory: raise ValueError('DEPENDENCY_TARGET_ABSENT')
        row = inventory[identity]
        if action in {'defer', 'remove'}:
            # Keep original identity, parameters and last materialized command.
            for child in _descendants(all_relations, {identity}):
                if child in inventory:
                    inventory[child]['status'] = 'removed' if action == 'remove' else 'deferred'
                    inventory[child]['reason'] = edit['reason'] if child == identity else 'Parent ' + identity + ': ' + edit['reason']
                    calls.pop(child, None); relations.pop(child, None)
            continue
        if action == 'restore':
            if row['status'] == 'render_pending': raise ValueError('DEPENDENCY_RESTORE_ALREADY_RENDERED')
            call = SceneToolCall.from_dict(edit['tool_call'])
            if call.tool in STRUCTURAL or call.arguments.get('kind', call.tool) != row['kind']:
                raise ValueError('DEPENDENCY_RESTORE_IDENTITY_CHANGED')
            row.update(status='render_pending', reason=None, tool_call=call.to_dict(), placement=deepcopy(edit['placement']))
            calls[identity] = call
            if edit['placement']: relations[identity] = deepcopy(edit['placement'])
            continue
        if row['status'] != 'render_pending' or old is None:
            raise ValueError('DEPENDENCY_TARGET_NOT_MATERIALIZED')
        if action == 'change':
            call = SceneToolCall.from_dict(edit['tool_call'])
            if (call.tool != old.tool or call.call_id != old.call_id or
                    call.arguments.get('kind') != old.arguments.get('kind')):
                raise ValueError('DEPENDENCY_CHANGE_IDENTITY_CHANGED')
            if call==old: raise ValueError('DEPENDENCY_CHANGE_NO_OP')
            if old.tool=='place_model_recipe' and any(call.arguments.get(k)!=old.arguments.get(k)
                    for k in ('model_id','recipe_sha256','interpreter_version','recipe')):
                raise ValueError('DEPENDENCY_RECIPE_DEFINITION_CHANGED')
            if old.tool=='place_library_asset' and call.arguments.get('snapshot')!=old.arguments.get('snapshot'):
                raise ValueError('DEPENDENCY_ASSET_SNAPSHOT_CHANGED')
            calls[identity] = call; moved.add(identity)
        elif action == 'reparent':
            if old.tool != 'place_room_item' or edit['placement'] is None:
                raise ValueError('DEPENDENCY_REPARENT_UNSUPPORTED')
            row['placement'] = deepcopy(edit['placement']); relations[identity] = deepcopy(edit['placement'])
            if 'tool_call' in edit:
                replacement = SceneToolCall.from_dict(edit['tool_call'])
                if (replacement.tool != old.tool or replacement.call_id != old.call_id or
                        replacement.arguments.get('kind') != old.arguments.get('kind')):
                    raise ValueError('DEPENDENCY_REPARENT_IDENTITY_CHANGED')
                calls[identity] = replacement
            # Parent contact is computed from catalogue geometry; XY stays explicit.
            if edit['placement']['relation'] == 'surface':
                from twinpulse_core.photo_quality import support_surface
                parent = calls.get(edit['placement']['parent_id'])
                if parent is None: raise ValueError('DEPENDENCY_REPARENT_PARENT_ABSENT')
                surface = support_surface(parent.arguments, edit['placement']['part'])
                if surface is None: raise ValueError('DEPENDENCY_REPARENT_PART_ABSENT')
                args = deepcopy(calls[identity].arguments); args['position_m'][2] = surface.transform.position_m[2] + surface.shape.dimensions_m[2]/2 + args['dimensions_m'][2]/2
                calls[identity] = SceneToolCall(old.call_id, old.tool, args)
            moved.add(identity)
    if len({c.call_id for c in calls.values()}) != len(calls):
        raise ValueError('DEPENDENCY_CALL_ID_DUPLICATE')
    ordered = [calls[c.arguments['id']] for c in state.plan.calls if c.arguments['id'] in calls]
    ordered += [c for i,c in calls.items() if i not in original_calls]
    evidence = None
    if state.plan.call_evidence is not None:
        prior = {e.call_id:e for e in state.plan.call_evidence}
        evidence = tuple(SiteCallEvidence(c.call_id, (), 'user', 'Reviewed dependency edit')
            if c.arguments['id'] in explicit else prior.get(c.call_id,
                SiteCallEvidence(c.call_id, (), 'user', 'Reviewed dependency edit')) for c in ordered)
    from twinpulse_core.library_assets import edit_plan_version
    plan = SiteToolPlan(state.plan.scene_id, state.plan.summary, state.plan.image_observations,
        tuple(ordered), plan_version=edit_plan_version(state.plan,ordered),
        call_evidence=evidence)
    placement = None if state.placement is None and not relations else dict(
        schema_version=('photo-placement-contract-1.2' if state.placement and
            state.placement['schema_version']=='photo-placement-contract-1.2' else 'photo-placement-contract-1.1'),
        relations=list(relations.values()))
    # Topological propagation through nested supports. Explicit child geometry
    # wins over inherited movement; unchanged descendants follow each parent once.
    pending = set(moved); handled = set()
    while pending:
        ready = sorted(i for i in pending if all_relations.get(i, {}).get('parent_id') not in pending)
        if not ready: raise ValueError('DEPENDENCY_PLACEMENT_CYCLE')
        for identity in ready:
            pending.remove(identity); handled.add(identity)
            if identity not in original_calls or identity not in calls or placement is None: continue
            inherited = [r for r in placement['relations'] if r['parent_id'] == identity and r['id'] not in explicit]
            if inherited:
                # The helper validates the entire graph first, so include ancestors.
                moved_plan = relocate_attached_children(state.plan, plan, placement, original_calls[identity].call_id)
                allowed = {r['id'] for r in inherited}
                plan = replace(plan, calls=tuple(next(c for c in moved_plan.calls if c.call_id == old.call_id)
                    if old.arguments['id'] in allowed else old for old in plan.calls))
                calls = {c.arguments['id']:c for c in plan.calls}
                pending |= allowed - handled
    for identity, row in inventory.items():
        if identity in calls:
            row['tool_call'] = calls[identity].to_dict()
            if identity in relations: row['placement'] = deepcopy(relations[identity])
            if row['placement'] is not None and relations.get(identity)!=row['placement']:
                raise ValueError('DEPENDENCY_PLACEMENT_COVERAGE_MISSING')
    from twinpulse_core.furniture import FurniturePoseGeometryError
    try:
        compiled = _compile(source, plan, placement, parent_revision)
    except FurniturePoseGeometryError as error:
        if not candidate_compile:raise
        raise CandidatePoseClearanceError(error) from error
    return EffectiveScene(plan, compiled, placement, inventory,deepcopy(state.refinement)), affected


def public_progressive(source, state):
    value = state.progressive(source)
    if value is None: return None
    return {k:deepcopy(value[k]) for k in ('schema_version', 'policy_version', 'plan_sha256', 'axes', 'unresolved', 'physical_authority')} | dict(
        current=True, inventory_count=len(value['inventory']),
        materialized_count=sum(r['status'] == 'render_pending' for r in value['inventory']))
