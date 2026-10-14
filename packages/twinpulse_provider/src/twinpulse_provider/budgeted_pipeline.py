# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Opt-in staged semantic generation over ordinary registered stage transports.

Not a new engine, executable agent or alternate robot path. All final output is
lowered through existing typed Site2.2/executor/library checks before returning.
"""
from copy import deepcopy
from contextlib import nullcontext
import asyncio
import json
import time

from twinpulse_core import canonical_sha256
from twinpulse_core.model_library import library_for_request, LIBRARY_VERSION
from .contracts import ProviderResponse
from .errors import InvalidProviderResponseError, ProviderError, GenerationCancelledError
from .errors import ProviderConfigurationError
from .generation_policy import ExecutionBudget, GenerationBudgetError, ProgressTracker, diagnostic_blockers
from .generation_store import GenerationStore, input_digest
from .nebius_pipeline import (NebiusChatCompletionsPipelineProvider, ObservationArtifact,
    _json_content, _ensure_current, _validation_code)
from .semantic_scene import (checked_structure, structure_schema, batch_schema,
    scene_draft, checked_batch, compile_scene, patch_schema, apply_patch_candidate,
    revision, COMPILER_REVISION, patch_candidate, inventory_requirements,
    compiler_diagnosis, geometry_repair_context, review_candidate_quality)
from .semantic_bindings import (evidence_catalog, structure_repair_schema, repair_structure,
    structure_repair_context, batch_repair_schema, repair_batch, BINDING_REVISION, STRUCTURE_REPAIR_REVISION)
from .stage_transport import explicit_json_contract, WIRE_CONTRACT_REVISION
from .repair_scope import SCOPE_REVISION
from .render_review import RENDER_REVIEW_REVISION
from .scene_capacity import PARAMETER_BATCH_SIZE

QUALITY_REPAIR_REVISION = 'observed-quality-repair-1.1'


class BudgetedPipeline(NebiusChatCompletionsPipelineProvider):
    def __init__(self, *args, policy, store_root=None, route_sha256=None, observer_wire_policy=None, **kwargs):
        kwargs['max_repairs'] = 0  # our common owner, not independent legacy loops
        super().__init__(*args, **kwargs)
        self.policy = policy.validate()
        self.total_timeout_s = policy.total_timeout_s
        self.store = GenerationStore(store_root) if store_root else None
        self.route_sha256 = route_sha256
        self.observer_wire_policy = deepcopy(observer_wire_policy or {})
        self.observer_wire_policy['wire_contract_revision'] = WIRE_CONTRACT_REVISION

    def diagnostic_for(self, request_id):
        result = super().diagnostic_for(request_id)
        budget = getattr(self, '_budget', None)
        if result and budget is not None:
            result['budget'] = budget.snapshot()
            result.update(repair_count=budget.repairs, max_repairs=budget.policy.max_repairs)
        return result

    def body(self, name, schema, system, content):
        body = {'model': self.planner_model_id, 'temperature': 0,
            'max_tokens': self.stage_output_token_caps.get('planner', 20000),
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': name, 'strict': True, 'schema': schema}},
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': json.dumps(content, ensure_ascii=False)}]}
        if self.planner_template_no_thinking:
            body['chat_template_kwargs'] = {'enable_thinking': False}
        return explicit_json_contract(body)

    async def generate_feedback(self,request,token,config):
        """One planner-only proposal over the ordinary audited budget boundary."""
        from .scene_edit_provider import feedback_proposal_json_schema,feedback_generation_request,FEEDBACK_ATOMIC_EDIT_RULE
        if request.images or request.inference_scope is None:
            raise ProviderConfigurationError('FEEDBACK_REQUIRES_EXACT_ORDINARY_APPROVAL')
        if (config.base_url!='https://api.tokenfactory.nebius.com/v1/' or
                self.planner_model_id!='nvidia/nemotron-3-super-120b-a12b' or
                self.stage_output_token_caps.get('planner')!=40000 or self.policy.per_call_timeout_s!=300):
            raise ProviderConfigurationError('FEEDBACK_REQUIRES_APPROVED_SUPER_40K_300S_ROUTE')
        content=json.loads(request.prompt)
        context={k:v for k,v in content.items() if k!='environment_model_library'}
        feedback_generation_request(context,request.request_id)
        financial=request.inference_scope.bind(request,self.policy,self.route_sha256)
        budget=ExecutionBudget(self.policy,financial_owner=financial);self._budget=budget
        token.generation_budget=budget;token.generation_role='initial'
        self._diagnostic=dict(request_id=request.request_id,input_kind='text',status='running',sequence=0,
            attempts=[],repair_count=0,max_repairs=0,policy_sha256=self.policy.sha256)
        body=self.body('twinpulse_scene_feedback',feedback_proposal_json_schema(context),
            'Interpret ordinary human scene feedback using only the saved current plan, source inventory, support relations and library. '
            'Return schema-only one bounded dependency patch or exactly one clarification question. Do not output code, '
            'commands, full-scene replacement, robot/task edits, new measurements, or claim a photo was observed. '
            'For ambiguous target or metric extent ask one question. Preserve object IDs/kinds and unrelated objects. '
            'Move/resize uses a complete current tool call. Parent changes keep descendants attached. '
            'Every patch target_id is the object identity in inventory.id / tool_call.arguments.id, never tool_call.call_id. '
            'Keep the saved call_id in the complete tool_call. Return the exact context_sha256 enum from the response schema. '
            +FEEDBACK_ATOMIC_EDIT_RULE+' '
            +
            'Restore/add always provides explicit floor/surface/drape/wall/ceiling placement. '
            'Use a modest stated estimated change only when the user permits estimation. All proposals require validated preview and explicit Apply. '
            'Write human-readable output in the language of the user feedback.',content)
        completion=None;value=None

        def validation_evidence(record):
            recorder=getattr(self._transport,'record_validation',None)
            identity=(completion.attempt_id if completion else
                self._diagnostic['attempts'][-1].get('attempt_id') if self._diagnostic['attempts'] else None)
            if recorder and identity:
                try:
                    recorder('scene_feedback',identity,{**record,
                        'context_sha256':context['context_sha256'],'current_state_sha256':context['current_state_sha256']})
                except Exception as storage_error:
                    budget.stop('VALIDATION_EVIDENCE_FAILED')
                    if token.diagnostics:
                        trace=token.diagnostics.child('inference_evidence',role='storage',attempt_id=identity)
                        trace.finish('failed',error=storage_error,error_code='validation_record_failed')
                    raise ProviderConfigurationError('Feedback validation evidence could not be persisted: '+
                        type(storage_error).__name__) from storage_error
        try:
            completion=await asyncio.wait_for(self._complete_stage('scene_feedback',body,token,config),budget.timeout_for('initial'))
            _ensure_current(token)
            if completion.model_id!=body['model'] or completion.finish_reason!='stop':
                raise InvalidProviderResponseError('Feedback model mismatch or truncated output; no retry')
            value=_json_content(completion,'scene_feedback')
            if (not isinstance(value,dict) or set(value)!={'schema_version','context_sha256','mode','explanation','patch'} or
                    value['schema_version']!='scene-edit-proposal-1.1'):
                error=InvalidProviderResponseError('Feedback proposal shape changed');error.code='FEEDBACK_SHAPE_INVALID';raise error
            if value['context_sha256']!=context['context_sha256']:
                error=InvalidProviderResponseError('Feedback proposal context changed');error.code='FEEDBACK_CONTEXT_MISMATCH';raise error
            # Identity is checked, never translated from a call_id to an ID.
            # Geometry/support and the explicit target scope remain App gates.
            edits=(value.get('patch') or {}).get('edits',[]) if isinstance(value.get('patch'),dict) else []
            seen={}
            for index,edit in enumerate(edits if isinstance(edits,list) else []):
                target=edit.get('target_id') if isinstance(edit,dict) else None
                if isinstance(target,str):
                    if target in seen:
                        error=InvalidProviderResponseError('Feedback target '+target[:64]+' appears in edits['+str(seen[target])+'] and edits['+
                            str(index)+']; emit one atomic final edit per target. Unchanged placement needs no second edit.')
                        error.code='FEEDBACK_DUPLICATE_TARGET';raise error
                    seen[target]=index
                if isinstance(edit,dict) and isinstance(edit.get('tool_call'),dict):
                    args=edit['tool_call'].get('arguments')
                    if not isinstance(args,dict) or edit.get('target_id')!=args.get('id'):
                        error=InvalidProviderResponseError('Feedback target must be the object ID, not call_id')
                        error.code='FEEDBACK_OBJECT_IDENTITY_MISMATCH';raise error
            validation_evidence(dict(validation='passed',candidate=value))
            self._diagnostic['status']='proposal_received';budget.stop('FEEDBACK_PROPOSAL_RECEIVED')
            return ProviderResponse(request.request_id,value,self.name,completion.model_id,
                dict(budget=budget.snapshot(),context_sha256=context['context_sha256']))
        except TimeoutError as error:
            token.cancel();budget.stop('REMOTE_OUTCOME_UNKNOWN')
            from .errors import ProviderTimeoutError
            raise ProviderTimeoutError('Feedback deadline exceeded; remote outcome unknown, no retry') from error
        except GenerationCancelledError as error:
            attempt=self._diagnostic['attempts'][-1] if self._diagnostic['attempts'] else {}
            received=attempt.get('status')=='received'
            code='FEEDBACK_CANCELLED_AFTER_RECEIPT' if received else 'FEEDBACK_CANCELLED'
            self._diagnostic.update(status='cancelled',validation_code=code)
            attempt.update(validation='failed',validation_code=code,cancelled=True,ignored_by_host=True)
            try:
                validation_evidence(dict(validation='failed',candidate=value,validation_code=code,
                    validation_detail='Cancelled output was ignored; no preview or apply.',
                    response_received=received,cancelled=True,role='initial'))
            except Exception as storage_error:
                error.evidence_error_type=type(storage_error).__name__
                error.diagnostics=self.diagnostic_for(request.request_id)
                raise error from storage_error
            budget.stop('FEEDBACK_CANCELLED');raise
        except InvalidProviderResponseError as error:
            code=_validation_code(error)
            self._diagnostic.update(status='validation_failed',validation_code=code)
            if self._diagnostic['attempts']:
                self._diagnostic['attempts'][-1].update(validation='failed',validation_code=code)
            try:
                validation_evidence(dict(validation='failed',candidate=value,
                    validation_code=code,validation_detail=str(error),role='initial'))
            except Exception as storage_error:
                error.evidence_error_type=type(storage_error).__name__
                error.diagnostics=self.diagnostic_for(request.request_id)
                raise error from storage_error
            budget.stop('FEEDBACK_FAILED');raise
        except Exception:
            budget.stop('FEEDBACK_FAILED');raise

    async def generate(self, request, token, config):
        if request.schema_version=='scene-edit-proposal-1.1':
            return await self.generate_feedback(request,token,config)
        if len(request.images) > 1 or self.site_plan_version != '2.2':
            raise InvalidProviderResponseError('Semantic generation supports text or one image in Site2.2')
        # An internal approved adapter can bind financial/input/model scope.
        # No host evaluation ledger is imported or looked up automatically.
        scope = request.inference_scope
        render_review = bool(request.images and self.policy.external_final_review)
        if render_review:
            if not getattr(scope, 'approved_render_review', False) or request.render_review_port is None:
                raise ProviderConfigurationError('CURRENT_RENDER_REVIEW_REQUIRES_APPROVAL_AND_ENGINE')
            request.render_review_port.preflight()
        parent = None
        if request.continuation_checkpoint:
            if not self.store or not scope:
                raise ProviderConfigurationError('CONTINUATION_REQUIRES_CURRENT_APPROVAL')
            parent = self.store.read('checkpoint', request.continuation_checkpoint)
            if (not parent or canonical_sha256(parent) != getattr(scope, 'approved_checkpoint_sha256', None)
                    or parent.get('input_sha256') != input_digest(request)
                    or parent.get('approval_id') == getattr(scope, 'approval_id', None)
                    or parent.get('request_id') == request.request_id):
                raise ProviderConfigurationError('CONTINUATION_APPROVAL_MISMATCH')
            old_budget = parent.get('budget', {})
            if (old_budget.get('in_flight') or any(not row.get('settled') or row.get('status') == 'outcome_unknown'
                    for row in old_budget.get('attempts', []))):
                raise ProviderConfigurationError('CONTINUATION_REMOTE_OUTCOME_UNKNOWN')
            if parent.get('draft') and parent['draft'].get('schema_version') != 'semantic-scene-1.0':
                raise ProviderConfigurationError('CONTINUATION_SCHEMA_UNSUPPORTED')
            if parent.get('geometry_progress'):
                if (parent.get('compiler_revision')!=COMPILER_REVISION or
                    parent.get('library_revision')!=LIBRARY_VERSION):
                    raise ProviderConfigurationError('CONTINUATION_DEPENDENCY_REVISION_CHANGED')
                ProgressTracker.restore(parent['geometry_progress'])
            elif parent.get('best_candidate'):
                raise ProviderConfigurationError('CONTINUATION_PROGRESS_HISTORY_UNAVAILABLE')
            if old_budget.get('stalled_repairs',0)>=self.policy.stalled_repairs:
                raise ProviderConfigurationError('CONTINUATION_STALLED_POLICY_EXHAUSTED')
            if parent.get('quality_progress',{}).get('history') and (
                    parent.get('scope_revision')!=SCOPE_REVISION or
                    parent.get('quality_repair_revision')!=QUALITY_REPAIR_REVISION):
                raise ProviderConfigurationError('CONTINUATION_QUALITY_REVISION_CHANGED')
            if parent.get('render_history') and parent.get('render_review_revision')!=RENDER_REVIEW_REVISION:
                raise ProviderConfigurationError('CONTINUATION_RENDER_REVIEW_REVISION_CHANGED')
        financial = scope.bind(request, self.policy, self.route_sha256) if scope else None
        budget = ExecutionBudget(self.policy, financial_owner=financial)
        if parent:
            previous = parent['budget']
            budget.prior_executions = deepcopy(previous.get('prior_executions', [])) + [{
                'request_id': parent['request_id'], 'checkpoint_id': request.continuation_checkpoint,
                'policy_sha256': previous['policy_sha256'], 'requests': previous['requests'],
                'repairs': previous['repairs'], 'elapsed_s': previous['elapsed_s'],
                'stop_reason': previous['stop_reason'],
                **({'cost': deepcopy(previous['cost'])} if 'cost' in previous else {})}]
            budget.repairs=previous['repairs']
            budget.carried_repairs=previous['repairs']
            budget.no_progress=previous.get('stalled_repairs',0)
            budget.repair_used_s=previous.get('repair_used_s',0)
            budget.final_used_s=previous.get('final_used_s',0)
            budget.carried_requests=previous.get('cumulative_requests',previous['requests'])
            budget.carried_elapsed_s=previous.get('cumulative_active_s',previous['elapsed_s'])
        self._budget = budget
        token.generation_budget = budget
        self._diagnostic = {'request_id': request.request_id, 'input_kind': 'photo' if request.images else 'text',
            'status': 'running', 'sequence': 0, 'attempts': [], 'repair_count': 0,
            'max_repairs': self.policy.max_repairs, 'policy_sha256': self.policy.sha256}
        self._stage_started = time.monotonic()
        checkpoints = deepcopy(parent.get('completed_stages', [])) if parent else []
        draft = deepcopy(parent.get('draft')) if parent else None
        room_seed = deepcopy(parent.get('room_seed')) if parent else None
        structure_observation = (ObservationArtifact.from_mapping(parent['structure_observation'])
            if parent and parent.get('structure_observation') else None)
        pending_parameter_candidates=deepcopy(parent.get('pending_parameter_candidates',{})) if parent else {}
        # Only the hash-approved local checkpoint can carry host-expanded1.3;
        # raw observer/cache responses still use the default wire validator.
        observation = ObservationArtifact.from_mapping(parent['observation'],allow_derived=True) if parent and parent.get('observation') else None
        source_observation=deepcopy(parent.get('source_observation')) if parent else None
        instance_grounding=deepcopy(parent.get('instance_grounding')) if parent else None
        if parent:
            self._diagnostic['parent_checkpoint_id'] = request.continuation_checkpoint
            if draft:
                # Source/library changes must revalidate, not trust a prior ready
                # flag. Existing final scenes in the App remain protected.
                checked_structure({k: draft[k] for k in ('summary', 'room', 'inventory')}, request, observation)
                draft = checked_batch(draft['objects'], {**draft, 'objects': {}}, list(draft['objects']))
                draft['state'] = 'DRAFT_INCOMPLETE'
        checkpoint_key = canonical_sha256({'request_id': request.request_id, 'input': input_digest(request)})
        patches = deepcopy(parent.get('patches',[])) if parent else []
        repair_failures = deepcopy(parent.get('repair_failures', [])) if parent else []
        best_candidate = deepcopy(parent.get('best_candidate')) if parent else None
        best_diagnosis = deepcopy(parent.get('best_diagnosis')) if parent else None
        best_preview = deepcopy(parent.get('best_preview_snapshot')) if parent else None
        tracker = ProgressTracker.restore(parent['geometry_progress']) if parent and parent.get('geometry_progress') else ProgressTracker()
        quality_tracker = ProgressTracker.restore(parent['quality_progress']) if parent and parent.get('quality_progress') else ProgressTracker()
        quality_best = deepcopy(parent.get('quality_best')) if parent else None
        quality_best_review = deepcopy(parent.get('quality_best_review')) if parent else None
        quality_preview = deepcopy(parent.get('quality_preview_snapshot')) if parent else None
        payload = None
        draft_refinement = None
        render_history = deepcopy(parent.get('render_history', [])) if parent else []
        preview_capture = None
        preview_captures = {}
        preview_plan = deepcopy(parent.get('preview_plan')) if parent else None
        if parent and parent.get('generation_preview'):
            self._diagnostic['generation_preview']=deepcopy(parent['generation_preview'])
            self._diagnostic['generation_preview'].update(state='blocked',error_code='PREVIEW_REBUILD_REQUIRED')
        if parent and best_candidate is not None:
            # Old checkpoints may have stored a partial best while their
            # tracker rejected its official partial ledger status. Recompute
            # evidence locally; do not infer PASS from saved flags or reset debt.
            try:
                with (token.diagnostics.span('best_local_revalidation') if token.diagnostics else nullcontext()):
                    _, checked_best=compile_scene(best_candidate,observation,request,progressive=True)
                tracker.rebind_locally_checked_best(best_candidate,checked_best)
                best_diagnosis={**checked_best,'issues':[]}
                self._diagnostic['best_local_revalidation']={
                    'candidate_revision':revision(best_candidate),'external_call':False,
                    'checks_complete':checked_best.get('checks_complete') is True,
                    'materialized_subset_checked':checked_best.get('materialized_subset_checked') is True}
            except (ValueError,InvalidProviderResponseError,ProviderConfigurationError) as revalidation_error:
                self._diagnostic['best_local_revalidation']={
                    'candidate_revision':revision(best_candidate),'external_call':False,
                    'error_code':str(revalidation_error).split(':',1)[0]}

        def checkpoint(state, error=None):
            from .scene_contract import role_of
            raw = source_observation or (observation.to_dict() if observation else None)
            declared = sum((row.get('instance_count') or 1) for row in raw['entities']
                if role_of(row) in {'object','unknown'}) if raw else 0
            pending = [row['id'] for row in draft['inventory'] if row['id'] not in draft['objects']] if draft else []
            parameterized = len(draft['objects']) if draft else 0
            progress = dict(schema_version='inventory-work-progress-1.0',observed_instances=declared,
                inventory_count=len(draft['inventory']) if draft else 0,parameterized_count=parameterized,
                pending_count=len(pending) if draft else declared,inventory_planned=draft is not None,
                parameter_batch_size=PARAMETER_BATCH_SIZE,parameters_complete=bool(draft is not None and not pending),
                checkpoint_saved=False,observation_saved=False,draft_saved=False,
                automatic_resume=False,physical_authority=False)
            self._diagnostic['inventory_progress']=deepcopy(progress)
            if self.store:
                progress['checkpoint_saved']=True
                progress['observation_saved']=observation is not None
                progress['draft_saved']=draft is not None
                self.store.save('checkpoint', checkpoint_key, {
                    'request_id': request.request_id, 'input_sha256': input_digest(request),
                    'route_sha256': self.route_sha256, 'policy': self.policy.to_dict(),
                    'approval_id': getattr(scope, 'approval_id', None),
                    'parent_checkpoint_id': request.continuation_checkpoint,
                    'compiler_revision': COMPILER_REVISION, 'library_revision': LIBRARY_VERSION,
                    'binding_revision': BINDING_REVISION, 'wire_contract_revision': WIRE_CONTRACT_REVISION,
                    'structure_repair_revision': STRUCTURE_REPAIR_REVISION,
                    'scope_revision': SCOPE_REVISION, 'quality_repair_revision': QUALITY_REPAIR_REVISION,
                    'render_review_revision': RENDER_REVIEW_REVISION, 'render_history': render_history,
                    'render_capture': deepcopy(self._diagnostic.get('render_capture')),
                    'generation_preview':deepcopy(self._diagnostic.get('generation_preview')),
                    'preview_render_key':canonical_sha256(preview_capture['metadata']) if preview_capture else None,
                    'preview_plan':deepcopy(preview_plan),
                    'state': state, 'draft': draft, 'room_seed': room_seed,
                    'structure_observation':structure_observation.to_dict() if structure_observation else None,
                    'pending_parameter_candidates':pending_parameter_candidates,'budget': budget.snapshot(),
                    'best_candidate': best_candidate, 'best_diagnosis': best_diagnosis,
                    'best_preview_snapshot': best_preview, 'quality_preview_snapshot': quality_preview,
                    'geometry_progress':tracker.snapshot(),
                    'quality_progress':quality_tracker.snapshot(),
                    'quality_best':quality_best,
                    'quality_best_review':quality_best_review,
                    'scope_decision':deepcopy(self._diagnostic.get('scope_decision')),
                    'working_branch':deepcopy(self._diagnostic.get('repair_decision')),
                    'local_revalidation':deepcopy(self._diagnostic.get('local_revalidation')),
                    'best_local_revalidation':deepcopy(self._diagnostic.get('best_local_revalidation')),
                    'rollback_revalidation':deepcopy(self._diagnostic.get('rollback_revalidation')),
                    'quality_review':deepcopy(self._diagnostic.get('quality_review')),
                    'progressive_twin':deepcopy(self._diagnostic.get('progressive_twin')),
                    'draft_refinement':deepcopy(draft_refinement),
                    'stage_acceptance':deepcopy(self._diagnostic.get('stage_acceptance')),
                    'completed_stages': checkpoints, 'error_code': error,
                    'patches': patches,
                    'repair_failures': repair_failures,
                    'compiled_plan': payload if state == 'APPROXIMATE_TWIN_READY' else None,
                    'plan_sha256': canonical_sha256(payload) if state == 'APPROXIMATE_TWIN_READY' else None,
                    'observation': observation.to_dict() if observation else None,
                    'source_observation': source_observation,'instance_grounding':instance_grounding,
                    'inventory_progress':progress,'pending_parameter_ids':pending,
                    'automatic_resume': False, 'Build': 'PREVIEW_ONLY' if render_history or self._diagnostic.get('render_capture') or preview_plan is not None else 'NOT_RUN',
                    'Run': 'NOT_RUN', 'physical_authority': False})
                self._diagnostic['checkpoint_id'] = checkpoint_key
                self._diagnostic['inventory_progress']=deepcopy(progress)
            if token.diagnostics:
                snapshot = budget.snapshot()
                token.diagnostics.bind(policy_sha256=self.policy.sha256,
                    checkpoint_id=checkpoint_key, parent_checkpoint_id=request.continuation_checkpoint,
                    requests=snapshot['requests'], repairs=snapshot['repairs'],
                    max_requests=snapshot['max_requests'], max_repairs=snapshot['max_repairs'],
                    elapsed_s=snapshot['elapsed_s'], stop_reason=snapshot['stop_reason'])
                if payload is not None and state == 'APPROXIMATE_TWIN_READY':
                    token.diagnostics.bind(plan_sha256=canonical_sha256(payload), semantic_revision=revision(draft))

        def remember_preview():
            from .candidate_preview import snapshot_preview
            return snapshot_preview(draft, preview_plan, preview_capture,
                                    self._diagnostic.get('generation_preview'))

        def restore_preview(saved):
            nonlocal preview_plan, preview_capture
            from .candidate_preview import checked_preview_snapshot
            restored = checked_preview_snapshot(draft, saved)
            # The failed candidate's render review must not describe best.
            self._diagnostic.pop('render_capture', None)
            self._diagnostic.pop('render_review', None)
            preview_plan = preview_capture = None
            if restored is None:
                from .generation_preview import compile_generation_preview
                try:
                    preview_plan, _, progress = compile_generation_preview(draft, observation, request)
                    progress.update(state='blocked', error_code='PREVIEW_REBUILD_REQUIRED')
                    self._diagnostic['generation_preview'] = progress
                except (ValueError, InvalidProviderResponseError):
                    self._diagnostic.pop('generation_preview', None)
                return
            preview_plan = restored['plan']
            progress = restored['progress']
            key = restored['render_key']
            preview_capture = deepcopy(preview_captures.get(key))
            if preview_capture is None and key and self.store:
                row = self.store.read('render', key)
                if row and row.get('metadata') == restored['capture_metadata']:
                    import base64
                    preview_capture = dict(metadata=deepcopy(row['metadata']), plan=deepcopy(preview_plan),
                        jpeg=base64.b64decode(row['jpeg_base64'], validate=True))
            # This restores a static, exact candidate/capture pair. Actual
            # current authority is reacquired by the normal Build on resume.
            self._diagnostic['generation_preview'] = progress

        async def publish_preview(plan=None):
            nonlocal preview_capture, preview_plan
            port=request.render_review_port
            if (draft is None and room_seed is None) or port is None or not getattr(port,'supports_incremental_preview',False):
                return
            _ensure_current(token)
            previous=deepcopy(self._diagnostic.get('generation_preview'))
            candidate_revision=revision(draft) if draft else canonical_sha256(room_seed)
            preview_observation = observation or structure_observation
            total=len(draft['inventory']) if draft else sum(1 for row in preview_observation.entities
                if __import__('twinpulse_provider.scene_contract',fromlist=['role_of']).role_of(row) in ('object','unknown'))
            counts=dict(rendered_count=0,pending_count=total,inventory_count=total)
            try:
                from .generation_preview import compile_generation_preview
                if plan is None:
                    if draft is None:
                        from .generation_preview import compile_room_seed
                        plan,progress=compile_room_seed(room_seed,preview_observation,request)
                    else:
                        plan,_,progress=compile_generation_preview(draft,observation,request)
                else:
                    shown={call['arguments'].get('id') for call in plan['calls']}&{row['id'] for row in draft['inventory']}
                    progress=dict(schema_version='generation-preview-1.0',state='building',
                        candidate_revision=revision(draft),scene_revision=None,rendered_count=len(shown),
                        pending_count=len(draft['inventory'])-len(shown),inventory_count=len(draft['inventory']),
                        preview_only=True,physical_authority=False)
                counts={key:progress[key] for key in counts}
                if previous and previous.get('rendered_count',0)>0 and progress['rendered_count']==0:
                    previous.update(state='blocked',error_code='NO_VALID_OBJECT_PREVIEW')
                    self._diagnostic['generation_preview']=previous
                    return
                if (preview_capture and preview_capture['metadata']['plan_sha256']==canonical_sha256(plan)
                        and preview_capture['metadata']['candidate_revision']==candidate_revision):
                    port.assert_current(preview_capture['metadata'])
                    progress.update(state='ready',scene_revision=preview_capture['metadata']['scene_revision'])
                    self._diagnostic['generation_preview']=progress
                    return
                self._diagnostic['generation_preview']=progress
                activity('building')
                if port.engine_identity is None:
                    port.preflight()
                role='final_review' if budget.initial_closed else 'initial'
                # Local previews consume wall time but no HTTP/repair slot.
                timeout=budget.timeout_for(role)
                started=time.monotonic()
                try:
                    with (token.diagnostics.span('generation_preview',component='application',
                            candidate_revision=candidate_revision) if token.diagnostics else nullcontext()):
                        capture=await port.capture(plan,candidate_revision,token,timeout)
                finally:
                    if role=='final_review':budget.final_used_s+=max(0,time.monotonic()-started)
                _ensure_current(token)
                capture['plan']=deepcopy(plan)
                preview_capture=capture;preview_plan=deepcopy(plan)
                preview_captures[canonical_sha256(capture['metadata'])] = deepcopy(capture)
                progress.update(state='ready',scene_revision=capture['metadata']['scene_revision'])
                activity('ready')
                self._diagnostic['generation_preview']=progress
                if self.store:
                    import base64
                    self.store.save('render',canonical_sha256(capture['metadata']),
                        {'metadata':capture['metadata'],'jpeg_base64':base64.b64encode(capture['jpeg']).decode('ascii')})
            except GenerationCancelledError:
                raise
            except (InvalidProviderResponseError,ValueError,ProviderConfigurationError,GenerationBudgetError) as error:
                _ensure_current(token)
                # A failed newer candidate keeps the previous display receipt.
                # Never turn preview failure into full geometry/quality PASS.
                code=_validation_code(error)
                if code=='PROVIDER_VALIDATION_FAILED':
                    import re
                    match=re.match(r'^([A-Z][A-Z0-9_]{1,79})(?=[: ]|$)',str(error))
                    if match:code=match.group(1)
                progress=previous or dict(schema_version='generation-preview-1.0',candidate_revision=candidate_revision,
                    scene_revision=None,preview_only=True,physical_authority=False,**counts)
                progress.update(state='blocked',error_code=code)
                activity('blocked',reason_codes=[code])
                self._diagnostic['generation_preview']=progress
                if port.broker.has_pending_operations():
                    # Unknown/running Build must settle before any further work.
                    budget.stop('PREVIEW_BUILD_OUTCOME_PENDING')
                    raise

        def validation_evidence(name, completion, record):
            recorder = getattr(self._transport, 'record_validation', None)
            identity = (completion.attempt_id if completion else
                self._diagnostic['attempts'][-1].get('attempt_id') if self._diagnostic['attempts'] else None)
            if identity is None:
                # A resumed checkpoint is recompiled BEFORE new HTTP. Keep
                # this local evidence in its checkpoint, not a fake paid ID.
                self._diagnostic['local_revalidation']={'name':name,'record':deepcopy(record),
                    'parent_checkpoint_id':request.continuation_checkpoint,'external_call':False}
            if recorder and identity:
                try:
                    recorder(name, identity, record)
                except Exception as storage_error:
                    budget.stop('VALIDATION_EVIDENCE_FAILED')
                    if token.diagnostics:
                        failure_trace = token.diagnostics.child('inference_evidence', role='storage', attempt_id=identity)
                        failure_trace.finish('failed', error=storage_error, error_code='validation_record_failed')
                    raise ProviderConfigurationError('Validation evidence could not be persisted: '+
                        type(storage_error).__name__) from storage_error

        def activity(phase, *, stage_name=None, **facts):
            previous=self._diagnostic.get('generation_activity',{})
            name=stage_name or self._diagnostic.get('stage','preparing')
            kept={k:v for k,v in previous.items() if k in ('batch_index','batch_total','affected_ids','reason_codes')
                and previous.get('stage')==name}
            self._diagnostic['generation_activity']=dict(schema_version='generation-activity-1.0',
                stage=name,phase=phase,**{**kept,**facts})

        async def stage(name, body, validator, role='initial'):
            token.generation_role = role
            token.validation_candidate = None
            _ensure_current(token)
            timeout = budget.timeout_for(role)
            self._diagnostic['stage'] = name
            activity('waiting_model',stage_name=name)
            completion = None
            value = None
            try:
                # Actual ordinary audited workers reserve/settle exactly where
                # HTTP begins/ends, including late settlement after cancellation.
                completion = await asyncio.wait_for(self._complete_stage(name, body, token, config), timeout)
                _ensure_current(token)
                if completion.model_id != body['model']:
                    error = InvalidProviderResponseError('PROVIDER_MODEL_MISMATCH')
                    error.repairable = False
                    raise error
                if completion.finish_reason != 'stop':
                    error = InvalidProviderResponseError('Chat Completions output was truncated'
                        if completion.finish_reason == 'length' else 'Unsupported finish reason')
                    error.repairable = False
                    error.code = ('PROVIDER_OUTPUT_TRUNCATED' if completion.finish_reason == 'length'
                                  else 'PROVIDER_FINISH_UNSUPPORTED')
                    raise error
                value = _json_content(completion, name)
                activity('validating',stage_name=name)
                trace = token.diagnostics
                with (trace.span('semantic_validation', semantic_stage=name) if trace else nullcontext()):
                    result = validator(value)
                self._diagnostic.update(status='validated', validator='passed')
                activity('ready',stage_name=name)
                for key in ('scene_contract', 'validation_code'):
                    self._diagnostic.pop(key, None)
                self._diagnostic['attempts'][-1]['validation'] = 'passed'
                if name=='repair':
                    self._diagnostic['attempts'][-1].update(patch_shape='passed',patch_effect='changed',
                        candidate_validation='pending')
                validation_evidence(name, completion, {'validation': 'passed', 'candidate': value,
                    'validation_candidate': token.validation_candidate,
                    'role': role, 'repair_context': getattr(token, 'repair_context', None)})
                return result
            except TimeoutError as error:
                budget.stop('REMOTE_OUTCOME_UNKNOWN')
                token.cancel()
                from .errors import ProviderTimeoutError
                failure = ProviderTimeoutError('Per-call deadline exceeded; remote outcome unknown')
                failure.per_call_timeout_s = timeout
                failure.diagnostics = self.diagnostic_for(request.request_id)
                raise failure from error
            except InvalidProviderResponseError as error:
                if value is None and hasattr(validator, 'repair_base_candidate'):
                    # Parsing failure is a failed PATCH, not a reason to discard
                    # a parsed base and ask for a whole-stage replacement.
                    error.candidate_value = deepcopy(validator.repair_base_candidate)
                    error.repair_base_diagnosis = deepcopy(validator.repair_base_diagnosis)
                if value is not None and not hasattr(error, 'candidate_value'):
                    error.candidate_value = value
                code = _validation_code(error)
                activity('blocked',stage_name=name,reason_codes=[code])
                self._diagnostic.update(status='validation_failed', validation_code=code)
                diagnosis = getattr(error, 'contract_report', {})
                if diagnosis:
                    self._diagnostic['scene_contract'] = deepcopy(diagnosis)
                self._diagnostic['attempts'][-1].update(validation='failed', validation_code=code)
                if name=='repair':
                    self._diagnostic['attempts'][-1].update(patch_effect='no_change' if code=='SEMANTIC_PATCH_NO_CHANGE' else 'failed',
                        patch_shape='passed' if code=='SEMANTIC_PATCH_NO_CHANGE' else 'failed',candidate_validation='pending')
                try:
                    validation_evidence(name, completion, {'validation': 'failed', 'candidate': value,
                        'validation_candidate': getattr(error, 'candidate_value', value),
                        'repair_base_diagnosis': getattr(error, 'repair_base_diagnosis', None),
                        'validation_code': code, 'validation_detail': str(error), 'diagnosis': diagnosis, 'role': role,
                        'repair_context': getattr(token, 'repair_context', None)})
                except Exception as storage_error:
                    error.evidence_error_type = type(storage_error).__name__
                    budget.stop('VALIDATION_EVIDENCE_FAILED')
                    error.diagnostics = self.diagnostic_for(request.request_id)
                    raise error from storage_error
                if code == 'PROVIDER_OUTPUT_TRUNCATED':
                    budget.stop('PROVIDER_OUTPUT_TRUNCATED')
                    self._diagnostic['stop_reason'] = 'output_limit_reached'
                elif getattr(error, 'repairable', True) is False:
                    budget.stop(code)
                error.diagnostics = self.diagnostic_for(request.request_id)
                raise

        def targeted_repair(schema, apply, validate, name, context):
            if schema is None:
                return None
            repair_body = self.body(name, schema,
                'Return only the typed correction allowed by this schema, not a whole candidate. '
                'Use the exact base revision. Leave valid items unchanged. Preserve every observed object. '
                'Combine all errors of one target into one coherent final change; do not create a text duplicate '
                'of a photographed object. A later validation may ask to revise the same target again. '
                'Estimates are not measurements. No executable tools or robot authority.', context)

            def validate_repair(value):
                try:
                    candidate = apply(value)
                except InvalidProviderResponseError as error:
                    error.repair_base_diagnosis = deepcopy(context['validation'])
                    raise
                token.validation_candidate = deepcopy(candidate)
                try:
                    return validate(candidate)
                except InvalidProviderResponseError as error:
                    error.candidate_value = deepcopy(candidate)
                    raise
            validate_repair.repair_base_candidate = deepcopy(context['previous_candidate'])
            validate_repair.repair_base_diagnosis = deepcopy(context['validation'])
            validate_repair.repair_mode = ('targeted_keyed_changes' if context.get('structure_repair')
                                           else 'targeted_operations')
            validate_repair.repair_contract = deepcopy(context.get('structure_repair'))
            return repair_body, validate_repair

        async def content_stage(name, body, validator, initial_role='initial', repair_factory=None, on_invalid=None):
            # Malformed complete observer/structure/batch is repaired only in
            # that small contract, using the same shared repair counter.
            progress = ProgressTracker()
            repairing = False
            original_body = deepcopy(body)
            original_validator = validator
            token.repair_context = None
            while True:
                try:
                    return await stage(name, body, validator, 'repair' if repairing else initial_role)
                except InvalidProviderResponseError as error:
                    if budget.terminal or getattr(error, 'repairable', True) is False:
                        raise
                    diagnosis = getattr(error, 'repair_base_diagnosis', getattr(error, 'contract_report', {}))
                    if not diagnosis or not diagnosis.get('issues'):
                        from .scene_contract import report, issue
                        # Complete parsed JSON can fail a legacy validator
                        # without a typed path. Retain its concrete rule in the
                        # stage correction; never send an empty validation.
                        diagnosis=report([issue(_validation_code(error),'$',
                            detail=str(error)[:512],stage=name)])
                    blockers = diagnostic_blockers(diagnosis, _validation_code(error))
                    # Only parsed contract JSON is repair context, never the
                    # provider's reasoning or unparsed completion text.
                    candidate = getattr(error, 'candidate_value', None)
                    if on_invalid is not None:
                        await on_invalid(candidate,diagnosis)
                    progressed = progress.observe(candidate, blockers)
                    try:
                        validation_evidence('repair_decision', None, {'stage': name,
                            'candidate_sha256': canonical_sha256(candidate), 'remaining_targets': blockers,
                            'progressed': progressed, 'repair_context': getattr(token, 'repair_context', None)})
                    except Exception as storage_error:
                        error.evidence_error_type = type(storage_error).__name__
                        raise error from storage_error
                    if repairing or initial_role == 'repair':
                        budget.repair_result(progressed=progressed)
                    if budget.repairs >= self.policy.max_repairs:
                        raise GenerationBudgetError('REPAIR_LIMIT_REACHED') from error
                    budget.timeout_for('repair')
                    repairing = True
                    body, validator = deepcopy(original_body), original_validator
                    token.repair_context = {'previous_attempt_id': self._diagnostic['attempts'][-1].get('attempt_id'),
                        'previous_candidate_sha256': canonical_sha256(candidate),
                        'remaining_targets': blockers, 'progressed': progressed}
                    feedback_content = {'correct_stage': name, 'previous_candidate': candidate,
                        'previous_attempt_id': token.repair_context['previous_attempt_id'],
                        'validation': diagnosis, 'remaining_targets': blockers,
                        'failed_patch_validation': (getattr(error, 'contract_report', None)
                            if hasattr(error, 'repair_base_diagnosis') else None),
                        'error_code': _validation_code(error), 'instruction':
                        'Return only this corrected stage contract. Fix all listed errors. '
                        'Do not omit visible objects, invent measurements, execute tools or change provider.'}
                    adapted = repair_factory(candidate, diagnosis) if repair_factory else None
                    if adapted:
                        body, validator = adapted
                        feedback_content['instruction'] = ('Apply only allowed typed corrections. Keep valid items unchanged. '
                            'For named slots, null means unchanged; merge all issues for a target into one change. '
                            'The same target may be corrected again against the next base revision.')
                    token.repair_context['mode'] = (validator.repair_mode if adapted else 'stage_contract_replacement')
                    if adapted and validator.repair_contract:
                        token.repair_context['contract_revision'] = validator.repair_contract['revision']
                    feedback = json.dumps(feedback_content, ensure_ascii=False)
                    # Merge into last user turn; valid role alternation even
                    # when a complete envelope contained invalid JSON.
                    last = body['messages'][-1]
                    if isinstance(last['content'], list):
                        last['content'].append({'type': 'text', 'text': feedback})
                    else:
                        last['content'] += '\n'+feedback

        async def repair_scene(candidate, diagnosis, problems, decision, *, kind='geometry'):
            nonlocal repair_failures
            from .repair_scope import checked_scope, scope_options
            from .repair_memory import remember_failure
            context, options = scope_options(candidate, diagnosis)
            repair_failures = remember_failure(repair_failures, candidate, diagnosis, problems,
                context, revision(candidate), kind=kind)
            activity('waiting_model',stage_name='repair',affected_ids=[r['id'] for r in context['targets']],
                reason_codes=[str(p).split(':',1)[0] for p in problems[:16]])
            patch_body = self.body('twinpulse_semantic_patch', patch_schema(candidate, observation,
                request=request, repair_diagnosis=diagnosis),
                'Correct this candidate with named semantic operations only, never executable tools. '
                'Preserve observation identity and explicit dimensions. Update affected parents/children together. '
                'Unrelated objects stay unchanged. If another eligible object must move, include request_scope '
                'and its actually changed update atomically in this response; the host validates that dependency, not prose. '
                'request_scope is not a list of available objects. Do not request scope for unchanged IDs or IDs '
                'already in repair_scope.targets. Emit one update per changed ID and scope only for changed '
                'eligible blockers outside those targets. Read failed_patch_validation on a rejected response. '
                'For photo-position conflicts use the compiled coordinates and numerical bounds in validation. '
                'Changing the declared region of a supported/draped item alone does not move its compiled '
                'position; consider its support parent and attachment anchor together. '
                'For floor packing use every conflict_set failed ID and its compiled placed-blocker/child bounds; '
                'a blocker update requires its eligible request_scope atomically, and region-only edits cannot fix an empty assembly axis. '
                'Read rejected_candidate_history: do not return an already rejected target combination '
                'unless a genuinely changed dependency resolves its listed cause. An empty region axis '
                'and an empty whole-floor axis are different. For drape, the child centre is placed at '
                'the selected parent edge, not edge-aligned by the child dimensions. Inspect its '
                'contributing assembly bounds; a full-size duvet is not automatically an overhang. '
                'Do not move supported objects to the floor merely to hide a photo contradiction. '
                'Return compact patch JSON with the exact base revision.',
                {'user_request':request.prompt, 'candidate':candidate, 'evidence_catalog':references,
                 'validation':diagnosis, 'error_code':problems, 'repair_scope':context,
                 'scope_options':options, 'repair_kind':kind, 'previous_patch_decision':{
                     k:decision[k] for k in ('decision','progressed','changed_ids','remaining_targets','regressed',
                         'rollback_to','candidate_revision','impacted_checks','remaining_repairs') if k in decision},
                 'rejected_candidate_history':repair_failures,
                 'model_library':library_for_request(request.prompt)})
            def checked_patch(value):
                try:
                    result=patch_candidate(candidate, value, observation, request=request,
                        repair_diagnosis=diagnosis)
                    scope_decision=checked_scope(candidate,value,diagnosis)
                except InvalidProviderResponseError as patch_error:
                    patch_error.candidate_value=deepcopy(candidate)
                    patch_error.repair_base_diagnosis=deepcopy(diagnosis)
                    raise
                token.validation_candidate=deepcopy(result)
                self._diagnostic['scope_decision']=scope_decision
                validation_evidence('geometry_scope',None,scope_decision)
                return result
            checked_patch.repair_base_candidate=deepcopy(candidate)
            checked_patch.repair_base_diagnosis=deepcopy(diagnosis)
            result = await content_stage('repair',patch_body,checked_patch,initial_role='repair')
            patches.append({'request_id':request.request_id,'before':revision(candidate),'after':revision(result),
                'reason_codes':problems[:64],'validation':'pending','repair_kind':kind,
                'scope_decision':deepcopy(self._diagnostic.get('scope_decision')),
                'changed_ids':[i for i in sorted(set(candidate['objects'])|set(result['objects']))
                    if candidate['objects'].get(i)!=result['objects'].get(i)],
                'room_changed':candidate['room']!=result['room']})
            return result

        try:
            if parent and best_candidate is not None:
                # Explicit resume recompiles the best displayable subset. A
                # legacy checkpoint may have no exact image for that candidate;
                # rebuild it through the normal revision-bound preview port
                # before an exhausted repair budget stops this action. This is
                # local display work, not another HTTP request or budget reset.
                # publish_preview validates the subset; saved flags alone
                # cannot authorize a Build or mark the whole candidate valid.
                draft=deepcopy(best_candidate)
                self._diagnostic['stage']='final_validation'
                restore_preview(best_preview)
                # A restored JPEG is static evidence, not current authority in
                # this new action/engine session. Acquire a fresh exact capture.
                preview_capture=None
                await publish_preview()
                if self._diagnostic.get('generation_preview',{}).get('state')=='ready':
                    best_preview=remember_preview()
                checkpoint('DRAFT_INCOMPLETE')
            if (request.images and observation is None and room_seed is None
                    and getattr(request.render_review_port,'supports_incremental_preview',False)):
                # First visible shell does not wait for a full object inventory.
                # This provisional observation cannot satisfy object coverage.
                from .generation_preview import room_seed_schema, checked_room_seed
                if structure_observation is None:
                    coarse=self.build_observer_body(request)
                    coarse['response_format']['json_schema']=dict(name='twinpulse_room_observation',strict=True,schema=dict(
                        type='object',additionalProperties=False,required=['summary','ambiguities'],properties=dict(
                            summary=dict(type='string',minLength=1,maxLength=300),
                            ambiguities=dict(type='array',maxItems=4,items=dict(type='string',maxLength=160)))))
                    coarse['messages'][0]['content']=(
                        'Describe only the visible room envelope, floor, walls, depth and camera orientation in at most '
                        'three concise sentences. No object inventory, instance counts, tools or measured coordinates. '
                        'Room scale is estimated and occluded boundaries are uncertain. A separate full image '
                        'observation will follow. Return compact schema JSON.')
                    coarse['max_tokens']=self.stage_output_token_caps.get('observer',4000)
                    def checked_coarse(value):
                        from .semantic_scene import _shape_issues
                        from .scene_contract import SceneContractError, report
                        issues=_shape_issues(value,coarse['response_format']['json_schema']['schema'])
                        if issues: raise SceneContractError(report(issues))
                        return ObservationArtifact.from_mapping(dict(schema_version='1.0',summary=value['summary'],
                            entities=[],relations=[],dimensions=[],ambiguities=value['ambiguities']))
                    structure_observation=await content_stage('observer_structure',explicit_json_contract(coarse),checked_coarse)
                    checkpoint('DRAFT_INCOMPLETE')
                room_body=self.body('twinpulse_semantic_room',room_seed_schema(request),
                    'Estimate a provisional room shell using the coarse visual summary and explicit user dimensions. '
                    'Missing scale is estimated, not measured. Detailed observation can later revise this shell. '
                    'Return only compact summary and room JSON.',
                    {'user_request':request.prompt,'observations':structure_observation.to_dict()})
                room_seed=await content_stage('room',room_body,
                    lambda value:checked_room_seed(value,structure_observation,request))
                checkpoints.append('room')
                await publish_preview()
                checkpoint('DRAFT_INCOMPLETE')
            if request.images and observation is None:
                observer_body = explicit_json_contract(self.build_observer_body(request))
                observer_body['max_tokens'] = self.stage_output_token_caps.get('observer', 4000)
                cache_key = canonical_sha256({'body': observer_body, 'observer_wire_policy': self.observer_wire_policy,
                    'input_scope': getattr(scope, 'cache_identity', None)})
                cached = self.store.read('observation', cache_key) if self.store and scope else None
                if cached:
                    observation = ObservationArtifact.from_mapping(cached['observation'])
                    self._diagnostic['observation_cache_hit'] = True
                else:
                    from .observation_instances import checked_observation_instances
                    observation = await content_stage('observer', observer_body, checked_observation_instances)
                    if self.store and scope:
                        self.store.save('observation', cache_key, {'observation': observation.to_dict(),
                            'input_sha256': input_digest(request)})
                checkpoints.append('observer')
            elif observation is None:
                observation = ObservationArtifact.from_mapping({'schema_version': '1.0',
                    'summary': 'Text only; no measured geometry.', 'entities': [], 'relations': [],
                    'dimensions': [], 'ambiguities': ['Geometry is estimated, not measured.']})
            if instance_grounding is None:
                from .observation_instances import expand_observation_instances
                source_observation=observation.to_dict()
                observation,instance_grounding=expand_observation_instances(observation)
                validation_evidence('instance_grounding',None,instance_grounding)
            self._diagnostic['instance_grounding']=deepcopy(instance_grounding)
            checkpoint('DRAFT_INCOMPLETE')
            references = evidence_catalog(request, observation)
            if draft is None and room_seed is None and getattr(request.render_review_port,'supports_incremental_preview',False):
                from .generation_preview import room_seed_schema, checked_room_seed
                room_body=self.body('twinpulse_semantic_room',room_seed_schema(request),
                    'Estimate only the approximate room shell, not inventory or object parameters. '
                    'Preserve explicit user room dimensions. State missing dimensions as estimates. '
                    'Use the provided visual observations when present. Return just compact summary and room JSON.',
                    {'user_request':request.prompt,'observations':observation.to_dict()})
                room_seed=await content_stage('room',room_body,
                    lambda value:checked_room_seed(value,observation,request))
                checkpoints.append('room')
                checkpoint('DRAFT_INCOMPLETE')
                await publish_preview()
                checkpoint('DRAFT_INCOMPLETE')
            structure_body = self.body('twinpulse_semantic_structure', structure_schema(request, observation, bound=True),
                'Plan only approximate room dimensions and object inventory, not tool calls. '
                'Include every observed physical object or unknown obstacle and explicitly requested object. '
                'Structure/openings/free space/robot observations are not furniture. '
                'Select one evidence_ref from the host evidence_catalog for each item; never write source or observation IDs. '
                'If an observed object is also mentioned in text, represent that same object once with its own '
                'seen reference, not as an ungrounded text object. Each seen reference denotes ONE distinct object. '
                'The typed role/category is authoritative, not a contradictory legacy kind. '
                'Additional explicitly requested objects may use a text reference. Unobserved optional objects may use '
                'hypothesis, marked as unverified estimates, never to replace a seen object. '
                'Cover every required_inventory ID with its own seen reference; do not replace coverage with a summary. '
                'Do not include a library catalogue as inventory. Estimates may change; explicit dimensions must not. '
                'Use pallet for a bare pallet, pallet_stack for a pallet already loaded with cargo, and rack for warehouse shelving. '
                'Use floor_covering for a visible rug/carpet layer, wall_fixture for fixed wall items, '
                'ceiling_fixture for fixed ceiling items, and wall_storage for mounted cabinets. '
                'Use unknown only when object type is uncertain, preserving its conservative hazard. '
                'No robot or execution authority. Compact JSON, no explanation.',
                {'user_request': request.prompt, 'observations': observation.to_dict(), 'room_seed':room_seed,
                 'required_inventory': inventory_requirements(observation),
                 'evidence_catalog': references,
                 'model_library': library_for_request(request.prompt)})
            if draft is None:
                def structure_repairs(candidate, diagnosis):
                    return targeted_repair(structure_repair_schema(candidate, diagnosis, request, observation),
                        lambda value: repair_structure(candidate, value, diagnosis, request, observation),
                        lambda value: checked_structure(value, request, observation, bound=True),
                        'twinpulse_semantic_structure', {'user_request': request.prompt,
                            'previous_candidate': candidate, 'validation': diagnosis, 'evidence_catalog': references,
                            'structure_repair': structure_repair_context(candidate, diagnosis, request, observation)})
                structure = await content_stage('structure', structure_body,
                    lambda value: checked_structure(value, request, observation, bound=True),
                    repair_factory=structure_repairs)
                draft = scene_draft(structure)
                checkpoints.append('structure')
            checkpoint('DRAFT_INCOMPLETE')
            if getattr(request.render_review_port,'supports_incremental_preview',False):
                await publish_preview()
                checkpoint('DRAFT_INCOMPLETE')
            from .generation_preview import parameter_order
            ids = [identity for identity in parameter_order(draft,observation) if identity not in draft['objects']]
            for start in range(0, len(ids), PARAMETER_BATCH_SIZE):
                targets = [identity for identity in ids[start:start+PARAMETER_BATCH_SIZE] if identity not in draft['objects']]
                if not targets:
                    continue
                activity('waiting_model',stage_name='objects',batch_index=start//PARAMETER_BATCH_SIZE+1,
                    batch_total=(len(ids)+PARAMETER_BATCH_SIZE-1)//PARAMETER_BATCH_SIZE,affected_ids=targets)
                # Host pins inventory IDs and sources once. Prior batches are
                # context, not immutable poses; final patch can revise parents.
                batch_body = self.body('twinpulse_semantic_batch', batch_schema(draft['inventory'], targets),
                    'Set parameters only for these required object keys. Select reusable model_id, positive xyz dimensions, '
                    'variant/finish, region and yaw. Each floor furniture must stand on the floor. '
                    'Describe child support/attachment using named parent IDs and valid model parts. '
                    'Warehouse rack requires bay_count/level_count and pallet_stack requires stack_levels '
                    'inside warehouse_parameters; their existing factories support yaw_deg=0 only. '
                    'Empty pallet supports deck; loaded pallet supports stack_top only; rack supports '
                    'shelf_1 through level_count. Respect clearance to other shelves and posts. '
                    'Do not use body for a bed (base/mattress/headboard), use top for a desk. '
                    'For drape, dimensions describe the hanging envelope centred on the selected parent edge, '
                    'not the full blanket footprint. A whole item lying on a surface must use surface and fit that part. '
                    'Mounted wall_storage/wall_fixture and ceiling_fixture keep their library attachment relation. '
                    'floor uses null parent/part/elevation and centre anchor. Preserve evidence and explicit measurements. '
                    'Regions are illustrative image-relative estimates, not localization. '
                    'Return compact JSON, no tools, geometry arithmetic or duplicate source references.',
                    {'user_request': request.prompt, 'room': draft['room'], 'inventory': draft['inventory'],
                     'targets': targets, 'completed_objects': draft['objects'],
                     'observations': observation.to_dict(), 'model_library': library_for_request(request.prompt)})
                def object_repairs(candidate, diagnosis):
                    return targeted_repair(batch_repair_schema(candidate, draft, targets),
                        lambda value: repair_batch(candidate, value, draft, targets),
                        lambda value: checked_batch(value, draft, targets), 'twinpulse_semantic_batch',
                        {'user_request': request.prompt, 'previous_candidate': candidate, 'validation': diagnosis,
                         'inventory': draft['inventory'], 'room': draft['room'], 'completed_objects': draft['objects']})
                async def preserve_valid_parameters(candidate,diagnosis):
                    nonlocal draft
                    if not isinstance(candidate,dict) or set(candidate)!=set(targets):
                        return  # Missing/extra identity must still be corrected explicitly.
                    valid={}
                    for identity,value in candidate.items():
                        try:
                            checked_batch({identity:value},draft,[identity])
                            valid[identity]=value
                        except InvalidProviderResponseError:
                            pending_parameter_candidates[identity]=deepcopy(value)
                    if not valid:
                        return
                    draft=checked_batch(valid,draft,list(valid))
                    checkpoint('DRAFT_INCOMPLETE')
                    await publish_preview()
                    checkpoint('DRAFT_INCOMPLETE')
                draft = await content_stage('objects', batch_body, lambda value:
                    checked_batch(value, draft, targets), repair_factory=object_repairs,
                    on_invalid=preserve_valid_parameters)
                for identity in targets:pending_parameter_candidates.pop(identity,None)
                checkpoints.append('objects:'+str(start//PARAMETER_BATCH_SIZE+1))
                checkpoint('DRAFT_INCOMPLETE')
                if getattr(request.render_review_port,'supports_incremental_preview',False):
                    await publish_preview()
                    checkpoint('DRAFT_INCOMPLETE')
            budget.initial_closed = True
            repairing = False
            while True:
                activity('validating',stage_name='final_validation')
                _ensure_current(token)
                compiling = True
                try:
                    trace = token.diagnostics
                    with (trace.span('semantic_compile') if trace else nullcontext()):
                        payload, provenance = compile_scene(draft, observation, request, progressive=True)
                    compiling = False
                    await publish_preview(payload)
                    if provenance.get('progressive_twin'):
                        self._diagnostic['progressive_twin']=deepcopy(provenance['progressive_twin'])
                    quality=review_candidate_quality(draft,payload,provenance,observation,request)
                    if render_review and quality['status'] != 'needs_revision':
                        from . import render_review as reviewer
                        self._diagnostic.update(stage='render_preview', status='running')
                        self._diagnostic['sequence']=self._diagnostic.get('sequence',0)+1
                        if budget.snapshot()['requests']+budget.carried_requests>=self.policy.max_requests:
                            raise GenerationBudgetError('REQUEST_LIMIT_REACHED')
                        started=time.monotonic()
                        self._stage_started=started
                        try:
                            with (trace.span('render_preview',component='application',candidate_revision=revision(draft))
                                    if trace else nullcontext()):
                                if (preview_capture and preview_capture['metadata']['plan_sha256']==canonical_sha256(payload)
                                        and preview_capture['metadata']['candidate_revision']==revision(draft)):
                                    request.render_review_port.assert_current(preview_capture['metadata'])
                                    capture=preview_capture
                                else:
                                    capture=await request.render_review_port.capture(payload,revision(draft),token,
                                        budget.timeout_for('final_review'))
                        finally:
                            budget.final_used_s+=max(0,time.monotonic()-started)
                        _ensure_current(token)
                        capture['plan']=payload
                        frame_key=reviewer.binding(draft,payload,capture)
                        self._diagnostic['render_capture']=deepcopy(capture['metadata'])
                        if self.store:
                            import base64
                            self.store.save('render',frame_key,{'metadata':capture['metadata'],
                                'jpeg_base64':base64.b64encode(capture['jpeg']).decode('ascii')})
                        review_body=reviewer.body(request,draft,observation,capture,
                            model=self.observer_model_id,cap=self.stage_output_token_caps.get('observer',4000))
                        # Malformed critic output is not fed back as a planner patch.
                        # Stop with its raw/validation record instead of inventing quality.
                        quality=await stage('render_review',review_body,lambda value:
                            reviewer.checked(value,draft,payload,capture,quality),'final_review')
                        request.render_review_port.assert_current(capture['metadata'])
                        render_history.append(deepcopy(quality))
                        validation_evidence('render_quality',None,quality)
                        self._diagnostic['render_review']=deepcopy(quality)
                    provenance['quality_review']=quality
                    self._diagnostic['quality_review']=deepcopy(quality)
                    validation_evidence('candidate_quality',None,quality)
                    complete_report={**provenance,'issues':[]}
                    candidate={**draft,'objects':[dict(id=i,**v) for i,v in draft['objects'].items()]}
                    progressed=tracker.observe(candidate,[],complete_report)
                    best_candidate=deepcopy(draft);best_diagnosis=deepcopy(complete_report)
                    best_preview=remember_preview()
                    if quality['status']=='needs_revision':
                        # Geometry is valid, but known current observation conflicts
                        # must feed a bounded repair before publication. No render
                        # or support PASS is inferred from a clean geometry ledger.
                        qproblems=diagnostic_blockers(quality,'PHOTO_COMPARISON_NEEDS_REVISION')
                        qprogress=quality_tracker.observe(candidate,qproblems,quality)
                        if quality_best is None or qprogress:
                            quality_best=deepcopy(draft);quality_best_review=deepcopy(quality)
                            quality_preview=remember_preview()
                        qdecision={'decision':quality_tracker.decision,'progressed':qprogress,
                            'candidate_revision':revision(draft),'stage_complete':False,'repair_kind':'quality'}
                        self._diagnostic.update(stage='photo_quality',repair_decision=qdecision,
                            geometry_checks=deepcopy(provenance),stage_acceptance={
                                'approximate_draft':'blocked','photo_quality':'needs_revision',
                                'Isaac_Build':'preview_passed' if quality.get('render_comparison')=='reviewed' else 'not_run','SIM_Run_Stop':'not_run',
                                'physical_alignment':'not_run','physical_mission':'not_run'})
                        validation_evidence('quality_repair_decision',None,qdecision)
                        if patches and patches[-1]['after']==revision(draft):
                            patches[-1].update(geometry_validation='passed',quality_validation='failed')
                        checkpoint('DRAFT_INCOMPLETE')
                        refinement_stop=None
                        if repairing:
                            # A geometry repair may expose photo conflicts for
                            # the first time. Count actual geometry advancement,
                            # not the quality tracker's initial observation.
                            geometry_advanced=(patches[-1]['repair_kind']=='geometry' and progressed)
                            try:budget.repair_result(progressed=qprogress or geometry_advanced)
                            except GenerationBudgetError as terminal:
                                if terminal.code!='REPAIR_STALLED':raise
                                refinement_stop=terminal.code
                        if budget.repairs>=self.policy.max_repairs:
                            refinement_stop=refinement_stop or 'QUALITY_REPAIR_LIMIT_REACHED'
                        if refinement_stop:
                            # This boundary has a CURRENT parsed candidate and
                            # full geometry checks. It is not an exception fallback
                            # to an old/best payload or a quality PASS.
                            _ensure_current(token)
                            checked_payload,checked_provenance=compile_scene(draft,observation,request,progressive=True)
                            if (canonical_sha256(checked_payload)!=canonical_sha256(payload) or
                                    not (checked_provenance.get('checks_complete') is True or
                                        checked_provenance.get('materialized_subset_checked') is True)):
                                raise GenerationBudgetError(refinement_stop)
                            budget.stop(refinement_stop)
                            from twinpulse_core.draft_refinement import create_refinement
                            draft_refinement=create_refinement(checked_payload,request_id=request.request_id,
                                candidate_revision=revision(draft),source_observation_sha256=instance_grounding['source_observation_sha256'],
                                quality=quality,checks=checked_provenance,budget=budget.snapshot(),
                                progressive=checked_provenance.get('progressive_twin'))
                            provenance=checked_provenance|{'quality_review':deepcopy(quality)}
                            self._diagnostic.update(draft_refinement=deepcopy(draft_refinement),stop_reason=refinement_stop,
                                geometry_checks=deepcopy(checked_provenance),stage_acceptance={
                                    'approximate_draft':'partial','photo_quality':'needs_revision',
                                    'Isaac_Build':'preview_passed' if quality.get('render_comparison')=='reviewed' else 'not_run',
                                    'SIM_Run_Stop':'not_run','physical_alignment':'not_run','physical_mission':'not_run'})
                            self._diagnostic['repair_decision'].update(stage_complete=False,refinement_incomplete=True)
                            validation_evidence('draft_refinement',None,{'validation':'partial',
                                'draft_refinement':draft_refinement,'candidate':draft})
                            break
                        if any(row.get('repairable') is False for row in quality['issues']):
                            raise InvalidProviderResponseError('QUALITY_REPAIR_TARGET_UNAVAILABLE')
                        draft=await repair_scene(draft,quality,qproblems,qdecision,kind='quality')
                        await publish_preview()
                        repairing=True
                        checkpoint('DRAFT_INCOMPLETE')
                        continue
                    if request.images:
                        quality_tracker.observe(candidate,[],quality)
                        quality_best=deepcopy(draft);quality_best_review=deepcopy(quality)
                        quality_preview=remember_preview()
                    self._diagnostic.update(geometry_checks=deepcopy(provenance),
                        repair_decision=dict(decision='stage_complete',progressed=progressed,
                            stage_complete=True,candidate_revision=revision(draft)),
                        stage_acceptance={'approximate_draft':'partial' if provenance.get('progressive_twin',{}).get('unresolved') else 'passed','photo_quality':quality['status'],
                            'Isaac_Build':'preview_passed' if quality.get('render_comparison')=='reviewed' else 'not_run','SIM_Run_Stop':'not_run','physical_alignment':'not_run',
                            'physical_mission':'not_run'})
                    validation_evidence('semantic_compile', None, {'validation': 'partial' if provenance.get('progressive_twin',{}).get('unresolved') else 'passed',
                        'candidate': draft, 'semantic_revision': revision(draft), 'patches': patches,
                        'checks':provenance.get('checks'), 'checks_complete':provenance.get('checks_complete')})
                    if patches and patches[-1]['after']==revision(draft):
                        patches[-1]['validation'] = 'passed'
                        patches[-1].update(geometry_validation='passed',quality_validation=quality['status'])
                        if self._diagnostic['attempts']:
                            self._diagnostic['attempts'][-1]['candidate_validation']='passed'
                    if repairing:
                        budget.repair_result(progressed=True)
                    break
                except (ValueError, InvalidProviderResponseError) as error:
                    if not compiling:
                        # Provider truncation/schema/evidence/quality errors
                        # are not compiler errors and must retain their cause.
                        raise
                    diagnosis = compiler_diagnosis(error, draft, request)
                    self._diagnostic.update(stage='final_validation', status='validation_failed',
                        validation_code=_validation_code(error))
                    if diagnosis:
                        self._diagnostic['scene_contract'] = deepcopy(diagnosis)
                    try:
                        validation_evidence('semantic_compile', None, {'validation': 'failed',
                            'candidate': draft, 'diagnosis': diagnosis, 'validation_detail': str(error), 'patches': patches})
                    except Exception as storage_error:
                        error.evidence_error_type = type(storage_error).__name__
                        raise error from storage_error
                    if patches and patches[-1]['after']==revision(draft):
                        patches[-1]['validation'] = 'failed'
                        if self._diagnostic['attempts']:
                            self._diagnostic['attempts'][-1]['candidate_validation']='failed'
                    problems = diagnostic_blockers(diagnosis, str(error).split(':')[0][:80])
                    candidate = {**draft, 'objects': [dict(id=i, **v) for i, v in draft['objects'].items()]}
                    progressed = tracker.observe(candidate, problems, diagnosis)
                    decision={'progressed':progressed,'decision':tracker.decision,
                        'candidate_revision':revision(draft),'diagnosis':diagnosis,
                        'advanced_checks':list(tracker.advanced_checks),'regressed':tracker.regressed,
                        'comparison_uncertain':tracker.comparison_uncertain,
                        'stage_complete':False}
                    if best_candidate is None or progressed and not tracker.regressed:
                        best_candidate=deepcopy(draft);best_diagnosis=deepcopy(diagnosis)
                        best_preview=remember_preview()
                    restored=False
                    if tracker.regressed:
                        can_explore=(tracker.decision!='repeated_candidate' and budget.repairs<self.policy.max_repairs
                            and budget.no_progress+1<self.policy.stalled_repairs and diagnosis.get('checks')
                            and all(r.get('repairable') is True for r in diagnosis.get('issues',[]))
                            and next(r for r in diagnosis['checks'] if r['check_id']=='input_contract')['status']=='passed'
                            and not any(r['status']=='error' for r in diagnosis['checks']))
                        if can_explore:
                            try:budget.timeout_for('repair')
                            except GenerationBudgetError:can_explore=False
                        decision['rollback_to']=revision(best_candidate)
                        if can_explore:
                            decision.update(decision='exploring',published=False,
                                remaining_repairs=self.policy.max_repairs-budget.repairs,
                                impacted_checks=[r['check_id'] for r in diagnosis['checks'] if r['status']!='passed'])
                            tracker.history[-1].update(decision='exploring',rollback_to=revision(best_candidate))
                        else:
                            # Keep the failed branch diagnosis on the decision.
                            # A clean geometry report on best is not a quality
                            # acceptance and must never replace this error.
                            draft=deepcopy(best_candidate)
                            restore_preview(best_preview)
                            payload=None
                            self._diagnostic.pop('render_capture',None)
                            self._diagnostic.pop('render_review',None)
                            restored=True
                            decision.update(branch_abandoned=True,published=False)
                            rollback={'candidate_revision':revision(draft),
                                'failed_candidate_revision':decision['candidate_revision'],
                                'failed_diagnosis':deepcopy(diagnosis),'external_call':False,
                                'previous_geometry_complete':bool(best_diagnosis.get('checks_complete'))}
                            try:
                                with (token.diagnostics.span('rollback_revalidation')
                                        if token.diagnostics else nullcontext()):
                                    restored_plan,restored_checks=compile_scene(draft,observation,request)
                                restored_quality=review_candidate_quality(draft,restored_plan,
                                    restored_checks,observation,request)
                                best_diagnosis={**restored_checks,'issues':[]}
                                rollback.update(validation='passed',checks=deepcopy(best_diagnosis),
                                    quality_status=restored_quality['status'])
                                self._diagnostic.update(scene_contract=deepcopy(best_diagnosis),
                                    geometry_checks=deepcopy(restored_checks),
                                    quality_review=deepcopy(restored_quality))
                            except (ValueError,InvalidProviderResponseError) as restored_error:
                                best_diagnosis=compiler_diagnosis(restored_error,draft,request)
                                rollback.update(validation='failed',diagnosis=deepcopy(best_diagnosis),
                                    quality_status='not_run')
                                self._diagnostic.update(scene_contract=deepcopy(best_diagnosis),
                                    geometry_checks=deepcopy(best_diagnosis))
                                self._diagnostic.pop('quality_review',None)
                            # This recheck is local only. A configured rendered
                            # critic must still run in the normal loop before
                            # publication; no old render is marked current.
                            self._diagnostic['stage_acceptance']={
                                'approximate_draft':'blocked','photo_quality':rollback['quality_status'],
                                'Isaac_Build':'not_run','SIM_Run_Stop':'not_run',
                                'physical_alignment':'not_run','physical_mission':'not_run'}
                            self._diagnostic['rollback_revalidation']=rollback
                            validation_evidence('rollback_revalidation',None,rollback)
                    self._diagnostic['repair_decision']=decision
                    validation_evidence('geometry_repair_decision',None,decision)
                    checkpoint('DRAFT_INCOMPLETE')
                    if tracker.decision=='evidence_insufficient':
                        raise GenerationBudgetError('CHECK_EVIDENCE_INSUFFICIENT') from error
                    if repairing:
                        budget.repair_result(progressed=progressed,exploratory=tracker.decision=='exploratory')
                    if restored:
                        if rollback['validation']=='failed':
                            # A best geometry candidate may itself still have
                            # known repairable gaps. Use its FRESH diagnosis,
                            # not the failed branch's error or cached report.
                            restored_issues=best_diagnosis.get('issues',[])
                            if (rollback['previous_geometry_complete'] or not restored_issues
                                    or any(r.get('repairable') is not True for r in restored_issues)
                                    or any(r.get('status')=='error' for r in best_diagnosis.get('checks',[]))):
                                raise GenerationBudgetError('ROLLBACK_REVALIDATION_FAILED') from error
                            diagnosis=deepcopy(best_diagnosis)
                            problems=diagnostic_blockers(diagnosis,'ROLLBACK_GEOMETRY_NEEDS_REVISION')
                        else:
                            # The failed paid patch is accounted exactly once.
                            # Re-enter geometry -> observation -> current render
                            # for the restored revision, within the SAME budget.
                            repairing=False
                            continue
                    if not diagnosis.get('issues') or any(row.get('repairable') is False for row in diagnosis['issues']):
                        raise InvalidProviderResponseError('UNMAPPED_COMPILER_ERROR: '+str(error)) from error
                    if budget.repairs >= self.policy.max_repairs:
                        raise GenerationBudgetError('REPAIR_LIMIT_REACHED') from error
                    draft = await repair_scene(draft,diagnosis,problems,decision)
                    repairing = True
                    await publish_preview()
                    checkpoint('DRAFT_INCOMPLETE')
            checkpoints.append('final_validation')
            draft['state'] = 'APPROXIMATE_TWIN_READY'
            self._diagnostic.update(stage='final_validation', status='validated', validator='passed',
                                    semantic_revision=revision(draft))
            for key in ('scene_contract', 'validation_code'):
                self._diagnostic.pop(key, None)
            checkpoint('APPROXIMATE_TWIN_READY',draft_refinement['stop_reason'] if draft_refinement else None)
            return ProviderResponse(request.request_id, payload, self.name, self.planner_model_id,
                {**provenance, 'generation_policy': self.policy.to_dict(),
                 'structure_repair_revision': STRUCTURE_REPAIR_REVISION,
                 'scope_revision': SCOPE_REVISION, 'quality_repair_revision': QUALITY_REPAIR_REVISION,
                 'render_review_revision': RENDER_REVIEW_REVISION, 'render_history':render_history,
                 'budget': budget.snapshot(), 'observation_sha256': observation.sha256,
                 **({'draft_refinement':draft_refinement} if draft_refinement else {}),
                 'source_observation_sha256':instance_grounding['source_observation_sha256'],
                 'instance_grounding':instance_grounding,
                 'checkpoint_id': checkpoint_key, 'patches': patches, 'automatic_resume': False})
        except BaseException as error:
            code = getattr(error, 'code', None) or type(error).__name__
            if isinstance(error, (GenerationCancelledError, asyncio.CancelledError)):
                budget.stop('GENERATION_CANCELLED')
            elif isinstance(error, ProviderError):
                budget.stop(code)
            self._diagnostic.update(status='failed', stop_reason=budget.terminal or code)
            if self._diagnostic.get('stage_acceptance',{}).get('approximate_draft') in ('passed','partial'):
                # Core checks alone cannot publish a draft if evidence or the
                # final checkpoint failed to persist.
                self._diagnostic['stage_acceptance']['approximate_draft']='failed'
                self._diagnostic['repair_decision']['stage_complete']=False
            if getattr(error,'contract_report',None):
                self._diagnostic['scene_contract']=deepcopy(error.contract_report)
            if quality_best is not None and (quality_tracker.regressed or
                    budget.terminal=='REPAIR_STALLED' and
                    self._diagnostic.get('repair_decision',{}).get('repair_kind')=='quality'):
                abandoned=revision(draft)
                draft=deepcopy(quality_best)
                restore_preview(quality_preview)
                self._diagnostic['quality_review']=deepcopy(quality_best_review)
                self._diagnostic['repair_decision'].update(branch_abandoned=True,
                    abandoned_revision=abandoned,rollback_to=revision(draft),published=False)
                try:
                    _,restored_checks=compile_scene(draft,observation,request)
                    self._diagnostic['geometry_checks']=restored_checks
                    best_candidate=deepcopy(draft)
                    best_diagnosis={**restored_checks,'issues':[]}
                except Exception as rollback_error:
                    # Do not replace the original provider/budget failure.
                    self._diagnostic['rollback_error_type']=type(rollback_error).__name__
            if best_candidate is not None and self._diagnostic.get('repair_decision',{}).get('decision')=='exploring':
                self._diagnostic['repair_decision']['branch_abandoned']=True
                draft=deepcopy(best_candidate)
                restore_preview(best_preview)
                self._diagnostic['scene_contract']=deepcopy(best_diagnosis)
            if isinstance(error, ProviderError):
                error.diagnostics = self.diagnostic_for(request.request_id)
            try:
                checkpoint('DRAFT_INCOMPLETE', code)
            except Exception as storage_error:
                # Preserve the primary failure and keep storage failure separate.
                error.checkpoint_error_type = type(storage_error).__name__
                self._diagnostic['checkpoint_error_type'] = type(storage_error).__name__
            if isinstance(error, ProviderError):
                error.diagnostics = self.diagnostic_for(request.request_id)
            raise
