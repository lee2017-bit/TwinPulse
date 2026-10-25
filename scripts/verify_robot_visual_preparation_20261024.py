# SPDX-License-Identifier: Apache-2.0
"""Read-only impact acceptance. Not a new robot/runtime admission gate.

This does not replace or mark the broader F01-F12 gate complete. Original
records are hash-bound; negative tests operate on copies, never saved results.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from verify_roomplan_preparation_gate import ui_issues, hold_and_map_issues, stop_and_target_issues, edit_revision_chain
from roomplan_runtime_copy_gate import check_runtime_copy


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def verify(records, release, source):
    issues = []
    for role in ('import', 'edit', 'sim', 'cold'):
        row = records.get(role, {})
        # Numeric edit has the same three edit/ACK/Undo steps but makes no
        # model-proposal claim. Do not rewrite the original phase or record.
        issues += ui_issues('ai_edit' if role=='edit' else role,row,release,expected_phase=role)
    issues += hold_and_map_issues(records.get('sim',{}),'844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b')
    issues += stop_and_target_issues(records.get('sim',{}))
    edit=records.get('edit',{})
    if not edit_revision_chain(edit,edit.get('edit_origin',{}).get('scene_revision'),first_preview_action='move_preview'):
        issues.append('UNBOUND_NUMERIC_EDIT_UNDO')
    for role, names in {
        'marker': ['Offline physical model placement', 'Physical sensor panel disconnected',
                   'Physical model body captured', 'Unclipped physical controls at both sizes'],
        'extra': ['Two SIM connections and independent sensors', 'Keyboard and bounded 90 degree command',
                  'Exact Stop all ACK and engine application', 'SIM sensors OFF and disconnect'],
        'restore': ['Cold estimated marker and no physical authority', 'Original failed physical history preserved', 'Exact original pause in read-only timeline'],
    }.items():
        row = records.get(role, {})
        if row.get('identity', {}).get('engine', {}).get('release_id') != release:
            issues.append('WRONG_RELEASE:' + role)
        events = {e.get('name'): e.get('evidence', {}) for e in row.get('events', [])}
        for name in names:
            if events.get(name, {}).get('status') != 'PASS':
                issues.append('MISSING_STEP:' + role + ':' + name)
        if row.get('errors'):
            issues.append('UI_ERROR:' + role)
        if events.get('Physical actions', {}).get('hardware_actions') != 0:
            issues.append('PHYSICAL_ACTIONS_NOT_ZERO:' + role)
    marker={e.get('name'):e.get('evidence',{}) for e in records.get('marker',{}).get('events',[])}
    for sample in marker.get('Unclipped physical controls at both sizes',{}).get('samples',[]):
        if not all(sample.get(k) is True for k in ('canvas_visible','stop_visible','pad_visible','robot_badge_visible')) or sample.get('origin_marker_count')!=0:
            issues.append('CLIPPED_PHYSICAL_CONTROLS')
    if len(marker.get('Unclipped physical controls at both sizes',{}).get('samples',[]))!=2:
        issues.append('MISSING_PHYSICAL_LAYOUT_SAMPLES')
    panel=marker.get('Physical sensor panel disconnected',{})
    if panel.get('physical_scan_svg_count')!=0 or panel.get('sim_visualization_selector_count')!=0 or 'Disconnected · no live scan' not in panel.get('text',''):
        issues.append('STALE_OR_SIM_SCAN_IN_PHYSICAL_PANEL')
    restored={e.get('name'):e.get('evidence',{}) for e in records.get('restore',{}).get('events',[])}
    pause=restored.get('Exact original pause in read-only timeline',{})
    if any(pause.get(k)!=v for k,v in {'operation_id':'490bf6806c064797b087177aef632f8e','connection_epoch':'d611f49c90394669901264fe3742bca2','source_segment_sha256':'26600372789497ae6f22dea4f08b75fed35169c63a007c7b6540ff9c99796b5c','source_line':546,'sequence':22669,'pause_id':'d611f49c90394669901264fe3742bca2:19','reason':'FIELD_DIRECTION_COVERAGE_GAP','physical_actions':0}.items()):
        issues.append('ORIGINAL_PAUSE_NOT_BOUND')
    extra={e.get('name'):e.get('evidence',{}) for e in records.get('extra',{}).get('events',[])}
    stopped=extra.get('Exact Stop all ACK and engine application',{})
    before=stopped.get('before',[]);response=stopped.get('response',{});acks=stopped.get('engine_acks',[])
    if len(before)!=2 or stopped.get('request',{}).get('action')!='stop_all':issues.append('UNBOUND_STOP_ALL')
    for prior in before:
        r=next((r for r in response.get('robots',[]) if r.get('robot_id')==prior.get('robot_id')),None)
        a=next((a for a in acks if a.get('robot_id')==prior.get('robot_id')),None)
        if (prior.get('kind')!='sim' or not r or not a or not r.get('motion_epoch') or r['motion_epoch']==prior.get('motion_epoch')
                or any(r.get(k)!=prior.get(k) or a.get(k)!=prior.get(k) for k in ('operation_id','connection_epoch'))
                or a.get('applied_motion_epoch')!=r['motion_epoch'] or a.get('control_state')!='PAUSED'):
            issues.append('UNBOUND_STOP_ALL')
    sup = records.get('supplementary', {})
    if sup.get('status') != 'PASS' or sup.get('release_id') != release or sup.get('source_sha256') != source or not sup.get('source_unchanged'):
        issues.append('SUPPLEMENTARY_NOT_CURRENT_PASS')
    replay = records.get('replay', {})
    if (replay.get('status') != 'PASS' or replay.get('frames') != 6081
            or replay.get('strict_incomplete') != 202 or replay.get('retained_complete_observations') != 201):
        issues.append('ORIGINAL_RAW_REPLAY_NOT_PASS')
    media = records.get('media', {})
    if media.get('status') != 'PASS' or not media.get('encoded_frames_visually_reviewed'):
        issues.append('MEDIA_NOT_VERIFIED')
    if records.get('installation', {}).get('receipt', {}).get('build_id') != release:
        issues.append('INSTALLATION_IDENTITY_MISMATCH')
    return issues


def runtime_issues(manifest,root,records):
    issues=[]
    expected={records.get(role,{}).get('versions',{}).get('engine',{}).get('launch_id') for role in ('import','cold')}
    seen=set()
    for ref in manifest.get('runtime_copies',[]):
        folder=(root/ref).resolve()
        if not folder.is_relative_to(root):
            issues.append('UNSAFE_RUNTIME');continue
        receipt=read(folder/'copy-receipt.json');launch=receipt.get('launch_id')
        if launch in seen or launch not in expected:issues.append('DUPLICATE_OR_UNBOUND_RUNTIME')
        seen.add(launch)
        issues += ['RUNTIME:'+str(v) for v in check_runtime_copy(folder,launch,receipt)]
        exits=read(folder/'owned-exit-observations.json');roles=exits.get('roles',{})
        if (exits.get('launch_id')!=launch or not exits.get('evidence_complete') or set(roles)!={'backend','engine'}
                or any(v.get('root_disposition')!='EXITED_DURING_GRACE' or v.get('return_code')!=0
                       or v.get('errors')!=[] or v.get('evidence_complete') is not True for v in roles.values())):
            issues.append('ROOT_EXIT_NOT_NORMAL')
        engine=read(folder/'engine-result.json');joins=engine.get('viewport_phase_diagnostics',{}).get('join_status',{})
        if (engine.get('cleanup_status')!='PRE_CLOSE_COMPLETE' or engine.get('cleanup_errors')!=[]
                or any(joins.get(k) is not False for k in ('viewport_alive','fleet_alive','diagnostic_alive'))
                or joins.get('scan_worker',{}).get('worker_alive') is not False):
            issues.append('INNER_CLEANUP_UNCONFIRMED')
    if None in expected or len(expected)!=2 or seen!=expected:issues.append('BOTH_CURRENT_LAUNCH_SHUTDOWNS_REQUIRED')
    return issues


def media_issues(manifest, root, records, release, source):
    """Bind the main review to these exact sessions, encoded clips and pixels."""
    media=records.get('media',{});issues=[]
    if media.get('release_id')!=release or media.get('source_sha256')!=source:
        issues.append('MEDIA_IDENTITY_MISMATCH')
    required={'import','edit','sim','cold','marker','extra','restore'}
    clips=media.get('clips',[])
    if len(clips)!=len(required) or {v.get('role') for v in clips}!=required:
        issues.append('MEDIA_SESSIONS_MISSING')
    def bound(ref):
        p=(root/ref.get('path','')).resolve()
        return (p.is_relative_to(root) and p.is_file() and not p.is_symlink() and not p.is_junction()
                and sha256(p.read_bytes()).hexdigest()==ref.get('sha256'))
    for clip in clips:
        role=clip.get('role');row=records.get(role,{})
        identity=row.get('versions',row.get('identity',{})).get('engine',{})
        session=manifest.get('refs',{}).get(role,{})
        expected=(Path(session.get('path','')).parent /
                  ('recording/app-screen.mp4' if role in {'import','edit','sim','cold'} else 'app-screen.mp4')).as_posix()
        if (clip.get('launch_id')!=identity.get('launch_id') or clip.get('session_sha256')!=session.get('sha256')
                or clip.get('video',{}).get('path')!=expected or not bound(clip.get('video',{}))
                or clip.get('decode_return_code')!=0 or clip.get('decode_stderr')!=''
                or clip.get('original_packet_timestamps_strict') is not True or clip.get('encoded_frame_count',0)<=1
                or not all(type(clip.get(k)) in (int,float) and math.isfinite(clip[k]) and clip[k]>0 for k in ('duration_s','recorded_wall_s'))
                or abs(clip.get('duration_s',float('inf'))-clip.get('recorded_wall_s',0))>=2
                or clip.get('reviewed') is not True or len(clip.get('frames',[]))!=2
                or {v.get('path') for v in clip.get('frames',[])}!={(Path(expected).parent/n).as_posix() for n in ('encoded-contact04.png','encoded-last04.png')}
                or any(not bound(v) for v in clip.get('frames',[]))):
            issues.append('MEDIA_UNBOUND:'+str(role))
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = read(args.manifest)
    active = read(Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/installed/active-release.json')
    release, source = active['release_id'], active['source_manifest_sha256']
    records, issues, hashes = {}, [], {}
    for role, ref in manifest['refs'].items():
        p = (root / ref['path']).resolve()
        if not p.is_relative_to(root) or not p.is_file() or p.is_symlink() or p.is_junction():
            issues.append('UNSAFE_OR_MISSING:' + role)
            continue
        digest = sha256(p.read_bytes()).hexdigest()
        if digest != ref['sha256']:
            issues.append('HASH_MISMATCH:' + role)
            continue
        records[role] = read(p)
        hashes[role] = ref
    if manifest.get('release_id') != release or manifest.get('source_sha256') != source:
        issues.append('NOT_ACTIVE_RELEASE')
    issues += verify(records, release, source)
    issues+=runtime_issues(manifest,root,records)
    issues+=media_issues(manifest,root,records,release,source)
    try:
        pause_path=(root/manifest['refs']['restore']['path']).parent/'events-00014.jsonl'
        raw=pause_path.read_bytes()
        if sha256(raw).hexdigest()!='26600372789497ae6f22dea4f08b75fed35169c63a007c7b6540ff9c99796b5c':
            raise ValueError('Original pause source SHA mismatch')
        event=json.loads(raw.splitlines()[545])
        if (event.get('sequence')!=22669 or event.get('kind')!='control_pause'
                or event.get('operation_id')!='490bf6806c064797b087177aef632f8e'
                or event.get('data',{}).get('pause_id')!='d611f49c90394669901264fe3742bca2:19'
                or event.get('data',{}).get('reason')!='FIELD_DIRECTION_COVERAGE_GAP'):
            raise ValueError('Original pause identity mismatch')
    except (OSError,KeyError,ValueError,IndexError):issues.append('ORIGINAL_PAUSE_SOURCE_UNVERIFIED')
    installed_root=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'
    installed_sources=read(installed_root/Path(active['exe']).parent/'_internal/resources/source-manifest.json')
    def replay_sources(value):
        required={'packages/twinpulse_robot_safety/native_stream.py','packages/twinpulse_robot_safety/field_tests.py','packages/twinpulse_robot_safety/fleet_control.py'}
        return (isinstance(value,dict) and {k.replace('\\','/') for k in value}==required
                and all(installed_sources.get(k.replace('\\','/'))==v for k,v in value.items()))
    if not replay_sources(records.get('replay',{}).get('source_sha256')):issues.append('REPLAY_SOURCE_MISMATCH')
    launch_ids={role:records.get(role,{}).get('versions',{}).get('engine',{}).get('launch_id') for role in ('import','edit','sim','cold')}
    if any(launch_ids[role]!=launch_ids['import'] for role in ('edit','sim')):issues.append('FRESH_LAUNCH_MISMATCH')
    for role,parent in (('marker','import'),('extra','import'),('restore','cold')):
        if records.get(role,{}).get('identity',{}).get('engine',{}).get('launch_id')!=launch_ids[parent]:issues.append('DISPLAY_LAUNCH_MISMATCH:'+role)
    negatives = []
    for role, name in [('marker', 'Physical model body captured'), ('marker', 'Physical sensor panel disconnected'),
                       ('extra', 'Exact Stop all ACK and engine application'), ('restore', 'Cold estimated marker and no physical authority'),
                       ('restore','Exact original pause in read-only timeline')]:
        modified = deepcopy(records)
        if role not in modified:
            negatives.append(dict(role=role, status='NOT_RUN_MISSING_ORIGINAL'))
            continue
        modified[role]['events'] = [e for e in modified[role]['events'] if e.get('name') != name]
        rejected = 'MISSING_STEP:' + role + ':' + name in verify(modified, release, source)
        negatives.append(dict(role=role, step=name, status='PASS_NEGATIVE_REJECTED' if rejected else 'FAIL'))
        if not rejected:
            issues.append('NEGATIVE_NOT_REJECTED:' + name)
    changed=deepcopy(records);changed.setdefault('sim',{})['continuous_display']=[]
    negative_hold='CONTINUOUS_60S_DISPLAY_UNPROVEN' in verify(changed,release,source)
    changed_manifest=deepcopy(manifest)
    if changed_manifest.get('runtime_copies'):
        changed_manifest['runtime_copies']=[changed_manifest['runtime_copies'][0]]*2
    negative_runtime=bool(runtime_issues(changed_manifest,root,records))
    changed_sources=dict(records.get('replay',{}).get('source_sha256',{}));changed_sources['packages/twinpulse_robot_safety/field_tests.py']='0'*64
    negative_source=not replay_sources(changed_sources)
    substituted=dict(records.get('replay',{}).get('source_sha256',{}))
    substituted.pop('packages/twinpulse_robot_safety/field_tests.py',None)
    replacement=next((k for k in installed_sources if k not in substituted and k!='packages/twinpulse_robot_safety/field_tests.py'),None)
    if replacement:substituted[replacement]=installed_sources[replacement]
    negative_keys=not replay_sources(substituted)
    old_media=deepcopy(records);old_media.setdefault('media',{})['release_id']='old-release'
    negative_media='MEDIA_IDENTITY_MISMATCH' in media_issues(manifest,root,old_media,release,source)
    for name,rejected in [('original hold samples missing',negative_hold),('duplicate launch runtime',negative_runtime),('different replay source',negative_source),('wrong third replay file',negative_keys),('old media identity',negative_media)]:
        negatives.append(dict(step=name,status='PASS_NEGATIVE_REJECTED' if rejected else 'FAIL'))
        if not rejected:issues.append('NEGATIVE_NOT_REJECTED:'+name)
    value = dict(schema='robot-visual-impact-acceptance-1.0', release_id=release, source_sha256=source,
                 status='PASS_SCOPED_SOFTWARE_PREPARATION' if not issues else 'FAIL', issues=issues,
                 evidence=hashes, negatives=negatives, originals_unchanged=True,
                 physical_outcomes='NOT_RUN_ROBOT_OFF', broader_F01_F12='NOT_NEWLY_REVALIDATED_IN_FULL',
                 limitation='Current change-impact acceptance only; not physical success, localization, or replacement of the full F01-F12 gate.')
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: value[k] for k in ('status', 'issues', 'negatives')}))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
