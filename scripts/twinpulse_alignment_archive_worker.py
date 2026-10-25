# SPDX-License-Identifier: Apache-2.0
"""Fixed read-only extraction of three preselected original scan frames."""
import argparse,json,os,re,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
if not getattr(sys,'frozen',False):
    for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'packages'/name/'src'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state-root',type=Path,required=True)
    parser.add_argument('--operation',required=True);parser.add_argument('--project',required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--start-sequence',type=int,default=0)
    args=parser.parse_args()
    if not re.fullmatch('[a-f0-9]{32}',args.operation) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',args.project) or args.start_sequence<0:raise ValueError('ALIGNMENT_ARCHIVE_IDENTITY')
    directory=args.state_root/'physical-live'/args.operation
    if any(p.is_symlink() for p in (directory,*directory.parents)):raise ValueError('ALIGNMENT_ARCHIVE_PATH')
    from twinpulse_app.physical_motion_analysis import read_archive
    archive=read_archive(directory,args.operation,args.project,time.monotonic()+60)
    if archive['receipt'].get('complete') is not True:raise ValueError('ALIGNMENT_ARCHIVE_INCOMPLETE')
    config=archive['sources'].get('field-config.json',{}).get('config')
    if not isinstance(config,dict) or not {'sensor_x_m','sensor_y_m','sensor_yaw_rad','angle_sign'}<=set(config):raise ValueError('ALIGNMENT_ARCHIVE_TF_UNVERIFIED')
    selected=[s for s in archive['scans'] if s['frame_sequence']>=args.start_sequence][:3]
    if len(selected)!=3:raise ValueError('ALIGNMENT_ARCHIVE_THREE_FRAMES_REQUIRED')
    result=dict(schema='alignment-archive-extraction-1.0',operation_id=args.operation,project_id=args.project,
        recorded_twin_context=archive['first'].get('source_twin_context'),receipt_sha256=archive['receipt_sha256'],
        segments=archive['receipt']['segments'],receipt_complete=True,extrinsic=[config['sensor_x_m'],config['sensor_y_m'],config['sensor_yaw_rad']],
        angle_sign=config['angle_sign'],tf_basis='HASH_VERIFIED_RECORDED_FIELD_CONFIG_NOT_AS_BUILT',
        frames=[dict(identity=[s['stream_id'],s['frame_sequence'],s['raw_sha256']],points=s['points_full'],
            start=s['start'],end=s['end']) for s in selected],
        selection='FIRST_THREE_VALID_COMPLETE_RINGS_AT_OR_AFTER_EXPLICIT_SEQUENCE',start_sequence=args.start_sequence,
        physical_authority=False,world_registration_verified=False)
    raw=json.dumps(result,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>2*1024*1024:raise ValueError('ALIGNMENT_ARCHIVE_RESULT_BOUND')
    with args.output.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
if __name__=='__main__':main()
