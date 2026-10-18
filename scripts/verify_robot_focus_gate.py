"""Read-only final evidence gate. Never runs an App/model/robot or repairs data."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path

REQUIRED={
 'fresh':[
  'Robots menu PC preparation and connection entry while hardware stays OFF',
  'Visible New chat and original robot-containing scene brief',
  'Real provider generation and current Isaac frame',
  'Register two robots through Manage form',
  'Two simultaneous real Isaac SIM connections and independent scan',
  'Held button moves selected robot; release retains both connections and scans',
  'All four normal pointer directions without injected delay',
  'Continuous 60-second held SIM rotation keeps session, sensor and fresh input',
  'FAULT INJECTION: delayed drive dispatch pauses, retains connection, needs fresh input',
  'FAULT MATRIX: 100/250/500/1000ms dispatch gaps preserve session and never replay after confirmed Stop',
  'Keyboard hold and control focus loss pause without disconnect',
  'WASD and all arrow key releases; Space stops without replay',
  'Main chat bounded 90 degree command, measured completion',
  'One session full turn with actual simulated scan',
  'LiDAR Off pauses but retains connection; On restarts sensor',
  'Actual obstacle approach stops Beta and fresh reverse escapes',
  'Named chat Stop interrupts finite task without model call or disconnect',
  'Two named finite tasks coexist; visible Stop all confirms both without disconnect',
  'Operation summary opens; raw JSON download is separate',
  'Actual frame anchors and camera transition',
  'Physical setup shown while robot remains off; no Connect or movement',
  'App-only supervised setup saves offline; all eleven trial paths visible without physical activation',
  'In-App measured-profile editor preserves identity and blocks null or mismatched measurements',
  'Explicit static estimated physical marker in actual Isaac; not tracking or localization',
  'Visible Exit TwinPulse normal shutdown'],
 'cold':[
  'Robots menu PC preparation and connection entry while hardware stays OFF',
  'Cold restore preserves definitions but no motion authority',
  'Historical operation reopened and downloaded without reconnecting',
  'Explicitly display saved Twin in current Isaac; no automatic motion restore',
  'Cold new explicit SIM connection; actual backward and right pad buttons',
  'App-only supervised setup saves offline; all eleven trial paths visible without physical activation',
  'Visible Exit TwinPulse normal shutdown'],
 'lineage':[
  'Actual installed startup and saved chat open',
  'Explicit saved Twin display in current Isaac',
  'Register and explicitly connect a new SIM operation',
  'Actual finite command and LiDAR observation link to chat and exact scene',
  'Stop all retains original request identity in operation',
  'Actual reviewed scene change and Undo preserve per-event revisions',
  'Project switch closes old operation without relabelling old events',
  'Exit through installed App button'],
 'lineage_cold':[
  'Actual installed startup and saved chat open',
  'Cold history does not restore authority and retains exact Twin reference',
  'Exit through installed App button']}
ROLES=set(REQUIRED)|{'normal','lifecycle','installation','supplementary','budget'}

def validate_records(records,release,source):
    issues=[]
    for role in sorted(ROLES-records.keys()):issues.append('MISSING_ROLE:'+role)
    for role,steps in REQUIRED.items():
        row=records.get(role,{})
        if row.get('status')!='PASS':issues.append('RUN_NOT_PASS:'+role)
        if row.get('desktop',{}).get('engine',{}).get('release_id')!=release:issues.append('WRONG_RELEASE:'+role)
        actual={s.get('name'):s for s in row.get('steps',[])}
        for name in steps:
            if actual.get(name,{}).get('status')!='PASS':issues.append('MISSING_OR_FAILED_STEP:'+role+':'+name)
        if any(s.get('status')!='PASS' for s in row.get('steps',[])):issues.append('FAILED_STEP:'+role)
        if row.get('http_errors') or row.get('errors') or row.get('page_errors'):issues.append('UNRESOLVED_UI_ERROR:'+role)
        if any(not r.get('exiting') and not r.get('fault') for r in row.get('request_failures',[])+row.get('request_failed',[])):
            issues.append('UNCLASSIFIED_REQUEST_FAILURE:'+role)
    for role,phase in [('fresh','fresh'),('cold','reopen'),('lineage','run'),('lineage_cold','cold')]:
        if records.get(role,{}).get('phase')!=phase:issues.append('SPLIT_OR_WRONG_PHASE:'+role)
    for first,second in [('fresh','cold'),('lineage','lineage_cold')]:
        if not records.get(first,{}).get('project') or records[first]['project']!=records.get(second,{}).get('project'):
            issues.append('PROJECT_MISMATCH:'+first+':'+second)
    fresh=records.get('fresh',{});steps={s.get('name'):s for s in fresh.get('steps',[])}
    for name,angle in [('Main chat bounded 90 degree command, measured completion',math.pi/2),
                       ('One session full turn with actual simulated scan',2*math.pi)]:
        delta=steps.get(name,{}).get('evidence',{}).get('delta')
        if type(delta) not in (int,float) or not math.isfinite(delta) or abs(delta-angle)>.01:issues.append('ORIGINAL_ANGLE_NOT_PROVEN:'+name)
    if records.get('lineage',{}).get('requested_command')!='left 90 degrees':issues.append('ORIGINAL_LINEAGE_90_NOT_RUN')
    normal=records.get('normal',{})
    if (normal.get('status')!='PASS_NORMAL_START_REUSE_DEBUG_OFF' or normal.get('release_id')!=release
            or normal.get('source_sha256')!=source or type(normal.get('ready_wait_ms')) not in (int,float)
            or not 0<normal.get('ready_wait_ms',0)<=120000 or normal.get('debug_listener_count')!=0
            or normal.get('app_listener_count')!=1 or normal.get('repeated_start_same_owner') is not True):issues.append('NORMAL_START_NOT_QUALIFIED')
    install=records.get('installation',{})
    if install.get('status')!='PASS' or install.get('release_id')!=release or install.get('source_manifest_sha256')!=source or install.get('mismatches')!=[] or install.get('capabilities',{}).get('physical_robot') is not True:
        issues.append('INSTALLATION_NOT_EXACT')
    supplementary=records.get('supplementary',{})
    if (supplementary.get('status')!='PASS' or supplementary.get('source_sha256')!=source
            or supplementary.get('release_id')!=release or supplementary.get('source_unchanged') is not True
            or {g['name'] for g in supplementary.get('groups',[]) if g.get('status')=='PASS'}!={'lineage-and-pc','native-worker','field','ui','web-build'}):
        issues.append('SUPPLEMENTARY_MISSING_OR_FAILED')
    lifecycle=records.get('lifecycle',{})
    if (lifecycle.get('status')!='PASS' or lifecycle.get('release_id')!=release or lifecycle.get('source_sha256')!=source
            or lifecycle.get('normal_start_launch_id')!=normal.get('launch_id') or lifecycle.get('shutdown_clean') is not True
            or lifecycle.get('restart_ready') is not True or not lifecycle.get('restart_launch_id')
            or lifecycle.get('restart_launch_id')==normal.get('launch_id') or lifecycle.get('restart_debug_listener_count')!=0
            or lifecycle.get('restart_app_listener_count')!=1 or lifecycle.get('restart_authenticated_ready') is not True
            or type(lifecycle.get('restart_ready_wait_ms')) not in (int,float)
            or not 0<lifecycle.get('restart_ready_wait_ms',0)<=120000):
        issues.append('NORMAL_LIFECYCLE_NOT_QUALIFIED')
    if records.get('budget',{}).get('within_approved_total') is not True:issues.append('BUDGET_UNCONFIRMED_OR_EXCEEDED')
    return issues

def load_evidence(manifest,root):
    records={};receipts=[];issues=[]
    for entry in manifest.get('evidence',[]):
        role=entry.get('role');relative=entry.get('path','');path=(root/relative).resolve()
        if role not in ROLES or role in records or not path.is_relative_to(root.resolve()):
            issues.append('INVALID_OR_DUPLICATE_REFERENCE:'+str(role));continue
        try:
            raw=path.read_bytes();digest=sha256(raw).hexdigest()
            if digest!=entry.get('sha256'):issues.append('EVIDENCE_HASH_MISMATCH:'+role);continue
            records[role]=json.loads(raw);receipts.append(dict(role=role,path=relative,sha256=digest))
        except (OSError,ValueError):issues.append('UNREADABLE_EVIDENCE:'+str(role))
    return records,receipts,issues

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.manifest.resolve().parent
    manifest=json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    records,receipts,issues=load_evidence(manifest,root)
    active=json.loads((Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json').read_text(encoding='utf-8-sig'))
    release=active['release_id'];source=active['source_manifest_sha256']
    if manifest.get('release_id')!=release or manifest.get('source_sha256')!=source:issues.append('NOT_ACTIVE_INSTALLED_RELEASE')
    issues+=validate_records(records,release,source)
    result=dict(schema='robot-focused-evidence-gate-1.0',checked_at_utc=datetime.now(timezone.utc).isoformat(),
        status='NOT_READY' if issues else 'READY_FOR_SUPERVISED_POWERED_TEST',release_id=release,source_sha256=source,
        issues=issues,evidence=receipts,physical_outcomes='NOT_RUN_ROBOT_OFF',
        limitation='PC software acceptance only; not physical stopping/localization/robot success or a guarantee against all defects.')
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False));return 1 if issues else 0
if __name__=='__main__':raise SystemExit(main())
