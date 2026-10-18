# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import unittest
from scripts.prepare_benchmark_pilot import PAIRS
from scripts.benchmark_protocol import journey_packet,text_sha,schedule
from scripts.benchmark_pilot_report import count_recall,category,auxiliary


class PilotContractTests(unittest.TestCase):
    def test_auxiliary_count_is_capped_and_not_full_quality(self):
        self.assertEqual(count_recall({'chair':2},{'chair':20})['value'],1)
        self.assertEqual(count_recall({'chair':2},{'chair':1})['value'],.5)
        self.assertEqual(category('office chair'),'chair')
        reference=dict(minimum_counts={'chair':1},source='explicit_text_contract',coverage='declared',metric_dimensions=None)
        result=auxiliary(reference,{}, {})
        self.assertEqual(result['saved_required_kind_recall']['value'],0)
        self.assertEqual(result['full_quality'],'NOT_EVALUATED')
        self.assertEqual(result['human_reviewers'],0)

    def test_factor_comparisons_and_constraint_lane(self):
        self.assertEqual(len(PAIRS),5)
        self.assertEqual(len({row[0] for row in PAIRS}),5)
        self.assertIn(('flash-lightning','deepseek-ai/DeepSeek-V4.1-Flash','nvidia/Nemotron-3_5-Lightning'),PAIRS)
        self.assertIn(('luna-lightning','gpt-6-luna','nvidia/Nemotron-3_5-Lightning'),PAIRS)
        self.assertIn(('luna-luna','gpt-6-luna','gpt-6-luna'),PAIRS)

    def test_auxiliary_counts_warehouse_factory_once_not_its_generated_parts(self):
        reference=dict(minimum_counts={'shelf':2,'pallet':1},source='explicit_text_contract',
            coverage='declared',metric_dimensions=None)
        calls=[dict(tool='create_rack_row',arguments={'id':'row'+str(i)}) for i in range(2)]
        calls.append(dict(tool='place_pallet_stack',arguments={'id':'loaded'}))
        project=dict(site_draft=dict(plan=dict(calls=calls)))
        result=auxiliary(reference,{},project)
        self.assertEqual(result['saved_required_kind_recall']['matched'],2)
        calls.append(dict(tool='place_room_item',arguments=dict(id='empty',kind='pallet')))
        result=auxiliary(reference,{},project)
        self.assertEqual(result['saved_required_kind_recall']['value'],1)
        self.assertEqual(result['support_accuracy'],'NOT_EVALUATED')

    def test_auxiliary_answers_never_enter_model_packet(self):
        case=dict(case_id='example',room_group='room',split='development',modality='text',prompt='A room',
            prompt_sha256=text_sha('A room'),photo=None,goal=dict(text='Go to desk'),
            source=dict(external_transmission_allowed=True),annotations=dict(secret='oracle'),
            reference=dict(secret='auxiliary oracle'))
        packet=journey_packet(case)
        self.assertNotIn('annotations',packet);self.assertNotIn('reference',packet)
        self.assertNotIn('source',packet)

    def test_paired_repetitions_balanced_deterministic(self):
        manifest=dict(seed=61146,repeats=2,cases=[dict(case_id='case-'+str(i),room_group='room-'+str(i),
            split='development',modality='photo' if i<3 else 'text') for i in range(6)],
            configs=[dict(config_id=row[0]) for row in PAIRS])
        jobs=schedule(manifest)
        self.assertEqual(len(jobs),60);self.assertEqual(jobs,schedule(manifest))
        for block in range(12):
            rows=[j for j in jobs if j['block']==block]
            self.assertEqual(len(rows),5);self.assertEqual(len({(j['case_id'],j['repeat']) for j in rows}),1)
        counts={config:[sum(j['config_id']==config and j['position']==pos for j in jobs) for pos in range(5)]
            for config,_,_ in PAIRS}
        self.assertTrue(all(max(values)-min(values)<=1 for values in counts.values()))


if __name__=='__main__':unittest.main()
