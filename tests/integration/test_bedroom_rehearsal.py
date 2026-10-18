# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import unittest
import copy
from hashlib import sha256
import json
from tests.integration.test_bedroom_twin import ROOT
from twinpulse_app.bedroom_review import load_bedroom_source, BedroomReview
from twinpulse_app.bedroom_rehearsal import RehearsalAdapter, rehearse_bedroom, compare_rehearsals, checked_replay
from twinpulse_app.evaluation_report import evaluate_bedroom_comparison
from twinpulse_core.revisions import canonical_sha256
from twinpulse_app.command_broker import CommandBroker, BrokerError
from twinpulse_core.local_navigation import LocalScan


class BedroomRehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=load_bedroom_source(ROOT)

    def test_same_conditions_comparison_and_unknown_collision(self):
        review=BedroomReview(CommandBroker(),lambda:self.source); state=review.prepare()
        c=review.compare(state['revision'],True)
        a,b=c['candidates']
        self.assertTrue(c['eligible_for_efficiency_comparison'])
        self.assertEqual(a['record']['start_pose'],b['record']['start_pose'])
        self.assertEqual(a['record']['waypoints'][-1],b['record']['waypoints'][-1])
        self.assertNotEqual(a['record']['waypoints'],b['record']['waypoints'])
        for candidate in (a,b):
            self.assertIsNone(candidate['metrics']['collision_count'])
            self.assertIsNone(candidate['metrics']['physical_success'])
            self.assertGreater(candidate['metrics']['guard_samples'],0)
        self.assertAlmostEqual(c['b_minus_a']['duration_s'],-7.85)
        self.assertEqual(c['conditions_revision'],canonical_sha256(c['conditions']))
        record=b['record']
        self.assertEqual(checked_replay(*self.source[:2],dict(scenario='direct',revision=record['revision'],frame=len(record['events']))),record)

    def test_a4_saved_comparison_axes_preserve_unknowns_and_identity(self):
        # Preserve Python's canonical numeric representation in an offline JSON roundtrip.
        # Historical browser exports are tested separately because JS erased 0.0 distinctions.
        current = compare_rehearsals(rehearse_bedroom(*self.source[:2]),
                                     rehearse_bedroom(*self.source[:2], 'direct'))
        saved = json.loads(json.dumps(current))
        report = evaluate_bedroom_comparison(saved)
        self.assertEqual(report['source_comparison_revision'], saved['revision'])
        self.assertEqual(report['conditions_revision'], saved['conditions_revision'])
        self.assertTrue(report['eligible_for_efficiency_comparison'])
        self.assertEqual(report['synthetic_b_minus_a'], saved['b_minus_a'])
        self.assertIsNone(report['overall_score'])
        self.assertFalse(report['source_verified'])
        self.assertFalse(report['motion_authorized'])
        for item in report['candidates']:
            axes = item['axes']
            self.assertEqual(axes['scene_fidelity']['status'], 'NOT_MEASURED')
            self.assertEqual(axes['simulation_quality']['status'], 'NOT_RUN')
            self.assertEqual(axes['task_success']['basis'], 'synthetic_kinematic_only')
            self.assertEqual(axes['cost']['status'], 'UNKNOWN')
            self.assertIsNone(axes['collision']['count'])

    def test_a4_rejects_tampered_or_noncomparable_saved_results(self):
        current = compare_rehearsals(rehearse_bedroom(*self.source[:2]),
                                     rehearse_bedroom(*self.source[:2], 'direct'))
        saved = json.loads(json.dumps(current))
        for mutation in (
            lambda value: value['candidates'][0]['metrics'].update(collision_count=0),
            lambda value: value['candidates'][1]['record'].update(scene_revision='other'),
            lambda value: value.update(synthetic_b_minus_a={'duration_s': -999}),
            lambda value: value.update(motion_authorized=True),
        ):
            bad = copy.deepcopy(saved)
            mutation(bad)
            with self.assertRaises(ValueError):
                evaluate_bedroom_comparison(bad)
        failed = rehearse_bedroom(*self.source[:2], 'direct')
        failed = {**failed, 'status': 'MISSION_EXPIRED'}
        failed['revision'] = canonical_sha256({k:v for k,v in failed.items() if k!='revision'})
        report = evaluate_bedroom_comparison(compare_rehearsals(rehearse_bedroom(*self.source[:2]), failed))
        self.assertFalse(report['eligible_for_efficiency_comparison'])
        self.assertIsNone(report['synthetic_b_minus_a'])
        self.assertEqual(report['candidates'][1]['axes']['task_success']['status'], 'FAIL')

    def test_a4_historical_browser_export_is_not_silently_re_attested(self):
        historical = json.loads((ROOT/'artifacts/bedroom-comparison-browser-20260928-r2/comparison-export.json').read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            evaluate_bedroom_comparison(historical)

    def test_current_server_export_keeps_float_identity_and_rejects_stale_revision(self):
        review=BedroomReview(CommandBroker(),lambda:self.source)
        current=review.prepare(); comparison=review.compare(current['revision'],True)
        exported=review.export_comparison(current['revision'],True,comparison['revision'])
        raw=exported['json_text'].encode('utf-8')
        self.assertEqual(exported['sha256'],sha256(raw).hexdigest())
        self.assertIn('0.0',exported['json_text'])
        self.assertEqual(evaluate_bedroom_comparison(json.loads(raw))['source_comparison_revision'],comparison['revision'])
        with self.assertRaises(BrokerError):
            review.export_comparison(current['revision'],True,'0'*64)
        with self.assertRaises(BrokerError):
            review.export_comparison(current['revision'],False,comparison['revision'])

    def test_current_rehearsal_export_keeps_identity_and_old_js_export_stays_invalid(self):
        review=BedroomReview(CommandBroker(),lambda:self.source)
        current=review.prepare(); record=review.rehearse(current['revision'],'route',True)
        exported=review.export_rehearsal(current['revision'],'route',True,record['revision'])
        raw=exported['json_text'].encode('utf-8')
        self.assertEqual(exported['sha256'],sha256(raw).hexdigest())
        loaded=json.loads(raw)
        self.assertEqual(loaded['revision'],canonical_sha256({k:v for k,v in loaded.items() if k!='revision'}))
        with self.assertRaises(BrokerError):
            review.export_rehearsal(current['revision'],'route',True,'0'*64)
        with self.assertRaises(BrokerError):
            review.export_rehearsal(current['revision'],'route',False,record['revision'])
        historical=json.loads((ROOT/'artifacts/bedroom-mission-browser-20260928-r1/export.json').read_text(encoding='utf-8'))
        self.assertNotEqual(historical['revision'],canonical_sha256({k:v for k,v in historical.items() if k!='revision'}))

    def test_compare_rejects_changed_conditions_or_record_integrity(self):
        a=rehearse_bedroom(*self.source[:2]);b=rehearse_bedroom(*self.source[:2],'direct')
        for key,value in (('scene_revision','other'),('manifest_revision','other'),('start_pose',(1,2,3)),('waypoints',((1,2),))):
            bad={**b,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):compare_rehearsals(a,bad)
        for change in ({'status':'fake'},{'motion_authorized':True},{'physical_validation':'PASS'}):
            with self.assertRaises(ValueError):compare_rehearsals(a,{**b,**change})

    def test_failed_arrival_never_wins_by_shorter_duration(self):
        a=rehearse_bedroom(*self.source[:2]);b=rehearse_bedroom(*self.source[:2],'direct')
        b={**b,'status':'MISSION_EXPIRED'}
        b['revision']=canonical_sha256({k:v for k,v in b.items() if k!='revision'})
        result=compare_rehearsals(a,b)
        self.assertFalse(result['eligible_for_efficiency_comparison']);self.assertIsNone(result['b_minus_a'])

    def test_prior_saved_trace_identity_preserved(self):
        prior=json.loads((ROOT/'artifacts/bedroom-mission-browser-20260928-r1/route.json').read_text(encoding='utf-8'))
        self.assertEqual(rehearse_bedroom(*self.source[:2])['revision'],prior['revision'])

    def test_comparison_requires_current_review_and_no_rehearsal_mutation(self):
        review=BedroomReview(CommandBroker(),lambda:self.source)
        with self.assertRaises(BrokerError):review.compare(self.source[1]['manifest_sha256'],True)
        state=review.prepare()
        with self.assertRaises(BrokerError):review.compare(state['revision'],False)
        original=copy.deepcopy(self.source[0].to_dict())
        review.compare(state['revision'],True)
        self.assertEqual(self.source[0].to_dict(),original)

    def test_fixed_mission_arrives_from_existing_photo_geometry(self):
        result=rehearse_bedroom(*self.source[:2])
        self.assertEqual(result['status'],'ARRIVED')
        self.assertEqual(result['scene_revision'],self.source[0].site.scene.revision)
        self.assertEqual(result['physical_validation'],'NOT_RUN')
        self.assertFalse(result['motion_authorized']);self.assertFalse(result['isaac_run'])
        self.assertGreater(result['command_count'],100)
        self.assertEqual(result['events'][-1]['proposed'],[0.,0.])
        self.assertTrue(any(e['proposed'][1]!=0 for e in result['events']))

    def test_obstacle_and_stale_scan_stop_with_zero_output(self):
        for scenario,reason in (('blocked','OBSTACLE_IN_SWEPT_ENVELOPE'),('stale_scan','SCAN_STALE')):
            result=rehearse_bedroom(*self.source[:2],scenario)
            self.assertEqual(result['status'],reason)
            last=result['events'][-1]
            self.assertEqual(last['decision']['linear_m_s'],0.)
            self.assertEqual(last['decision']['angular_rad_s'],0.)
            self.assertEqual(last['pose_before'],last['pose_after'])

    def test_synthetic_obstacle_stop_replan_and_arrival_are_one_record(self):
        before=copy.deepcopy(self.source[0].to_dict())
        record=rehearse_bedroom(*self.source[:2],'detour')
        self.assertEqual(record['status'],'ARRIVED')
        self.assertEqual(record['physical_validation'],'NOT_RUN')
        self.assertFalse(record['motion_authorized'])
        self.assertEqual(len(record['replan_events']),1)
        self.assertEqual(record['replan_events'][0]['status'],'NEW_SYNTHETIC_PATH')
        self.assertTrue(record['replan_events'][0]['output_zero'])
        stopped=[e for e in record['events'] if e.get('phase')=='synthetic_obstacle_stop']
        self.assertEqual(len(stopped),1)
        self.assertEqual(stopped[0]['pose_before'],stopped[0]['pose_after'])
        self.assertGreater(record['command_count'],100)
        self.assertEqual(checked_replay(*self.source[:2],
            {'scenario':'detour','revision':record['revision'],'frame':len(record['events'])}),record)
        self.assertEqual(self.source[0].to_dict(),before)

    def test_synthetic_no_path_is_terminal_not_an_arrival(self):
        record=rehearse_bedroom(*self.source[:2],'detour_no_path')
        self.assertEqual(record['status'],'NO_PATH')
        self.assertEqual(record['replan_events'][-1]['status'],'NO_PATH')
        self.assertTrue(record['replan_events'][-1]['output_zero'])
        self.assertEqual(record['events'][-1]['pose_before'],record['events'][-1]['pose_after'])
        self.assertFalse(any(e['t']>record['replan_events'][-1]['t'] for e in record['events']))

    def test_manual_and_mission_proposals_use_same_checked_adapter(self):
        outputs=[]
        for source in ('manual','mission'):
            a=RehearsalAdapter(self.source[0].site.scene,(0.,-.65,0.))
            scan=LocalScan((.2,)*72,0.,'base_link','synthetic_model','synthetic_raycast')
            outputs.append(a.apply(source,.03,0.,scan,0.))
            self.assertEqual(a.pose,(0.,-.65,0.));self.assertEqual(a.events[0]['proposed'],[.03,0.])
        self.assertEqual(outputs[0],outputs[1])

    def test_review_binding_and_no_engine_commands(self):
        broker=CommandBroker();review=BedroomReview(broker,lambda:self.source)
        with self.assertRaises(BrokerError):review.rehearse(self.source[1]['manifest_sha256'],'route',True)
        state=review.prepare()
        for rev,scenario,ack in ((state['revision'],'route',False),('0'*64,'route',True),(state['revision'],'live',True)):
            with self.assertRaises(BrokerError):review.rehearse(rev,scenario,ack)
        self.assertEqual(review.rehearse(state['revision'],'stale_scan',True)['status'],'SCAN_STALE')


if __name__=='__main__':unittest.main()
