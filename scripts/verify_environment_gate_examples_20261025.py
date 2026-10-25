# SPDX-License-Identifier: Apache-2.0
"""Exercise gate helpers on immutable historical evidence, never product writes."""
import ast
from copy import deepcopy
import hashlib,json,os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/environment-task-loop-20261025-01'
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.task_collection import TaskCollection
from twinpulse_core import canonical_sha256
read=lambda p:json.loads(p.read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
project=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects/chat_mvmcf9wa_18f1e6d1'
tree=ast.parse((ROOT/'scripts/verify_environment_task_readiness_20261025.py').read_text(encoding='utf-8'))
selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'collection_lineage','normal_roots','mandatory_steps'}]
exec(compile(ast.Module(body=selected,type_ignores=[]),'<gate_helpers>','exec'))
debug=deepcopy(next(n for n in selected if n.name=='collection_lineage'));debug.name='lineage_conditions'
terms=debug.body[-1].value.args[0].values
debug.body[-1]=ast.Return(value=ast.Dict(keys=[ast.Constant(value=ast.unparse(t)) for t in terms],values=terms))
exec(compile(ast.fix_missing_locations(ast.Module(body=[debug],type_ignores=[])),'<gate_diagnostic>','exec'))
adopt=read(OUT/'adopt05/result.json');changed=deepcopy(adopt)
for row in changed['requests']:
    if row['request'].get('action')=='preview_obstacle':row['status']=400
folder=OUT/'runtime-copies15-recovery/0d56e7cefa284e1cb863fd1293f7d933'
cleanup=read(folder/'cleanup-receipt.json');owned=read(folder/'owned-exit-observations.json');engine=read(folder/'engine-result.json')
wrong_photo=deepcopy(adopt);wrong_photo['photo']['photo']['sha256']='f'*64
checks=dict(original_bound_adoption=collection_lineage(adopt,adopt['edits'][0]),
    failed_photo_request_rejected=not collection_lineage(changed,changed['edits'][0]),
    wrong_photo_digest_rejected=not collection_lineage(wrong_photo,wrong_photo['edits'][0]),
    actual_two_roots_pass=normal_roots(cleanup,owned,engine),
    empty_roles_rejected=not normal_roots(dict(cleanup,process_exit_observations={}),owned,engine),
    missing_engine_rejected=not normal_roots(dict(cleanup,process_exit_observations={'backend':cleanup['process_exit_observations']['backend']}),owned,engine),
    mandatory_step_missing_rejected=not mandatory_steps(dict(steps=[dict(name='a',status='PASS')]),['a','b']))
if (OUT/'hybrid16/result.json').is_file():
    current=read(OUT/'hybrid16/result.json')
    checks['current_installed_hybrid_lineage']=collection_lineage(current,current['edits'][1])
if (OUT/'reapply16/result.json').is_file():
    reapply=read(OUT/'reapply16/result.json')
    checks['current_installed_reapply_lineage']=collection_lineage(reapply,reapply['edits'][0])
value=dict(status='PASS' if all(checks.values()) else 'FAIL',scope='GATE_HELPERS_HISTORICAL_EXAMPLES_NOT_FINAL_UI_ACCEPTANCE',checks=checks)
if not checks['original_bound_adoption']:value['failed_lineage_conditions']=[k for k,v in lineage_conditions(adopt,adopt['edits'][0]).items() if not v]
attempt=sys.argv[1] if len(sys.argv)>1 else '01'
if len(attempt)!=2 or not attempt.isdecimal():raise ValueError('ATTEMPT_REQUIRED')
with (OUT/('gate-examples'+attempt+'.json')).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print(json.dumps(value));sys.exit(0 if all(checks.values()) else 1)
