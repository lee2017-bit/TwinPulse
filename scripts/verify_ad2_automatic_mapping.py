# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Saved evidence through the actual App service. Never contacts a robot.

Sessions are independent: rejection or corruption cannot hide the other sessions.
Processing PASS, model alignment and physical readiness are separate results.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.automatic_demo_service import AutomaticDemoService

JOBS=('4493be87ef7643ababb661b4a12f0180','b6cf346718da44b99e7bffe6f7919bbf','1a7f033af112437699ca67aef3438ecb')
SOURCES=('scripts/verify_ad2_automatic_mapping.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_demo_service.py',
    'packages/twinpulse_app/src/twinpulse_app/recorded_replay.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_photo_alignment.py',
    'packages/twinpulse_app/src/twinpulse_app/saved_mapping_evidence.py')


def hashes(folder):
    if not folder.is_dir() or folder.is_symlink():raise ValueError('ORIGINAL_FOLDER_MISSING_OR_UNSAFE')
    paths=sorted(folder.rglob('*'))
    if any(p.is_symlink() for p in paths):raise ValueError('ORIGINAL_SYMLINK_REJECTED')
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file()}


def failure(exc,stage):
    code=getattr(exc,'code',None) or str(exc)
    code=code.upper() if isinstance(code,str) else ''
    return {'status':'FAIL','error_type':type(exc).__name__,
        'reason':code if re.fullmatch('[A-Z][A-Z0-9_]{0,119}',code) else 'VERIFIER_EXCEPTION_REDACTED',
        'errno':exc.errno if isinstance(exc,OSError) else None,'error_stage':stage}


def run_batch(root, *, jobs=JOBS, reference_map=None, photo_policy='align_only',
              replay_mode='as_fast', service_factory=AutomaticDemoService):
    root=Path(root).resolve()
    if not jobs or any(job not in JOBS for job in jobs) or len(set(jobs))!=len(jobs):
        raise ValueError('SAVED_SESSION_ALLOWLIST')
    if reference_map and len(jobs)!=1:raise ValueError('REFERENCE_REQUIRES_ONE_SESSION')
    sources={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in SOURCES}
    rows=[];worker_unreaped=False
    for source_id in jobs:
        folder=root/'artifacts/manual-control'/source_id
        row={'source_job_id':source_id,'raw_folder':str(folder),'status':'FAIL'}
        service=None;before=None;stage='ORIGINAL_HASH_BEFORE';started=time.monotonic()
        try:
            before=hashes(folder);row['original_sha256']=before
            if worker_unreaped:
                row.update(status='SKIPPED_DEPENDENCY',reason='PREVIOUS_WORKER_NOT_REAPED')
            else:
                stage='START_SHARED_APP';service=service_factory(root,'default')
                service.start('ad2-offline-verifier',source_id,reference_map,photo_policy,replay_mode)
                stage='WAIT_SHARED_APP';service.worker.join(timeout=765 if replay_mode=='recorded_1x' else 165)
                if service.worker.is_alive():raise ValueError('AUTOMATIC_PROCESSING_DID_NOT_END')
                job=service.snapshot('ad2-offline-verifier')['job']
                row['job_state']=job['state'];row['replay_timing']=job.get('replay_timing')
                if job['state']!='COMPLETED':
                    stage=job.get('error_stage') or 'SHARED_APP_FAILED'
                    raise ValueError(job.get('error') or 'AUTOMATIC_PROCESSING_FAILED')
                stage='VERIFY_RESULT_AND_REOPEN'
                if replay_mode=='recorded_1x':
                    timing=job['replay_timing']
                    assert job['elapsed_s']+.001>=timing['receipt_span_s']
                    assert timing['processing_elapsed_s']<150 and timing['pending_event_bound']==1
                    assert not timing['timing_verified'] and not timing['motion_authorized']
                report=job['result'];reopened=service.reopen('ad2-offline-verifier',job['map_id'])
                assert reopened['pose_candidate'] is None and reopened['motion_authorized'] is False
                assert report['motion_authorized'] is False and report['alignment_verified'] is False
                photo=report.get('photo_alignment')
                if photo:
                    assert photo['alignment_verified'] is False and photo['motion_authorized'] is False
                    assert not set(photo.get('fit_sequences',[]))&set(photo.get('validation_sequences',[]))
                    assert reopened['photo_alignment']['report_revision']==photo['report_revision']
                row.update(status='PASS',reference_map_id=reference_map,derived_map_id=job['map_id'],
                    counts=report['counts'],reasons=report['reasons'],localization_state=report['state'],
                    source_status=report['source_status'],source_reason=report['source_reason'],
                    keyframes=report['keyframe_count'],map_cells=len(report['corrected_cells']),
                    odom_cells=len(report['odom_cells']),loop_status=report['loop_status'],
                    reference_eligible=report['reference_eligible'],cache_builds=report['cache_builds'],
                    transitions=report['transitions'],reopen_without_pose=True,
                    photo_alignment={k:v for k,v in photo.items() if k in
                        ('status','reason','policy','geometry_status','applied_revision','fit_error_m',
                         'validation_before_m','validation_after_m','alternative_margin_m','fit_sequences',
                         'validation_sequences','room_base_revision','photo_revision','report_revision',
                         'nominal_geometry_revision','residual_diagnosis')} if photo else None)
        except Exception as exc:
            row.update(failure(exc,stage))
            if service and service.job:
                try:
                    job=service.snapshot('ad2-offline-verifier')['job']
                    row['last_job']={k:job.get(k) for k in ('state','error','error_stage','progress_sequence','replay_timing')}
                except Exception as diagnostic:
                    row['diagnostic_failure']=failure(diagnostic,'FAILED_JOB_SNAPSHOT')
        finally:
            if service:
                try:service.close()
                except Exception as cleanup:
                    row['cleanup_failure']=failure(cleanup,'CLOSE_SHARED_APP');row['status']='FAIL'
                worker_unreaped=bool(service.worker and service.worker.is_alive())
                row['worker_reaped']=not worker_unreaped
                if worker_unreaped:row.update(status='FAIL',cleanup_error='WORKER_NOT_REAPED')
            try:
                after=hashes(folder);row['originals_unchanged']=before is not None and after==before
                if before is not None and after!=before:
                    row['original_after_sha256']=after
                    row.update(status='FAIL',integrity_error='ORIGINAL_CHANGED')
            except Exception as exc:
                row['originals_unchanged']=False;row['integrity_failure']=failure(exc,'ORIGINAL_HASH_AFTER')
                row['status']='FAIL'
            row['seconds']=time.monotonic()-started;rows.append(row)
    source_unchanged=all((root/p).is_file() and hashlib.sha256((root/p).read_bytes()).hexdigest()==digest for p,digest in sources.items())
    passed=source_unchanged and all(r['status']=='PASS' for r in rows)
    return {'schema':'ad2-actual-causal-verification-1.0','status':'PASS' if passed else 'FAIL','sessions':rows,
        'first_failure':next(({'source_job_id':r['source_job_id'],**{k:r.get(k) for k in
            ('reason','error_stage','integrity_error','cleanup_error')}} for r in rows if r['status']!='PASS'),None),
        'robot_contact':False,'physical_demo_ready':False,'timing_verified':False,
        'source_failure_not_repaired':True,'reference_eligibility_is_diagnostic_only':True,
        'photo_policy':photo_policy,'replay_mode':replay_mode,'source_sha256':sources,
        'verification_sources_unchanged':source_unchanged,'SAVED_REAL_ALIGNMENT_SUPPORTED':passed and all(
            r.get('photo_alignment') and r['photo_alignment']['status']=='ALIGNMENT_CANDIDATE' for r in rows)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--job',choices=JOBS);parser.add_argument('--reference-map')
    parser.add_argument('--photo-policy',choices=('disabled','align_only','correct_walls'),default='disabled')
    parser.add_argument('--replay-mode',choices=('as_fast','recorded_1x'),default='as_fast')
    args=parser.parse_args()
    if args.reference_map and not args.job:parser.error('--reference-map requires one explicit --job')
    if args.output.exists():parser.error('OUTPUT_ALREADY_EXISTS')
    try:
        report=run_batch(args.root,jobs=(args.job,) if args.job else JOBS,reference_map=args.reference_map,
                         photo_policy=args.photo_policy,replay_mode=args.replay_mode)
    except Exception as exc:
        report={'schema':'ad2-actual-causal-verification-1.0',**failure(exc,'BATCH_SETUP'),
                'robot_contact':False,'physical_demo_ready':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,sort_keys=True,indent=2,allow_nan=False)
    print(json.dumps({'status':report['status'],'output':str(args.output),'sessions':[
        {k:r.get(k) for k in ('source_job_id','status','reason','seconds')} for r in report.get('sessions',[])]}))
    return 0 if report['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
