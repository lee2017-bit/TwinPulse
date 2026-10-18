# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic/offline contract counterexamples, never model or Isaac acceptance."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.benchmark_protocol import canonical_sha, file_sha, prepare, checked_manifest, journey_packet, source_freeze
from scripts.benchmark_environment import (capture, identity, verify_environment, checked_environment,
    COVERAGE, RUNTIME_NAMES, PACKAGES, VERSION)
from scripts.benchmark_evaluation import selected_rubric, readiness
from scripts.prepare_benchmark_evaluation import worksheets
from scripts.benchmark_campaign import initialize, admission, manifest_main, write_atomic
from scripts.collect_comparative_benchmark import collector, public_report
import tests.integration.test_benchmark_protocol as protocol_data

ROOT = Path(__file__).resolve().parents[2]
RUBRIC = dict(schema_version='benchmark-rubric-1.0',entity_f1_min=.8,hazard_recall_min=.9,
    relation_accuracy_min=.8,match_distance_uv=.2,relation_epsilon_uv=.05,
    adjacent_distance_uv=.3,size_relative_tolerance=.2)


class EnvironmentEvaluationTests(unittest.TestCase):
    def setUp(self):
        data=protocol_data.BenchmarkProtocolTests();data.setUp();self.addCleanup(data.doCleanups)
        self.root=data.root;self.value=deepcopy(data.value)
        roles=dict(observer=dict(provider='openai',model='gpt-6-luna'),
                   planner=dict(provider='nebius',model='nvidia/Nemotron-3_5-Lightning'))
        roles.update(repair=deepcopy(roles['planner']),critic=deepcopy(roles['observer']))
        self.value['configs']=[dict(config_id='reviewed',roles=roles,settings_sha256='a'*64)]
        for case in self.value['cases']:
            case['annotations']=None;case['source']['external_transmission_allowed']=True
        self.files={name:self.root/(name+'.fixture') for name in RUNTIME_NAMES}
        for path in self.files.values():path.write_bytes(b'FAKE_RUNTIME_NOT_EXECUTED')
        # Only a read of the existing reviewed local robot asset closure.
        with patch('scripts.benchmark_environment.runtime_paths',return_value=self.files):
            self.environment=capture(ROOT)
        self.save('environment.json',self.environment);self.save('rubric.json',RUBRIC)
        catalog=dict(schema_version='stage-model-catalog-1.0',verified_at='2026-10-10T00:00:00+00:00',
            valid_until='2026-10-16T00:00:00+00:00',source_sha256='a'*64,
            models=[dict(model_id='nvidia/Nemotron-3_5-Lightning',visible=True,modalities=['text'],
                         context_tokens=32000,input_per_million='0.1',output_per_million='0.2')])
        self.save('models.json',catalog)
        self.value.update(schema_version='comparative-benchmark-1.2',
            model_catalog=self.ref('models.json'),execution_environment=self.ref('environment.json'),
            evaluation=dict(rubric=self.ref('rubric.json'),review_provenance=None))
        self.manifest=self.root/'manifest.json';self.refresh()

    def save(self,name,value):
        path=self.root/name;path.write_text(json.dumps(value),encoding='utf-8');return path

    def ref(self,name):return dict(path=name,sha256=file_sha(self.root/name))

    def refresh(self):
        self.save('manifest.json',self.value);self.prepared=prepare(self.manifest)
        self.normalized=checked_manifest(self.value,self.root)

    def grant(self):
        now=datetime.now(timezone.utc)
        return dict(schema_version='benchmark-authorization-1.0',authorization_id='offline-only',
            manifest_sha256=self.prepared['manifest_sha256'],approved_at=now.isoformat(),
            expires_at=(now+timedelta(hours=4)).isoformat(),human_approval='SYNTHETIC TEST NOT ACTUAL APPROVAL',
            providers={p:dict(limit_usd='20',existing_exposure_usd='0',original_input=True,derived_render=True)
                for p in ('nebius','openai')},request_cap=24,trial_usd='1.00',admission_reserve_s=1800)

    def test_capture_does_not_launch_process_network_or_read_credentials(self):
        with patch('scripts.benchmark_environment.runtime_paths',return_value=self.files), \
             patch('socket.create_connection',side_effect=AssertionError('NO_NETWORK')), \
             patch('subprocess.run',side_effect=AssertionError('NO_PROCESS')), \
             patch('twinpulse_app.credentials.WindowsCredentialStore.load',side_effect=AssertionError('NO_KEY')):
            value=capture(ROOT)
        self.assertEqual(len(value['assets']),9);self.assertEqual(len(value['runtime_files']),9)
        self.assertEqual(value['coverage'],COVERAGE)
        value['captured_at']='2026-10-11T00:00:00+00:00'
        self.assertEqual(identity(value),identity(self.environment))
        self.assertNotIn('hostname',json.dumps(value));self.assertNotIn('username',json.dumps(value))

    def test_v13_requires_frozen_caps_without_rewriting_legacy_v12(self):
        from scripts.benchmark_campaign import eligibility
        from scripts.benchmark_protocol import frozen_stage_output_caps
        legacy=deepcopy(self.value)
        self.assertEqual(frozen_stage_output_caps(self.normalized['configs'][0]),dict(observer=20000,planner=20000))
        self.value['schema_version']='comparative-benchmark-1.3'
        with self.assertRaisesRegex(ValueError,'CONFIG_INVALID'):self.refresh()
        self.value['configs'][0]['stage_output_token_caps']=dict(observer=40000,planner=40000)
        self.refresh()
        self.assertEqual(frozen_stage_output_caps(self.prepared['configs'][0]),dict(observer=40000,planner=40000))
        self.assertEqual(eligibility(self.prepared),[dict(config_id='reviewed',reason='OUTPUT_CAP_EXCEEDS_MODEL_CONTEXT_INPUT_MARGIN')])
        self.assertEqual(len(self.prepared['jobs']),8)  # Ineligible jobs remain visible.
        self.value=legacy;self.refresh()
        self.assertEqual(eligibility(self.prepared),[])
        self.assertNotIn('stage_output_token_caps',self.normalized['configs'][0])

    def test_matching_entrypoints_not_actual_runtime_pass_and_mutations_rejected(self):
        with patch('scripts.benchmark_environment.runtime_paths',return_value=self.files):
            self.assertEqual(verify_environment(self.prepared,ROOT)['actual_isaac_readiness'],'NOT_RUN')
            self.files['node'].write_bytes(b'CHANGED_RUNTIME')
            with self.assertRaisesRegex(ValueError,'EXECUTION_ENVIRONMENT_CHANGED'):
                verify_environment(self.prepared,ROOT)
        for field in ('host','python_packages','assets','coverage'):
            value=deepcopy(self.environment)
            if field=='host':value[field]['cpu_count']+=1
            elif field=='python_packages':value[field]['Pillow']='DIFFERENT'
            elif field=='assets':value[field]['turtlebot3_burger.usda']['sha256']='b'*64
            else:value[field]['actual_isaac_readiness']='PASS'
            if field in ('assets','coverage'):
                with self.assertRaises(ValueError):checked_environment(value)
            else:self.assertNotEqual(identity(value),identity(self.environment))

    def test_fixed_launcher_override_and_missing_node_never_guess_readiness(self):
        from scripts.benchmark_environment import runtime_paths
        with patch.dict('os.environ',{'PYTHONEXE':'not-permitted'}):
            with self.assertRaisesRegex(ValueError,'OVERRIDE_UNSUPPORTED'):runtime_paths()
        with patch.dict('os.environ',{'PYTHONEXE':''}),patch('shutil.which',return_value=None):
            with self.assertRaisesRegex(ValueError,'MISSING_NODE'):runtime_paths()

    def test_child_checks_environment_before_registry_or_credential_boundary(self):
        import scripts.run_ordinary_staged_live_ten as runner
        args=['runner',str(self.root/'not-created'),'--benchmark-manifest',str(self.manifest),
              '--case-id','text-one','--config-id','reviewed','--benchmark-profile',
              '--approval-text','OFFLINE FIXTURE NOT ACTUAL APPROVAL']
        changed={**self.environment,'host':{**self.environment['host'],'cpu_count':1}}
        if changed['host']['cpu_count']==self.environment['host']['cpu_count']:changed['host']['cpu_count']=2
        with patch('sys.argv',args),patch('scripts.benchmark_protocol.source_freeze',return_value={}), \
             patch('scripts.benchmark_environment.capture',return_value=changed), \
             patch.object(runner,'KeyRegistry',side_effect=AssertionError('NO_REGISTRY')), \
             patch.object(runner,'WindowsCredentialStore',side_effect=AssertionError('NO_CREDENTIAL')):
            with self.assertRaisesRegex(ValueError,'EXECUTION_ENVIRONMENT_CHANGED'):runner.main()
        self.assertFalse((self.root/'not-created').exists())

    def test_missing_or_changed_post_run_environment_proof_cannot_settle_as_pass(self):
        import scripts.run_ordinary_staged_live_ten as runner
        approval=dict(execution_environment_sha256=identity(self.environment),evaluation_rubric_sha256=canonical_sha(RUBRIC))
        self.save('approval.json',approval)
        match=dict(status='ENTRYPOINTS_ASSETS_MATCH_NOT_RUNTIME_PASS',
                   environment_sha256=identity(self.environment),actual_isaac_readiness='NOT_RUN')
        for after in (None,{**match,'environment_sha256':'b'*64},{**match,'actual_isaac_readiness':'PASS'}):
            self.save('summary.json',dict(status='PASS',benchmark_environment_audit=dict(before=match,after=after)))
            with self.assertRaisesRegex(ValueError,'ENVIRONMENT_AUDIT_MISSING_OR_CHANGED'):
                runner.audit_ordinary_run(self.root)

    def test_environment_extra_secret_fields_and_unreviewed_assets_are_rejected(self):
        for mutation in ('secret','asset','relative'):
            value=deepcopy(self.environment)
            if mutation=='secret':value['api_key']='FIXTURE_NOT_A_KEY'
            elif mutation=='asset':value['assets']['payloads/geometries.usd']['sha256']='0'*64
            else:value['runtime_files']['python']['path']='relative.exe'
            with self.assertRaises(ValueError):checked_environment(value)

    def test_source_freeze_contains_reviewed_binary_asset_dependency(self):
        frozen=source_freeze(ROOT)
        self.assertTrue(all(record['path'] in frozen for record in self.environment['assets'].values()))
        self.assertTrue(any(p.endswith('geometries.usd') for p in frozen))
        self.assertFalse(any('/outputs/' in p.replace('\\','/') for p in frozen))

    def test_manifest_rubric_selection_cannot_be_substituted_even_if_also_frozen(self):
        alternate={**RUBRIC,'entity_f1_min':.1};path=self.save('alternate.json',alternate)
        self.value['freeze']['alternate.json']=file_sha(path);self.refresh()
        self.assertEqual(selected_rubric(self.prepared),RUBRIC)
        with self.assertRaisesRegex(ValueError,'RUBRIC_SELECTION_CHANGED'):
            collector(self.prepared,initialize(self.prepared,self.grant()),self.root,self.normalized,alternate)
        self.save('rubric.json',alternate)
        with self.assertRaisesRegex(ValueError,'SHA_CHANGED'):prepare(self.manifest)

    def test_pending_worksheets_do_not_forge_labels_and_never_enter_model_input(self):
        result=worksheets(self.prepared,RUBRIC)
        self.assertFalse(result['automatic_labels']);self.assertEqual(result['status'],'PENDING_HUMAN_LABEL_REVIEW')
        for draft in result['drafts']:
            self.assertEqual(draft['reviewers'],[]);self.assertEqual(draft['entities'],[])
            self.assertIsNone(draft['room_size_m']);self.assertFalse(draft['coverage_complete'])
        self.assertTrue(all(row['source']=='unreviewed' and row['reviewers']==[]
                            for row in result['review_provenance_template']['cases']))
        self.assertNotIn('rubric',json.dumps(self.prepared['packets']))
        self.assertNotIn('annotations',json.dumps(self.prepared['packets']))
        self.assertNotIn('execution_environment',json.dumps(self.prepared['packets']))

    def test_worksheet_cli_is_exclusive_read_only_and_pending(self):
        import scripts.prepare_benchmark_evaluation as cli
        output=self.root/'worksheets';before=self.manifest.read_bytes()
        args=['worksheets','--manifest',str(self.manifest),'--rubric',str(self.root/'rubric.json'),'--output',str(output)]
        with patch('sys.argv',args),patch('socket.create_connection',side_effect=AssertionError('NO_HTTP')),redirect_stdout(StringIO()):
            cli.main()
            with self.assertRaises(FileExistsError):cli.main()
        result=json.loads((output/'readiness.json').read_text())
        self.assertEqual(result['status'],'PENDING_HUMAN_LABEL_REVIEW');self.assertEqual(result['HTTP'],0)
        self.assertEqual(len(list(output.glob('*.annotation-draft.json'))),4)
        self.assertTrue((output/'label-review-draft.json').is_file())
        self.assertEqual(self.manifest.read_bytes(),before)

    def test_duplicate_text_is_one_group_and_cannot_cross_holdout(self):
        a,b=self.value['cases'][2:]
        b['prompt']=a['prompt'];b['prompt_sha256']=a['prompt_sha256']
        with self.assertRaisesRegex(ValueError,'DUPLICATE_TEXT_GROUP'):self.refresh()
        b['room_group']=a['room_group'];self.refresh()
        b['split']='holdout'
        with self.assertRaisesRegex(ValueError,'ROOM_SPLIT_LEAKAGE'):self.refresh()

    def test_legacy_selection_remains_explicitly_partial_not_retroactively_upgraded(self):
        legacy=deepcopy(self.value);legacy['schema_version']='comparative-benchmark-1.1'
        legacy.pop('evaluation');legacy.pop('execution_environment')
        a,b=legacy['cases'][2:];b['prompt']=a['prompt'];b['prompt_sha256']=a['prompt_sha256']
        self.save('legacy.json',legacy);prepared=prepare(self.root/'legacy.json')
        self.assertNotIn('evaluation',prepared);self.assertNotIn('execution_environment',prepared)
        self.assertEqual(verify_environment(prepared,ROOT)['status'],'LEGACY_PARTIAL_FREEZE')

    def test_holdout_missing_labels_prevents_reservation(self):
        self.value['cases']=self.value['cases'][2:3];self.value['cases'][0]['split']='holdout';self.refresh()
        state=initialize(self.prepared,self.grant())
        gate=admission(state,datetime.now(timezone.utc))
        self.assertEqual(gate['code'],'HOLDOUT_LABELS_NOT_REVIEWED_BEFORE_OUTPUTS');self.assertEqual(state['runs'],[])

    def test_environment_mismatch_prevents_child_lock_and_cost_reservation(self):
        grant=self.grant();approval=self.save('approval-fixture.json',grant)
        directory=self.root/'campaign';directory.mkdir()
        path=directory/'manifest-campaign.json';write_atomic(path,initialize(self.prepared,grant),create=True)
        before=path.read_bytes()
        args=SimpleNamespace(manifest=self.manifest,authorization=approval,directory=directory,
                             initialize=False,reconcile=False,run_next=True)
        with patch('scripts.benchmark_campaign.source_freeze',return_value={}), \
             patch('scripts.benchmark_environment.capture',return_value={**self.environment,
                 'host':{**self.environment['host'],'cpu_count':self.environment['host']['cpu_count']+1}}), \
             patch('scripts.benchmark_campaign.subprocess.run',side_effect=AssertionError('NO_CHILD')):
            with self.assertRaisesRegex(ValueError,'EXECUTION_ENVIRONMENT_CHANGED'):manifest_main(args)
        self.assertEqual(path.read_bytes(),before);self.assertFalse((directory/'manifest-dispatch-lock.json').exists())

    def test_public_report_has_only_fingerprints_and_human_pending_no_full_pass(self):
        state=initialize(self.prepared,self.grant())
        report=public_report(collector(self.prepared,state,self.root,self.normalized),self.prepared)
        encoded=json.dumps(report)
        self.assertNotIn(str(self.root),encoded);self.assertNotIn('cpu_count',encoded)
        self.assertFalse(report['reproducibility']['human_identity_verified'])
        self.assertEqual(report['reproducibility']['label_readiness'],'PENDING_OR_INVALID_LABELS')
        self.assertTrue(all(not trial['qualified_full_pass'] for trial in report['trials']))

    def test_frozen_annotations_and_pre_review_attestation_both_required(self):
        case=self.value['cases'][2];packet=self.prepared['packets'][case['case_id']]
        labels=dict(schema_version='benchmark-annotation-1.0',case_id=case['case_id'],
            input_sha256=canonical_sha(packet),rubric_sha256=canonical_sha(RUBRIC),
            coordinate_frame='room_xy_normalized_front_negative_y',coverage_complete=True,
            reviewers=['SYNTHETIC_REVIEWER_NOT_HUMAN_EVIDENCE'],entities=[dict(label_id='desk',kind='desk',
                visibility='observable',hazard=True,centre_uv=None,size_m=None,size_authority='unknown',placement=None)],
            relations=[],room_size_m=None,room_size_authority='unknown')
        self.save('labels.json',labels);case['annotations']=self.ref('labels.json')
        self.refresh();self.assertEqual(self.prepared['evaluation_readiness']['status'],'PENDING_OR_INVALID_LABELS')
        provenance=dict(schema_version='benchmark-label-review-1.0',dataset_id=self.value['dataset_id'],
            rubric_sha256=canonical_sha(RUBRIC),cases=[dict(case_id=c['case_id'],
                input_sha256=canonical_sha(self.prepared['packets'][c['case_id']]),
                annotations_sha256=c['annotations']['sha256'] if c['annotations'] else None,
                reviewers=labels['reviewers'] if c is case else [],source='human' if c is case else 'unreviewed',
                blinded=c is case,reviewed_before_outputs=c is case,
                reviewed_at='2026-10-11T00:00:00+00:00' if c is case else None) for c in self.value['cases']])
        self.save('review.json',provenance);self.value['evaluation']['review_provenance']=self.ref('review.json');self.refresh()
        row=next(r for r in self.prepared['evaluation_readiness']['cases'] if r['case_id']==case['case_id'])
        self.assertEqual(row['status'],'LABELS_REVIEWED_ATTESTED')
        self.assertFalse(self.prepared['evaluation_readiness']['human_identity_verified'])
        self.save('review.json',{**provenance,'dataset_id':'wrong-dataset'})
        self.value['evaluation']['review_provenance']=self.ref('review.json')
        with self.assertRaisesRegex(ValueError,'PROVENANCE_BINDING_CHANGED'):self.refresh()
        self.save('review.json',provenance);self.value['evaluation']['review_provenance']=self.ref('review.json');self.refresh()
        rows=deepcopy(provenance['cases']);row=next(r for r in rows if r['case_id']==case['case_id'])
        row['reviewed_before_outputs']=False
        self.save('review.json',{**provenance,'cases':rows});self.value['evaluation']['review_provenance']=self.ref('review.json')
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_LABEL_REVIEW_REQUIRED'):self.refresh()
        self.save('review.json',provenance);self.value['evaluation']['review_provenance']=self.ref('review.json');self.refresh()
        self.save('labels.json',{**labels,'coverage_complete':False})
        with self.assertRaisesRegex(ValueError,'SHA_CHANGED'):prepare(self.manifest)


if __name__=='__main__':unittest.main()
