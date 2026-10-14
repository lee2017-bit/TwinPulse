# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Recheck a copied robot evidence directory with the robot powered off."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'packages/twinpulse_core/src'))
sys.path.insert(0, str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from raw_ros_record import TOPICS, inspect_recording, replay_recording
from ros_message_diagnostics import review_replayed

# Keep these fixed contracts in step with the two exporters. A receipt is not
# authority to omit a file that the selected operation was required to save.
COMMON = ('report.json', 'session.jsonl', 'base.log', 'off.log', 'before.log',
          'after.log', 'final-off.log')
SESSION_FILES = {
    'off': COMMON,
    'lidar': COMMON + ('raw.bin', 'chunks.json'),
    **{mode: COMMON + ('telemetry.json', 'ros-messages.raw',
                        'ros-messages.raw.footer.json')
       for mode in ('qualify', 'control')},
    **{mode: COMMON + ('telemetry.json','driver.log','ros-messages.raw','ros-messages.raw.footer.json')
       for mode in ('qualify_scan','control_scan','scan','mission')},
}
STATIONARY_FILES = ('report.json', 'operation.log', 'telemetry.json',
                    'base.log', 'observer.log', 'before-board.log', 'after-board.log',
                    'ros-messages.raw', 'ros-messages.raw.footer.json')


def _json_file(path, limit=16*1024*1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('EVIDENCE_JSON_PATH_OR_SIZE_INVALID')
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('EVIDENCE_JSON_DUPLICATE_KEY')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_keys)


def _binding_errors(directory, receipt, verified, raw):
    errors = []
    schema = receipt['schema_version']
    if receipt.get('robot_originals_retained') is not True:
        errors.append('ORIGINAL_RETENTION_UNCONFIRMED')
    try:
        if verified.get('report.json') != 'VERIFIED':
            raise ValueError('REPORT_NOT_VERIFIED')
        report = _json_file(directory/'report.json')
        if not isinstance(report, dict):
            raise ValueError('REPORT_INVALID')
        if schema == 'robot-session-export-1':
            if (receipt.get('binding') != 'VERIFIED'
                    or report.get('robot_session_id') != receipt.get('robot_session_id')
                    or report.get('mode') != receipt.get('mode')):
                raise ValueError('SESSION_REPORT_BINDING_MISMATCH')
            if receipt['mode'] == 'lidar':
                if verified.get('raw.bin') != 'VERIFIED' or report.get('raw_sha256') != digest(directory/'raw.bin'):
                    raise ValueError('LIDAR_RAW_BINDING_MISMATCH')
            elif receipt['mode'] in {'qualify', 'qualify_scan', 'control', 'control_scan', 'scan', 'mission'}:
                if verified.get('ros-messages.raw.footer.json') != 'VERIFIED' or raw['status'] != 'VERIFIED':
                    raise ValueError('SESSION_RAW_NOT_VERIFIED')
                footer = _json_file(directory/'ros-messages.raw.footer.json', 16*1024)
                recorded = report.get('raw_ros')
                if (not isinstance(recorded, dict) or recorded.get('sha256') != footer.get('sha256')
                        or recorded.get('counts') != footer.get('counts')
                        or recorded.get('complete') is not True):
                    raise ValueError('SESSION_REPORT_RAW_BINDING_MISMATCH')
        else:
            if (receipt.get('report_binding', {}).get('status') != 'VERIFIED_SAME_RUN'
                    or receipt.get('raw_replay', {}).get('status') != 'VERIFIED_OFFLINE'
                    or report.get('run_id') != receipt.get('run_id')):
                raise ValueError('STATIONARY_REPORT_BINDING_MISMATCH')
            if verified.get('telemetry.json') != 'VERIFIED' or raw['status'] != 'VERIFIED':
                raise ValueError('STATIONARY_RAW_NOT_VERIFIED')
            telemetry = _json_file(directory/'telemetry.json')
            footer = _json_file(directory/'ros-messages.raw.footer.json', 16*1024)
            recorded = telemetry.get('raw_ros')
            if (not isinstance(recorded, dict) or recorded.get('sha256') != footer.get('sha256')
                    or recorded.get('counts') != footer.get('counts')
                    or recorded.get('complete') is not True):
                raise ValueError('STATIONARY_TELEMETRY_RAW_BINDING_MISMATCH')
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(str(exc)[:120])
    return errors


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def ros_decoder():
    """Return a ROS 2 decoder only when compatible local packages already exist."""
    try:
        from rclpy.serialization import deserialize_message
    except ImportError:
        return None
    def decode(payload, type_name):
        if type_name not in TOPICS.values():
            raise ValueError('ROS_TYPE_NOT_ALLOWLISTED')
        package, category, message = type_name.split('/')
        if category != 'msg':
            raise ValueError('ROS_TYPE_NOT_MESSAGE')
        cls = getattr(importlib.import_module(package + '.msg'), message)
        return deserialize_message(payload, cls)
    return decode


def inspect(directory, *, decoder=None, require_decode=False):
    directory = Path(directory).resolve(strict=True)
    receipt = _json_file(directory/'export.json', 64*1024)
    if not isinstance(receipt, dict):
        raise ValueError('EXPORT_RECEIPT_INVALID')
    if receipt.get('schema_version') not in {'robot-evidence-export-1','robot-session-export-1'}:
        raise ValueError('EXPORT_SCHEMA_INVALID')
    files = receipt.get('files')
    if not isinstance(files, dict):
        raise ValueError('EXPORT_FILES_INVALID')
    if any(not isinstance(name, str) or '/' in name or '\\' in name or name in {'.', '..'}
           for name in files):
        raise ValueError('EXPORT_FILENAME_INVALID')
    if receipt['schema_version'] == 'robot-session-export-1':
        mode = receipt.get('mode')
        run_id = receipt.get('robot_session_id')
        if not isinstance(mode, str) or mode not in SESSION_FILES or not isinstance(run_id, str) or not re.fullmatch(r'manual-[a-f0-9]{32}', run_id):
            raise ValueError('EXPORT_SESSION_ID_OR_MODE_INVALID')
        required = set(SESSION_FILES[mode])
        report = _json_file(directory/'report.json')
        if 'mission_evidence' in report:
            from twinpulse_core.mission_evidence_contract import checked_descriptor
            if mode!='mission':raise ValueError('MISSION_EVIDENCE_MODE')
            required.add(checked_descriptor(report['mission_evidence'])['file'])
    else:
        run_id = receipt.get('run_id')
        if not isinstance(run_id, str) or not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}', run_id):
            raise ValueError('EXPORT_STATIONARY_ID_INVALID')
        required = set(STATIONARY_FILES)
    contract_errors = []
    if set(files) != required:
        contract_errors.append('EXPORT_FILE_SET_MISMATCH')
    verified = {}
    ordinary_limit = 8*1024*1024 if receipt['schema_version'] == 'robot-session-export-1' else 16*1024*1024
    for name in sorted(required | set(files)):
        entry = files.get(name)
        if name not in required:
            verified[name] = 'UNEXPECTED_FILE'
            continue
        if not isinstance(entry, dict):
            verified[name] = 'MISSING_OR_INCOMPLETE'
            continue
        path = directory/name
        if entry.get('status') != 'COPIED':
            verified[name] = 'MISSING_OR_INCOMPLETE'
        elif (path.is_symlink() or not path.is_file()
                or type(entry.get('bytes')) is not int or entry['bytes'] < 0
                or entry['bytes'] > (80*1024*1024 if name=='ros-messages.raw' else
                    64*1024*1024 if name=='session.jsonl' and receipt.get('mode') in {'control','control_scan'} else ordinary_limit)
                or path.stat().st_size != entry['bytes']
                or digest(path) != entry.get('sha256')):
            verified[name] = 'HASH_OR_SIZE_MISMATCH'
        else:
            verified[name] = 'VERIFIED'
    raw = {'status':'NOT_CAPTURED', 'message_decode':'NOT_RUN'}
    if 'ros-messages.raw' in required and verified.get('ros-messages.raw') == 'VERIFIED' and verified.get('ros-messages.raw.footer.json') == 'VERIFIED':
        try:
            frames = inspect_recording(directory/'ros-messages.raw')
            raw = {'status':'VERIFIED','messages':len(frames),
                   'topics':sorted({meta['topic'] for meta,_ in frames}),
                   'message_decode':'NOT_RUN'}
            if decoder is not None:
                replayed = replay_recording(directory/'ros-messages.raw', decoder)
                raw['message_decode'] = 'CUSTOM_DECODER_COMPLETE'
                raw['decoded_messages'] = len(replayed)
                raw['message_diagnostics'] = review_replayed(replayed)
            elif require_decode:
                raw['message_decode'] = 'ROS_DECODER_UNAVAILABLE'
        except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:
            raw = {'status':'REJECTED','message_decode':'REJECTED',
                   'reason':type(exc).__name__+':'+str(exc)[:120]}
    elif 'ros-messages.raw' in required:
        raw = {'status':'REJECTED', 'message_decode':'NOT_RUN', 'reason':'RAW_FILES_NOT_VERIFIED'}
    contract_errors.extend(_binding_errors(directory, receipt, verified, raw))
    mission_evidence = None
    if receipt['schema_version']=='robot-session-export-1' and receipt.get('mode')=='mission' and 'mission_evidence' in report:
        descriptor=report['mission_evidence']; name=descriptor['file']
        entry=files.get(name,{})
        if (verified.get(name)!='VERIFIED' or entry.get('bytes')!=descriptor['bytes']
                or entry.get('sha256')!=descriptor['sha256']):
            contract_errors.append('MISSION_EVIDENCE_FILE_HASH')
        else:
            try:
                from twinpulse_core.mission_evidence_contract import decode_evidence,replay_mission_evidence
                value=decode_evidence((directory/name).read_bytes())
                if value['revision']!=descriptor['revision']:
                    raise ValueError('MISSION_EVIDENCE_DESCRIPTOR_REVISION')
                context={'project_id':value['scope']['project_id'],'session_id':report['robot_session_id'],
                    'boot_id':report['boot_id'],'release_id':report['release_id'],
                    'source_revision':report['release_id'],'origin':'live_ros'}
                replay=replay_mission_evidence(value,value['scope'],report['mission_id'],
                    report['mission_request_sha256'],context)
                mission_evidence={**replay,'keyframe_count':len(value['survey_map']['keyframes']),
                    'tracking_endpoint_count':len(value['survey_map']['tracking_endpoints']),
                    'endpoint_cell_count':len(value['survey_map']['endpoint_cells']),
                    'revision':value['revision']}
                if replay['status']=='MISMATCH':contract_errors.append('MISSION_EVIDENCE_FIT_REPLAY_MISMATCH')
            except (OSError,ValueError,KeyError,TypeError) as exc:
                code=str(exc)
                if not re.fullmatch('[A-Z0-9_]{1,120}',code):code='MISSION_EVIDENCE_REPLAY_FAILED'
                contract_errors.append(code)
    return {'schema_version':'robot-evidence-offline-review-1',
            'status':'COMPLETE' if (receipt.get('status')=='COMPLETE' and not contract_errors
                                   and all(v=='VERIFIED' for v in verified.values())
                                   and raw['status'] in {'VERIFIED','NOT_CAPTURED'}
                                   and (not require_decode or raw.get('message_decode')=='CUSTOM_DECODER_COMPLETE'))
                    else 'INCOMPLETE',
            'export_status':receipt.get('status'),'files':verified,'raw_ros':raw,
            'contract_errors':contract_errors,
            'mission_evidence':mission_evidence,
            'physical_validation':'NOT_RUN_BY_THIS_TOOL'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence_dir', type=Path)
    parser.add_argument('--decode-ros', action='store_true',
                        help='Require installed ROS 2 rclpy and message packages; never installs them')
    args = parser.parse_args()
    decoder = ros_decoder() if args.decode_ros else None
    try:
        result = inspect(args.evidence_dir, decoder=decoder, require_decode=args.decode_ros)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({'schema_version':'robot-evidence-offline-review-1',
                          'status':'INCOMPLETE', 'error_type':type(exc).__name__,
                          'reason':str(exc)[:160], 'physical_validation':'NOT_RUN_BY_THIS_TOOL'}, indent=2))
        return 2
    if args.decode_ros and decoder is not None and result['raw_ros'].get('message_decode')=='CUSTOM_DECODER_COMPLETE':
        result['raw_ros']['message_decode']='ROS_RCLPY_DECODED'
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='COMPLETE' else (3 if args.decode_ros and decoder is None else 2)


if __name__=='__main__':
    raise SystemExit(main())
