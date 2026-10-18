# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fetch a completed robot session's fixed files without issuing robot commands."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess


REMOTE_REPORTS = '/home/twinpulse/.local/share/twinpulse/robot/reports'
COMMON = ('report.json', 'session.jsonl', 'base.log', 'off.log', 'before.log',
          'after.log', 'final-off.log')
MODE_FILES = {
    'off': COMMON,
    'lidar': COMMON + ('raw.bin', 'chunks.json'),
    'qualify': COMMON + ('telemetry.json', 'ros-messages.raw', 'ros-messages.raw.footer.json'),
    'qualify_scan': COMMON + ('telemetry.json', 'driver.log', 'ros-messages.raw',
                              'ros-messages.raw.footer.json'),
    'control': COMMON + ('telemetry.json', 'ros-messages.raw', 'ros-messages.raw.footer.json'),
    'mission': COMMON + ('telemetry.json', 'driver.log', 'ros-messages.raw', 'ros-messages.raw.footer.json'),
    'localize': COMMON + ('telemetry.json','driver.log','ros-messages.raw','ros-messages.raw.footer.json','survey-reference.json'),
    **{mode: COMMON + ('telemetry.json', 'driver.log', 'ros-messages.raw', 'ros-messages.raw.footer.json')
       for mode in ('control_scan','scan')},
}


def expected_files(report):
    """Additive optional evidence: old releases keep their original file set."""
    names = MODE_FILES[report['mode']]
    if 'mission_evidence' in report:
        from twinpulse_core.mission_evidence_contract import checked_descriptor, FILE_NAME
        if report['mode'] != 'mission': raise ValueError('MISSION_EVIDENCE_MODE')
        checked_descriptor(report['mission_evidence'])
        names += (FILE_NAME,)
    return names


def _inspect_raw_recording(path):
    """Use the repository's exact-byte inspector; fail closed if it is absent."""
    from .runtime_paths import resource_root
    source = (resource_root() / 'packages' / 'twinpulse_robot_safety'
              / 'raw_ros_record.py')
    if not source.is_file():
        raise ValueError('ROS_RAW_INSPECTOR_UNAVAILABLE')
    spec = importlib.util.spec_from_file_location('twinpulse_export_raw_inspector', source)
    if spec is None or spec.loader is None:
        raise ValueError('ROS_RAW_INSPECTOR_UNAVAILABLE')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.inspect_recording(path)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def export_finished_session(report, destination, *, runner=subprocess.run, scp=None, key=None, known=None, robot_binding=None):
    """Post-cleanup transfer/resume only; never restart a robot operation."""
    from .robot_adapters import legacy_binding, require_adapter
    pinned=legacy_binding() if robot_binding is None else robot_binding
    target = require_adapter(pinned,operation='transfer')
    run_id = report.get('robot_session_id')
    mode = report.get('mode')
    if (not isinstance(run_id, str) or not re.fullmatch(r'manual-[a-f0-9]{32}', run_id)
            or mode not in MODE_FILES):
        raise ValueError('ROBOT_EVIDENCE_ID_OR_MODE_INVALID')
    names = expected_files(report)
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError('EVIDENCE_DESTINATION_SYMLINK')
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('EVIDENCE_DESTINATION_SYMLINK')
    receipt_path = destination/'export.json'
    if receipt_path.is_symlink() or (receipt_path.exists() and not receipt_path.is_file()):
        raise ValueError('EVIDENCE_RECEIPT_PATH_UNSAFE')
    cached = {}
    try:
        previous = json.loads(receipt_path.read_text(encoding='utf-8'))
        saved_report = json.loads((destination/'report.json').read_text(encoding='utf-8'))
        if (previous.get('robot_session_id') == run_id and previous.get('mode') == mode
                and previous.get('robot_binding_sha256',legacy_binding()['sha256'])==pinned['sha256']
                and saved_report.get('robot_session_id') == run_id
                and saved_report.get('boot_id') == report.get('boot_id')
                and saved_report.get('release_id') == report.get('release_id')
                and isinstance(previous.get('files'), dict)):
            cached = previous['files']
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    scp = scp or shutil.which('scp.exe') or shutil.which('scp')
    key = Path(key) if key is not None else Path.home()/'.ssh/twinpulse-burger/id_ed25519_automation'
    known = Path(known) if known is not None else Path.home()/'.ssh/known_hosts'
    if not scp or not key.is_file() or not known.is_file():
        raise ValueError('PC_SCP_PREREQUISITE_MISSING')
    options = ['-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile='+str(known),
               '-o', 'ConnectTimeout=5', '-o', 'ForwardAgent=no',
               '-o', 'ProxyCommand=none', '-o', 'ProxyJump=none', '-P',str(target.port)]
    files = {}
    for name in names:
        cap = 80*1024*1024 if name=='ros-messages.raw' else 64*1024*1024 if name=='session.jsonl' and mode in {'control','control_scan'} else 8*1024*1024
        final = destination/name
        staging = destination/(name+'.part')
        prior = cached.get(name)
        if (isinstance(prior, dict) and prior.get('status') == 'COPIED'
                and final.is_file() and not final.is_symlink() and final.stat().st_size <= cap
                and prior.get('bytes') == final.stat().st_size
                and prior.get('sha256') == _sha256(final)):
            files[name] = dict(prior)
            continue
        if final.is_symlink() or staging.is_symlink() or staging.exists() and not staging.is_file():
            files[name] = {'status':'LOCAL_PATH_UNSAFE_OR_STALE'}
            continue
        discarded_partial = staging.is_file()
        if discarded_partial:
            try:
                staging.unlink()  # Exact generated .part only; never a completed evidence file.
            except OSError:
                files[name] = {'status':'STALE_PARTIAL_UNREMOVABLE'}
                continue
        host='['+target.host+']' if ':' in target.host else target.host
        remote = target.user+'@'+host+':'+REMOTE_REPORTS+'/'+run_id+'/'+name
        try:
            completed = runner([scp, *options, remote, str(staging)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=12, check=False)
            if staging.is_symlink() or staging.exists() and not staging.is_file():
                files[name] = {'status':'LOCAL_PATH_UNSAFE_OR_STALE'}
                continue
            if completed.returncode or not staging.is_file():
                files[name] = {'status':'MISSING_OR_TRANSFER_FAILED','exit_code':completed.returncode}
                continue
            size = staging.stat().st_size
            if size > cap:
                files[name] = {'status':'SIZE_LIMIT_EXCEEDED','bytes':size}
                continue
            staging.replace(final)
            files[name] = {'status':'COPIED','bytes':size,'sha256':_sha256(final),
                           'stale_partial_discarded':discarded_partial}
        except (OSError, subprocess.TimeoutExpired) as exc:
            files[name] = {'status':'TRANSFER_ERROR','error_type':type(exc).__name__}
        finally:
            if staging.is_file() and not staging.is_symlink():
                staging.unlink()
    binding = 'UNVERIFIED'
    binding_reason = None
    try:
        copied = json.loads((destination/'report.json').read_text(encoding='utf-8'))
        if (copied.get('robot_session_id') != run_id or copied.get('mode') != mode
                or copied.get('boot_id') != report.get('boot_id')
                or copied.get('release_id') != report.get('release_id')):
            raise ValueError('ROBOT_REPORT_CONTEXT_MISMATCH')
        if copied.get('mission_evidence') != report.get('mission_evidence'):
            raise ValueError('MISSION_EVIDENCE_REPORT_CHANGED')
        if 'mission_evidence' in report:
            descriptor = report['mission_evidence']; path = destination/descriptor['file']
            if path.stat().st_size != descriptor['bytes'] or _sha256(path) != descriptor['sha256']:
                raise ValueError('MISSION_EVIDENCE_FILE_HASH')
        if 'ros-messages.raw' in MODE_FILES[mode]:
            footer = json.loads((destination/'ros-messages.raw.footer.json').read_text(encoding='utf-8'))
            reported = copied.get('raw_ros')
            if (footer.get('complete') is not True or footer.get('dropped') != 0
                    or footer.get('sha256') != _sha256(destination/'ros-messages.raw')
                    or not isinstance(reported, dict)
                    or reported.get('sha256') != footer.get('sha256')
                    or reported.get('counts') != footer.get('counts')
                    or (isinstance(report.get('raw_ros'), dict)
                        and (report['raw_ros'].get('sha256') != footer.get('sha256')
                             or report['raw_ros'].get('counts') != footer.get('counts')))
                    or reported.get('complete') is not True):
                raise ValueError('ROS_RAW_FOOTER_MISMATCH')
            _inspect_raw_recording(destination/'ros-messages.raw')
        elif mode == 'lidar':
            if copied.get('raw_sha256') != _sha256(destination/'raw.bin'):
                raise ValueError('LIDAR_RAW_HASH_MISMATCH')
        binding = 'VERIFIED'
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        binding = 'REJECTED'
        binding_reason = type(exc).__name__ + ':' + str(exc)[:120]
    receipt = {'schema_version':'robot-session-export-1','robot_session_id':run_id,
               'robot_binding_sha256':pinned['sha256'],
               'mode':mode,'robot_originals_retained':True,'files':files,'binding':binding,
               'binding_reason':binding_reason,
               'raw_message_decode':'NOT_RUN',
               'status':'COMPLETE' if binding=='VERIFIED' and all(
                   item['status']=='COPIED' for item in files.values()) else 'INCOMPLETE'}
    if receipt_path.is_symlink() or (receipt_path.exists() and not receipt_path.is_file()):
        raise ValueError('EVIDENCE_RECEIPT_PATH_UNSAFE')
    receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt


def load_mission_evidence(directory, report, scope, mission_id, request_sha256):
    """Read a fully verified local export only. No remote transfer or motion."""
    from twinpulse_core.mission_evidence_contract import checked_descriptor, checked_mission_evidence, decode_evidence
    descriptor = checked_descriptor(report.get('mission_evidence'))
    directory = Path(directory)
    path = directory/descriptor['file']; receipt_path = directory/'export.json'
    if any(p.is_symlink() for p in (path,receipt_path,*directory.parents,directory)):
        raise ValueError('MISSION_EVIDENCE_PATH_UNSAFE')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    entry = receipt.get('files',{}).get(descriptor['file'],{})
    if (receipt.get('binding')!='VERIFIED' or receipt.get('status')!='COMPLETE'
            or receipt.get('robot_session_id')!=report.get('robot_session_id') or receipt.get('mode')!='mission'
            or entry.get('status')!='COPIED' or entry.get('sha256')!=descriptor['sha256']
            or entry.get('bytes')!=descriptor['bytes']):
        raise ValueError('MISSION_EVIDENCE_EXPORT_NOT_VERIFIED')
    if not path.is_file() or path.stat().st_size!=descriptor['bytes'] or _sha256(path)!=descriptor['sha256']:
        raise ValueError('MISSION_EVIDENCE_FILE_HASH')
    context = {'project_id':scope['project_id'],'session_id':report['robot_session_id'],
        'boot_id':report['boot_id'],'release_id':report['release_id'],
        'source_revision':report['release_id'],'origin':'live_ros'}
    value = checked_mission_evidence(decode_evidence(path.read_bytes()),
        scope,mission_id,request_sha256,context)
    if value['revision']!=descriptor['revision']:raise ValueError('MISSION_EVIDENCE_DESCRIPTOR_REVISION')
    return value
