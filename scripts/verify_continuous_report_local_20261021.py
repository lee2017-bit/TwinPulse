# SPDX-License-Identifier: Apache-2.0
"""Static local artifact/binding check, not rendered UI acceptance."""
from hashlib import sha256
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'outputs/robot-continuous-repair-20261021'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',choices=('25','27','31','33','35','37','39','41','43','45','47','53','57'),default='25')
    parser.add_argument('--expected-status',choices=('READY','NOT_READY'),help='Report QA only: does not alter the acceptance gate or App evidence.')
    parser.add_argument('--revision',choices=('','b','c','d'),default='',help='Preserve the prior static report receipt after a report revision.')
    args=parser.parse_args()
    missing=[]
    class QA(HTMLParser):
        def handle_starttag(self,tag,attrs):
            for key,value in attrs:
                if key in ('href','src') and value and not value.startswith(('http:','https:','#')) and not (ROOT/value).exists():missing.append(value)
    raw=(ROOT/'report.html').read_bytes();QA().feed(raw.decode('utf-8'))
    report=json.loads((ROOT/'result.json').read_text(encoding='utf-8'))
    assert not missing,missing
    expect_ready=args.expected_status=='READY' or args.expected_status is None and args.attempt in ('31','33')
    if expect_ready:
        assert report['gate_result']['status']=='READY_FOR_SUPERVISED_POWERED_TEST' and report['overall'].startswith('READY_FOR_')
        assert report['diagnostic_contract_fix']['value']['status']=='PASS' and not report['final_binding_issues']
        assert report['final_actual_scope']['ui-reproduction-'+report['final_reproduction_attempt']]['status']=='PASS'
    else:
        assert report['gate_result']['status']=='NOT_READY' and report['overall'].startswith('PARTIAL_NOT_READY')
        if args.attempt=='31':
            current=report['current_failed_review']['value']
            assert current['status']=='PARTIAL_NOT_READY_FINAL_UI_FAILED_ENVIRONMENT_UNRESOLVED'
            assert current['actual_attempt']=='31' and report['final_actual_scope']['ui-31']['status']=='FAIL'
            assert current['release_id']==report['current_installed']['release_id']
            assert 'RUN_NOT_PASS:fresh' in report['gate_result']['issues'] and report['final_binding_issues']
            assert not report.get('diagnostic_contract_fix'), 'Missing full UI download/cold roundtrip must not be labelled PASS'
    assert report['motion_review_source']['frozen_input_matches_protected_original05_receipt_segments_rows']
    candidate=report['motion_review_source']['frozen_candidate_groups'][0]['value']
    assert candidate['status']=='PASS' and candidate['source_unchanged'] and candidate['inspection_target']=='FROZEN_CANDIDATE_NOT_INSTALLED'
    assert report['final_attempt']==args.attempt
    if args.attempt=='27':
        memory=report['memory_retry27_29']['value']
        assert memory['status']=='FAIL_OBSERVED_CAUSE_UNRESOLVED' and memory['after_reboot']['status']=='NOT_RUN'
        assert report['final_actual_scope']['ui-reproduction-29']['status']=='FAIL'
        assert report['motion_review_source']['status']=='INSTALLED27_EXPLICIT_ANALYZE_AND_NEXT_COLD_GET_RESTORE_PASS_BODY_UNKNOWN'
    value=dict(status='PASS_STATIC_ONLY',report_sha256=sha256(raw).hexdigest(),report_links='PASS',gate=report['gate_result']['status'],
        protected_segments=len(report['original_archive']),candidate_status=candidate['status'],remaining_usd=report['budget_final']['remaining_additional_50_usd'],
        expected_status='READY' if expect_ready else 'NOT_READY',
        limits='Not rendered report screenshot, installed UI or hardware acceptance. The original failed whole journey remains failed.')
    suffix='-reboot30' if args.attempt=='27' and 'reboot_comparison30' in report else ''
    if suffix:
        assert report['reboot_comparison30']['value']['issues']==[]
        assert report['reboot_comparison30']['same_source_ui']['status']=='PASS'
        assert report['reboot_comparison30']['value']['original29_chair']['status']=='FAIL'
        assert report['reboot_comparison30']['value']['after30_chair']['status']=='PASS'
        assert report['gate_result']['status']=='NOT_READY'
    with (ROOT/f'report-static-check{args.attempt}{suffix}{args.revision}.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
    print(json.dumps(value))

if __name__=='__main__':main()
