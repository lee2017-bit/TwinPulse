# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exercise a reviewed local release outside the checkout, without installing.

Uses the existing Python runtime, not a new venv. Fixed device-free App/core
tests run from the packaged sources under -I. This is not clean-install,
target-binary, physical, or complete AD5 acceptance.
An explicitly selected saved scan is test input, not a release member. Its
original bytes are copied and hash-checked independently; no transport runs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
SAVED_SCAN_RELATIVE='artifacts/ros-scan-20260930T143239Z-c4b681f5'
SAVED_SCAN_FILES=('report.json','driver.log','before-board.log','after-board.log',
                  'ros-messages.raw','ros-messages.raw.footer.json')
TESTS=(
    'packages.twinpulse_core.tests.test_current_innovation_filter',
    'packages.twinpulse_core.tests.test_photo_line_basis',
    'packages.twinpulse_core.tests.test_survey_tracking_endpoints',
    'tests.integration.test_cold_start_mission',
    'tests.integration.test_mission_report_storage_failure',
    'tests.integration.test_mission_observation_boundaries',
    'tests.integration.test_recorded_replay_pacing',
    'tests.integration.test_automatic_comparison',
    'tests.integration.test_mission_cleanup_wall_time',
    'tests.integration.test_active_mission_display',
    'tests.integration.test_same_window_ros',
    'tests.integration.test_ros_scan_client',
    'tests.integration.test_remote_correction_guard',
    'tests.integration.test_r4_bridge_api',
    'tests.integration.test_a1b_engine_readiness',
    'tests.integration.test_packaged_nominal_geometry',
    'tests.integration.test_photo_placement',
    'tests.integration.test_scene_changes',
    'tests.integration.test_model_library',
    'tests.integration.test_chat_site_text_generation',
    'tests.integration.test_execution_diagnostics',
    'tests.integration.test_campaign_pricing_verification',
    'tests.integration.test_photo_geometry_live_budget',
)
CHILD=r'''
import io,json,pathlib,re,sys,unittest
root=pathlib.Path(sys.argv[1]).resolve()
sys.path[:0]=[str(root/'packages'/p/'src') for p in
    ('twinpulse_core','twinpulse_app','twinpulse_provider')]+[str(root)]
import twinpulse_core.current_mission_evidence as core
import twinpulse_app.automatic_mission_service as app
origins={m.__name__:str(pathlib.Path(m.__file__).resolve()) for m in (core,app)}
assert all(pathlib.Path(p).is_relative_to(root) for p in origins.values())
assert 'rclpy' not in sys.modules
suite=unittest.defaultTestLoader.loadTestsFromNames(json.loads(sys.argv[2]))
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=0).run(suite)
def diagnostic(test,trace):
    last=trace.strip().splitlines()[-1] if trace.strip() else ''
    kind=last.partition(':')[0]
    cause=last.partition(':')[2].strip()
    frames=[]
    for filename,line in re.findall(r'File "([^"]+)", line (\d+)',trace):
        p=pathlib.Path(filename)
        frames.append({'file':str(p.relative_to(root)) if p.is_relative_to(root) else 'RUNTIME_OR_STDLIB',
                       'line':int(line)})
    return {'test_id':test.id(),'exception_type':kind if re.fullmatch('[A-Za-z]{1,80}',kind) else 'REDACTED',
            'machine_cause':cause if re.fullmatch('[A-Z][A-Z0-9_]{0,119}',cause) else None,
            'frames':frames[-12:]}
report={'tests_run':result.testsRun,'failure_ids':[t.id() for t,_ in result.failures],
 'error_ids':[t.id() for t,_ in result.errors],'skips':[t.id() for t,_ in result.skipped],
 'unexpected_successes':[t.id() for t in result.unexpectedSuccesses],
 'import_origins':origins,'device_runtime_imported':'rclpy' in sys.modules,
 'diagnostics':[diagnostic(t,trace) for t,trace in (result.failures+result.errors)][:64],
 'passed':result.wasSuccessful() and not result.skipped and result.testsRun>0}
print('PACKAGED_RESULT='+json.dumps(report,allow_nan=False))
raise SystemExit(0 if report['passed'] else 2)
'''


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _checked_manifest(package):
    manifest=package/'release-manifest.json'
    data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    if data.get('schema')!='twinpulse-offline-release-1.0':raise ValueError('RELEASE_SCHEMA')
    files=data.get('files');seen=set()
    if not isinstance(files,list) or not 10<=len(files)<=1000:raise ValueError('RELEASE_FILE_BUDGET')
    for row in files:
        name=row['path'];path=package/name
        if (not isinstance(name,str) or '\\' in name or Path(name).is_absolute()
                or any(part in {'.','..',''} for part in name.split('/'))
                or name.lower() in seen or path.is_symlink()
                or not path.resolve().is_relative_to(package)):
            raise ValueError('RELEASE_UNSAFE_PATH')
        seen.add(name.lower())
        if not path.is_file() or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:
            raise ValueError('RELEASE_FILE_HASH_MISMATCH')
    return package,data,sha(manifest)


def checked_package(package):
    package=Path(package).resolve()
    if not package.is_relative_to(ROOT/'artifacts/offline-release'):
        raise ValueError('REVIEWED_LOCAL_RELEASE_REQUIRED')
    return _checked_manifest(package)


def provide_saved_scan(isolated):
    folder=ROOT/SAVED_SCAN_RELATIVE
    if not folder.resolve().is_relative_to(ROOT) or folder.is_symlink():raise ValueError('SAVED_SCAN_INPUT_PATH')
    paths=[folder/name for name in SAVED_SCAN_FILES]
    if any(not p.is_file() or p.is_symlink() for p in paths):raise ValueError('SAVED_SCAN_TEST_INPUT_MISSING')
    if sum(p.stat().st_size for p in paths)>2*1024*1024:raise ValueError('SAVED_SCAN_TEST_INPUT_BUDGET')
    hashes={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    target=isolated/SAVED_SCAN_RELATIVE;target.mkdir(parents=True,exist_ok=False)
    for p in paths:
        shutil.copyfile(p,target/p.name)
        if sha(target/p.name)!=hashes[p.relative_to(ROOT).as_posix()]:raise ValueError('SAVED_SCAN_INPUT_HASH_CHANGED')
    return hashes


def _run_owned_runtime(command,isolated,stdout,stderr):
    """Reuse the launcher's existing ownership boundary, not process-name kills."""
    job=None;child=None
    if os.name=='nt':
        sys.path[:0]=[str(isolated/'packages'/p/'src') for p in
                      ('twinpulse_core','twinpulse_app','twinpulse_provider')]
        from twinpulse_app.process_manager import _WindowsJob
        origin=Path(sys.modules['twinpulse_app.process_manager'].__file__).resolve()
        if not origin.is_relative_to(isolated):raise ValueError('PACKAGE_CLEANUP_IMPORT_ORIGIN')
        job=_WindowsJob('offline-package-verifier')
    try:
        child=subprocess.Popen(command,cwd=isolated,stdout=stdout,stderr=stderr,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW) if os.name=='nt' else 0)
        if job:job.assign(child)
        code=child.wait(timeout=360)
        remaining=job.active_process_count() if job else 0
        return {'returncode':code,'owned_tree':'WINDOWS_JOB_CLOSED' if job else 'OWNED_PROCESS_EXITED',
                'descendants_before_close':remaining}
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if job:job.terminate()
                else:child.kill()
                child.wait(timeout=5)
        if job:job.close()


def run_runtime_cases(isolated,output,isaac_python):
    """Fixed actual runtime cases. No caller-supplied commands or test IDs."""
    runtime=Path(isaac_python).resolve()
    playwright=ROOT/'apps/twinpulse-web/node_modules/@playwright/test/index.mjs'
    if not runtime.is_file() or runtime.name.lower()!='python.bat':raise ValueError('EXISTING_ISAAC_PYTHON_REQUIRED')
    if not playwright.is_file():raise ValueError('EXISTING_PLAYWRIGHT_REQUIRED')
    if not (isolated/'apps/twinpulse-web/e2e/packaged-mission-isaac.mjs').is_file():raise ValueError('PACKAGED_BROWSER_DRIVER_MISSING')
    cases=[]
    for name in ('normal','storage','geometry','startup'):
        destination=output/name
        script='verify_ad4_geometry_isaac.py' if name=='geometry' else 'verify_ad4_active_isaac.py'
        command=[str(runtime),'-B',str(isolated/'scripts'/script),str(destination)]
        if name=='startup':
            command=[sys.executable,'-I','-B',str(isolated/'scripts/verify_startup_failure_browser.py'),
                     '--artifact-dir',str(destination),'--recovery-isaac',str(runtime),'--playwright-module',str(playwright)]
        elif name!='geometry':command+=['--browser-case',name,'--playwright-module',str(playwright)]
        # Files rather than undrained stdout pipes: Kit can emit large logs.
        code=None;ownership={}
        try:
            with (output/(name+'-stdout.log')).open('xb') as stdout,(output/(name+'-stderr.log')).open('xb') as stderr:
                ownership=_run_owned_runtime(command,isolated,stdout,stderr)
            code=ownership['returncode']
            receipt=destination/('result.json' if name=='startup' else 'verification.json')
            body=json.loads(receipt.read_text(encoding='utf-8')) if receipt.is_file() else {'status':'FAIL','reason':'RUNTIME_REPORT_MISSING'}
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
            receipt=destination/('result.json' if name=='startup' else 'verification.json')
            body={'status':'FAIL','reason':'RUNTIME_CASE_EXCEPTION','error_type':type(exc).__name__,
                  'error_errno':exc.errno if isinstance(exc,OSError) else None}
        # Persist a typed outcome even if startup fails before a child report.
        cases.append({'case':name,'returncode':code,'report':str(receipt.relative_to(output)),
            'status':body.get('status'),'reason':body.get('reason'),'error_type':body.get('error_type'),
            'error_errno':body.get('error_errno'),'ownership':ownership,
            'frames':len(body.get('frames',[])),'active_receipts':len(body.get('active_receipts',[])),
            'geometry_receipts':len(body.get('geometry_receipts',[])),'browser':body.get('browser'),
            'import_origins':body.get('import_origins',{})})
        # A case failure never suppresses the other independent checks.
    return {'scope':'SAME_ISOLATED_PACKAGE_WEB_API_ISAAC_FIXED_NORMAL_STORAGE_GEOMETRY_STARTUP',
            'external_test_runtime':'EXISTING_NODE_CHROME_PLAYWRIGHT_ISAAC_NO_INSTALL',
            'playwright_sha256':sha(playwright),'cases':cases,
            'passed':all(c['status']=='PASS' and c['returncode']==0 for c in cases)}


def verify(package,output,*,saved_scan_fixture=False,isaac_python=None,runtime_only=False):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'artifacts') or output==ROOT/'artifacts':
        raise ValueError('OWNED_ARTIFACT_OUTPUT_REQUIRED')
    output.mkdir(parents=True,exist_ok=False)
    report={'schema':'packaged-automatic-demo-offline-1.0','status':'FAILED',
        'tests':list(TESTS),'python_runtime':'EXISTING_NO_INSTALL',
        'clean_install':'NOT_RUN','target_binary':'NOT_BUILT','isaac':'NOT_RUN',
        'robot_connections':0,'physical_validation':'NOT_RUN',
        'offline_implementation_ready':False,'physical_demo_ready':False}
    sources=('scripts/verify_packaged_automatic_demo.py','scripts/build_offline_release.ps1')
    driver_hashes={p:sha(ROOT/p) for p in sources}
    stage='RELEASE_MANIFEST';isolated=None
    try:
        if runtime_only and not isaac_python:raise ValueError('RUNTIME_ONLY_REQUIRES_ISAAC')
        package,manifest,identity=checked_package(package)
        report.update(package=str(package),release_id=manifest['release_id'],
            development_release=manifest.get('dirty'),member_count=len(manifest['files']),
            web_build_mode=manifest.get('web_build_mode','FROZEN_BUILD'),manifest_sha256=identity)
        with TemporaryDirectory(prefix='twinpulse-packaged-') as directory:
            stage='ISOLATED_COPY'
            isolated=Path(directory).resolve()
            if isolated.is_relative_to(ROOT):raise ValueError('CHECKOUT_OUTSIDE_ISOLATION_REQUIRED')
            for row in manifest['files']:
                target=isolated/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(package/row['path'],target)
            shutil.copyfile(package/'release-manifest.json',isolated/'release-manifest.json')
            _,_,copied_identity=_checked_manifest(isolated)
            if copied_identity!=identity:raise ValueError('ISOLATED_COPY_MANIFEST_CHANGED')
            environment=dict(os.environ)
            # The -I parent deliberately ignores the caller's PYTHONPATH. Its
            # owned test subprocesses must also resolve only packaged modules,
            # rather than depending on a developer shell or the checkout.
            environment['PYTHONPATH']=os.pathsep.join([str(isolated)]+[
                str(isolated/'packages'/p/'src') for p in
                ('twinpulse_core','twinpulse_app','twinpulse_provider')])
            evidence=isolated/'artifacts/demo-preflight/packaged'
            environment['TWINPULSE_PREFLIGHT_EVIDENCE']=str(evidence)
            environment['PYTHONIOENCODING']='utf-8'
            inputs=provide_saved_scan(isolated) if saved_scan_fixture else {}
            report['test_input_scope']='EXPLICIT_SAVED_SCAN_NOT_RELEASE_MEMBER' if inputs else 'NO_EXTERNAL_TEST_INPUT'
            report['test_input_sha256']=inputs
            stage='ISOLATED_APP_CORE'
            if runtime_only:
                report['child']={'status':'NOT_RUN','passed':False,'tests_run':0,'reason':'EXPLICIT_RUNTIME_ONLY_SCOPE'}
            else:
                result=subprocess.run([sys.executable,'-I','-B','-c',CHILD,str(isolated),json.dumps(TESTS)],
                    cwd=isolated,env=environment,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=900)
                # Capture BEFORE cleanup; never lose completed test results.
                lines=[s[len('PACKAGED_RESULT='):] for s in result.stdout.splitlines() if s.startswith('PACKAGED_RESULT=')]
                report['returncode']=result.returncode
                report['child']=json.loads(lines[-1]) if lines else {'passed':False,'reason':'CHILD_REPORT_MISSING'}
            (output/'app-core-result.json').write_text(json.dumps(report['child'],indent=2),encoding='utf-8')
            if isaac_python:
                stage='PACKAGED_RUNTIME_CASES'
                runtime_output=output/'runtime';runtime_output.mkdir()
                report['runtime']=run_runtime_cases(isolated,runtime_output,isaac_python)
                report['isaac']='ACTUAL_PACKAGED_RUNTIME_PASS' if report['runtime']['passed'] else 'ACTUAL_PACKAGED_RUNTIME_FAILED'
                report['runtime_artifact_sha256']={p.relative_to(output).as_posix():sha(p)
                    for p in sorted(runtime_output.rglob('*')) if p.is_file()}
            if evidence.exists():
                stage='PRESERVE_EXECUTED_EVIDENCE'
                shutil.copytree(evidence,output/'executed-evidence')
                report['executed_artifact_sha256']={str(p.relative_to(output)):sha(p) for p in
                    sorted((output/'executed-evidence').rglob('*')) if p.is_file()}
            _,_,after_copy=_checked_manifest(isolated)
            if after_copy!=identity:raise ValueError('ISOLATED_COPY_MANIFEST_CHANGED')
            if any(sha(ROOT/p)!=h or sha(isolated/p)!=h for p,h in inputs.items()):raise ValueError('SAVED_SCAN_INPUT_HASH_CHANGED')
            report['test_input_unchanged']=True
            report['isolation']='DECLARED_FILES_OUTSIDE_CHECKOUT_EXISTING_RUNTIME'
            stage='ISOLATED_COPY_CLEANUP'
        report['isolated_copy_removed']=True
        # Fixed tests expose only bounded structured outcomes, not exception
        # text, credentials, or a user's environment. No arbitrary test IDs.
        stage='FINAL_RELEASE_RECHECK'
        if runtime_only:
            _,_,after=checked_package(package)
            if after!=identity:raise ValueError('RELEASE_MANIFEST_CHANGED')
            if report['runtime']['passed']:report['status']='PACKAGED_RUNTIME_ONLY_PASS'
        elif result.returncode==0 and report['child'].get('passed') and not report['child']['device_runtime_imported']:
            # Recheck after execution; a concurrent source/package edit cannot
            # silently qualify the old manifest or a different source snapshot.
            _,_,after=checked_package(package)
            if after!=identity:raise ValueError('RELEASE_MANIFEST_CHANGED')
            report['status']='PACKAGED_APP_CORE_OFFLINE_PASS'
            if isaac_python:
                report['status']='PACKAGED_WEB_API_ISAAC_OFFLINE_PASS' if report['runtime']['passed'] else 'FAILED'
    except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
        cause=str(exc)
        report.update(error_type=type(exc).__name__,error_stage=stage,
            reason=cause if re.fullmatch('[A-Z][A-Z0-9_]{0,119}',cause) else 'PACKAGED_CHECK_EXCEPTION_REDACTED',
            error_errno=exc.errno if isinstance(exc,OSError) else None)
        if isinstance(exc,OSError) and exc.filename and isolated:
            filename=Path(exc.filename).resolve()
            report['error_file']=str(filename.relative_to(isolated)) if filename.is_relative_to(isolated) else 'OUTSIDE_ISOLATED_COPY'
        if stage=='ISOLATED_COPY_CLEANUP':
            report['isolated_copy_removed']=False
            report['retained_isolation']=str(isolated)
    finally:
        report['source_sha256']=driver_hashes
        report['driver_unchanged']=all(sha(ROOT/p)==h for p,h in driver_hashes.items())
        if not report['driver_unchanged']:
            report.update(status='FAILED',reason='VERIFICATION_DRIVER_CHANGED')
        (output/'verification.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--saved-scan-fixture',action='store_true',help='Provide fixed saved raw as separate immutable test input; never SSH')
    parser.add_argument('--isaac-python',type=Path,help='Existing Isaac python.bat; run fixed same-package Web/API/Isaac cases without installation')
    parser.add_argument('--runtime-only',action='store_true',help='Explicit runtime-only scope; App/core tests are NOT_RUN, never full acceptance')
    args=parser.parse_args()
    report=verify(args.package,args.output,saved_scan_fixture=args.saved_scan_fixture,isaac_python=args.isaac_python,runtime_only=args.runtime_only)
    print(json.dumps({'status':report['status'],'report':str(args.output/'verification.json'),
        'physical_validation':'NOT_RUN','offline_implementation_ready':False},allow_nan=False))
    return 0 if report['status'] in ('PACKAGED_APP_CORE_OFFLINE_PASS','PACKAGED_WEB_API_ISAAC_OFFLINE_PASS','PACKAGED_RUNTIME_ONLY_PASS') else 2


if __name__=='__main__':raise SystemExit(main())
