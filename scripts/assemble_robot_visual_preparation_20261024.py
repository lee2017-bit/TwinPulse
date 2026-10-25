# SPDX-License-Identifier: Apache-2.0
"""Hash-bind existing current-install records. Does not run the App or repair results."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--tag',required=True)
    p.add_argument('--installation',required=True);p.add_argument('--supplementary',required=True)
    p.add_argument('--cold-tag',help='Explicit separately rerun whole cold/restore journey; preserve original failed cold evidence.')
    p.add_argument('--media');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();tag=a.tag
    if len(tag)!=2 or not tag.isascii() or not tag.isdecimal():raise ValueError('Two-digit tag required')
    cold_tag=a.cold_tag or tag
    if len(cold_tag)!=2 or not cold_tag.isascii() or not cold_tag.isdecimal():raise ValueError('Two-digit cold tag required')
    active=json.loads((Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json').read_text(encoding='utf-8-sig'))
    def read(name):return json.loads((root/name).read_text(encoding='utf-8-sig'))
    def ref(name):
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('Missing or unsafe reference: '+name)
        return dict(path=path.relative_to(root).as_posix(),sha256=sha256(path.read_bytes()).hexdigest())
    paths={role:f'roomplan-{role}{tag}/result.json' for role in ('import','edit','sim','cold')}
    paths.update({role:f'ui-{role}{tag}/session.json' for role in ('marker','extra','restore')})
    paths['cold']=f'roomplan-cold{cold_tag}/result.json'
    paths['restore']=f'ui-restore{cold_tag}/session.json'
    paths.update(installation=a.installation,supplementary=a.supplementary,replay='observation-replay01.json')
    if a.media:paths['media']=a.media
    copies=[f"runtime-copies{trial}/{read('start-'+role+'-'+trial+'.json')['launch_id']}" for role,trial in (('fresh',tag),('cold',cold_tag))]
    value=dict(release_id=active['release_id'],source_sha256=active['source_manifest_sha256'],refs={role:ref(name) for role,name in paths.items()},runtime_copies=copies,
               journey_tags=dict(fresh=tag,cold=cold_tag),classification='Separate whole fresh and cold journeys; original failed records are not rewritten or joined to a continuation.')
    with a.output.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(release_id=value['release_id'],references=len(paths),output=str(a.output))))


if __name__=='__main__':main()
