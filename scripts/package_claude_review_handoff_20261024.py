# SPDX-License-Identifier: Apache-2.0
"""Explicit local review ZIP; no device/network/API or installed-state mutation."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
import difflib
import json
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/claude-independent-review-20261024-01'
DOCS=ROOT/'docs/handoff/2026-10-24'
LATEST=ROOT/'outputs/robot-auto-demo-20261024-01'
PRIOR=ROOT/'outputs/robot-demo-powered-20261024-02'
REL='20261024T053958Z-9d2b297a8246'
RES=LATEST/'build01/dist/TwinPulse/_internal/resources'
OLD=PRIOR/'build02/dist/TwinPulse/_internal/resources'
TOP='TwinPulse_Claude_Review_2026-10-24'
ARCHIVE=OUT/(TOP+'.zip')
TEXT={'.py','.ts','.tsx','.mjs','.cjs','.js','.ps1','.cmd','.bat','.toml','.json','.yaml','.yml','.md','.txt','.xml','.cpp','.h','.hpp','.spec','.css','.html','.lock','.urdf','.xacro','.cff','.ini','.cfg','.usda','.usd','.usdc'}
SCOPES=('packages/','extensions/','apps/twinpulse-web/','apps/twinpulse-desktop/','scripts/','tests/','config/','packaging/','assets/simulation/')
ROOT_FILES={'AGENTS.md','README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','CITATION.cff','pyproject.toml','.gitignore','.gitattributes','pnpm-workspace.yaml','pnpm-lock.yaml'}
SELECTED_DOCS={
 'docs/planning/TWINPULSE_PROJECT_MEMORY.md','docs/planning/TWINPULSE_BASELINE.md',
 'docs/planning/TWINPULSE_SUBMISSION_FOCUSED_REPAIR_PLAN_2026-10-23.md',
 'docs/analysis/TWINPULSE_NARRATIVE_ROOMPLAN_ALIGNMENT_2026-10-23.md',
 'docs/analysis/TWINPULSE_POWERED_FAILURE_VISUAL_REVIEW_2026-10-24.md',
 'docs/verification/ROBOT_FOCUSED_TEST_ACCEPTANCE_2026-10-18.md',
 'docs/DESKTOP_UI_TESTING.md','docs/WINDOWS_EXE_QUICKSTART.md',
 'docs/LICENSING.md','docs/RELEASE_PROVENANCE.md','docs/progress.md',
 'docs/reference/creator-20261022/README.md',
 'docs/reference/creator-20261022/TWINPULSE_MASTER_NARRATIVE_CODEX_v0_3_2026-10-22.md',
 'docs/reference/creator-20261022/TwinPulse_PhotoFidelity_Demo_Handoff_2026-10-22.md'}
RULES={
 'private_key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
 'github_token':re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
 'api_key_prefix':re.compile(rb'\bsk-[A-Za-z0-9_-]{28,}\b'),
 'aws_access_key':re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
 'jwt_value':re.compile(rb'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b')}

def digest(b):return sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def canonical(v):return json.dumps(v,sort_keys=True).encode()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)

def main():
    if OUT.exists():raise ValueError('NEW_REVIEW_OUTPUT_REQUIRED')
    OUT.mkdir(parents=True)
    records={}; origins={}; findings=[]
    def add(name,raw,origin):
        if name in records or name.startswith('/') or '..' in Path(name).parts:raise ValueError('UNSAFE_OR_DUPLICATE_MEMBER')
        for rule,pattern in RULES.items():
            match=pattern.search(raw)
            if match:findings.append(dict(file=name,rule=rule,line=raw[:match.start()].count(b'\n')+1))
        records[name]=raw;origins[name]=origin
    def copy(p,name=None):
        p=p.resolve(strict=True)
        if not p.is_relative_to(ROOT) or p.is_symlink():raise ValueError('OUTSIDE_OR_LINK')
        add(name or 'source/'+p.relative_to(ROOT).as_posix(),p.read_bytes(),p.relative_to(ROOT).as_posix())
    files=[s.decode('utf-8') for s in git('ls-files','-z','--cached','--others','--exclude-standard').split(b'\0') if s]
    selected=[]
    for rel in sorted(set(files)):
        p=ROOT/rel
        if not p.is_file():continue
        if any(t in p.parts for t in ('node_modules','__pycache__','.git','dist','build','.venv','.build-venv')):continue
        allowed=rel in ROOT_FILES or rel in SELECTED_DOCS or (p.parent==ROOT and p.suffix=='.cmd')
        if rel.startswith(SCOPES) and (p.suffix.lower() in TEXT or p.name in {'CMakeLists.txt','ROBOTIS-LICENSE','LICENSE','NOTICE'}):allowed=True
        if not allowed:continue
        if p.name.startswith('.env') or p.suffix.lower() in {'.pem','.key','.pfx','.p12'}:continue
        copy(p);selected.append(rel)
    for doc in sorted(DOCS.glob('*.md')):copy(doc,doc.name)
    manifest=read(RES/'source-manifest.json')
    manifest_id=digest(canonical(manifest))
    install=read(LATEST/'installation01.json')
    if manifest_id!=install['verification']['source_manifest_sha256']:raise ValueError('INSTALLED_SOURCE_MAP_MISMATCH')
    if install['verification']['build_id']!=REL:raise ValueError('RELEASE_MISMATCH')
    comparison=[]
    for rel in selected:
        if rel not in manifest:continue
        actual=digest(records['source/'+rel])
        comparison.append(dict(path=rel,installed_sha256=manifest[rel],snapshot_sha256=actual,match=actual==manifest[rel]))
    production=lambda p:p.startswith(('packages/','extensions/','apps/')) and '/tests/' not in p and not re.search(r'\.test\.',p)
    code_mismatches=[v for v in comparison if not v['match'] and production(v['path'])]
    if code_mismatches:raise ValueError('REVIEW_PRODUCT_CODE_DIFFERS_FROM_INSTALLED')
    add('source-vs-installed.json',json.dumps(dict(installed_source_id=manifest_id,compared=len(comparison),rows=comparison,
        production_code_mismatches=code_mismatches,not_in_installed_manifest=[r for r in selected if r not in manifest],
        note='Non-code documentation may be newer. Manifest members omitted from ZIP are not silently claimed present.'),indent=2).encode(),'generated SHA comparison')
    copy(RES/'source-manifest.json','evidence/latest/installed-source-manifest.json')
    for name in ('installation01.json','result01.json','scope.json','astra-final-review.txt',
                 'finite-execution-red01.log','finite-execution-green01.log','finite-execution-green02.log',
                 'finite-execution-green03.log','finite-execution-green04.log',
                 'finite-robot-regression01.log','finite-robot-regression02.log','finite-robot-regression03.log'):
        copy(LATEST/name,'evidence/latest/'+name)
    copy(LATEST/'ui-01d/receipt.json','evidence/latest/receipt.json')
    # Small real evidence rows: exact original bytes, never reformatted/backfilled.
    targets={9068,15359,15372,15596,19394,19455,19471}
    request_ids={'74d3c0e9-afd2-452f-afc8-694dd556e6d7','28f7f4f6-7e53-4f16-b04f-3ea429a25548'}
    excerpt=[];index=[]
    receipt=read(LATEST/'ui-01d/receipt.json')
    for segment in receipt['segments']:
        p=LATEST/'ui-01d'/segment['path'];raw=p.read_bytes()
        if digest(raw)!=segment['sha256'] or len(raw)!=segment['bytes']:raise ValueError('ORIGINAL_SEGMENT_CHANGED')
        for line_no,line in enumerate(raw.splitlines(keepends=True),1):
            v=json.loads(line)
            keep=(v.get('schema')=='physical-live-event-2.0' and v.get('sequence') in targets)
            keep|=(v.get('schema')=='physical-live-pc-command-2.0' and v.get('request_id') in request_ids)
            if not keep:continue
            excerpt.append(line)
            index.append(dict(excerpt_line=len(excerpt),original=p.relative_to(ROOT).as_posix(),original_line=line_no,
                original_segment_sha256=segment['sha256'],raw_line_sha256=digest(line),schema=v['schema'],
                sequence=v.get('sequence'),kind=v.get('kind'),request_id=v.get('request_id') or v.get('data',{}).get('request_id')))
    if len(excerpt)!=9:raise ValueError('EXCERPT_SELECTION_INCOMPLETE')
    add('evidence/latest/original-excerpts.jsonl',b''.join(excerpt),'byte-identical selected original rows')
    add('evidence/latest/excerpt-index.json',json.dumps(index,indent=2).encode(),'generated original row index')
    launch='c33072ddfbaa490db3b28ece7f763079'
    for name in ('cleanup-receipt.json','copy-receipt.json','owned-exit-observations.json','engine-result.json'):
        copy(LATEST/'runtime-copiesauto01'/launch/name,'evidence/latest/runtime/'+name)
    historical={
        PRIOR/'result02.json':'evidence/prior/result02.json',
        PRIOR/'attempt01.json':'evidence/prior/attempt01.json',
        ROOT/'outputs/robot-powered-roomplan-20261023-01/powered-retest-status.json':'evidence/prior/powered-retest-status.json',
        ROOT/'outputs/robot-powered-roomplan-20261023-01/registry-repair-status.json':'evidence/prior/registry-repair-status.json',
        ROOT/'outputs/robot-visual-ready-20261024-01/handoff22.json':'evidence/prior/handoff22.json',
        ROOT/'outputs/robot-visual-ready-20261024-01/gate-result22.json':'evidence/prior/gate-result22.json',
        ROOT/'outputs/robot-visual-ready-20261024-01/scoped-gate12b.json':'evidence/prior/scoped-gate12b.json',
        ROOT/'outputs/roomplan-scanner-review-20261023/usd-inspection.json':'evidence/roomplan/usd-inspection.json',
        ROOT/'outputs/roomplan-scanner-review-20261023/library-source-probe.json':'evidence/roomplan/library-source-probe.json'}
    for p,name in historical.items():copy(p,name)
    diffs=[]
    old_manifest=read(OLD/'source-manifest.json')
    for rel in ('packages/twinpulse_robot_safety/fleet_control.py','packages/twinpulse_robot_safety/teleop_contract.py'):
        old=(OLD/rel).read_bytes()
        if digest(old)!=old_manifest[rel]:raise ValueError('PRIOR_SOURCE_HASH_MISMATCH')
        copy(OLD/rel,'evidence/prior-source/'+rel)
        diffs.extend(difflib.unified_diff(old.decode().splitlines(True),records['source/'+rel].decode().splitlines(True),
            fromfile='prior-installed/'+rel,tofile='current-installed/'+rel))
    add('evidence/finite-execution-vs-prior.patch',''.join(diffs).encode(),'generated exact prior/current product comparison')
    add('evidence/working-tree-status.txt',git('status','--short'),'git status --short; no reset/commit/push')
    info=dict(schema='twinpulse-independent-review-package-1.0',created_utc=datetime.now(timezone.utc).isoformat(),
        purpose='Private user-requested Claude review; no external upload, install or hardware action',
        git_head=git('rev-parse','HEAD').decode().strip(),dirty=True,installed_release=REL,installed_source_id=manifest_id,
        package_is_installer=False,source_selection='Current tracked+nonignored untracked code/config/tests; fixed documentation and evidence allowlist',
        source_files=len(selected),source_bytes=sum(len(records['source/'+r]) for r in selected),
        included_installed_manifest_members=sum(r in manifest for r in selected),production_code_mismatches=0,
        omissions=['Personal RoomPlan USD/home photos','Private runtime/settings/credentials/projects','Full raw sensor archives and videos',
            'EXE/DLL/runtime dependencies/Isaac/ROS/venvs/node_modules','Most historical outputs and document attachments'],
        review_limits=['Cannot reconstruct actual RoomPlan or independently rerun complete hardware evidence from excerpts.',
            'Full source/test snapshot is not a turnkey clean installation; omitted binary/private fixtures may prevent some tests.',
            'Earlier scope.json is immutable preparation history; result01.json is its subsequent actual outcome.',
            'Historical relative links can name originals retained only on source PC.'],
        secret_scan=dict(rules=list(RULES),findings=findings,scope='Included bytes only. Pattern scan does not prove absence of every possible secret.'),
        robot_state='User charging and will notify after charge; no hardware authorization from this handoff')
    add('PACKAGE_INFO.json',json.dumps(info,indent=2).encode(),'generated package provenance')
    if findings:
        (OUT/'secret-scan-findings.json').write_text(json.dumps(findings,indent=2),encoding='utf-8')
        raise ValueError('POTENTIAL_SECRET_REVIEW_REQUIRED_NO_ARCHIVE_WRITTEN')
    listing=[dict(path=name,bytes=len(raw),sha256=digest(raw),origin=origins[name]) for name,raw in sorted(records.items())]
    records['MANIFEST.json']=json.dumps(dict(schema='review-zip-file-manifest-1.0',files=listing,
        note='Manifest does not hash itself; outer SHA256SUMS covers the entire ZIP.'),indent=2).encode()
    with zipfile.ZipFile(ARCHIVE,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(records.items()):z.writestr(TOP+'/'+name,raw)
    with zipfile.ZipFile(ARCHIVE) as z:
        if z.testzip() is not None:raise ValueError('ZIP_CRC_FAILURE')
        if len(z.namelist())!=len(records):raise ValueError('ZIP_MEMBER_COUNT')
        for name,raw in records.items():
            if digest(z.read(TOP+'/'+name))!=digest(raw):raise ValueError('ZIP_ROUNDTRIP_MISMATCH')
    zip_sha=digest(ARCHIVE.read_bytes())
    (OUT/'SHA256SUMS.txt').write_text(zip_sha+'  '+ARCHIVE.name+'\n',encoding='utf-8')
    verification=dict(status='VERIFIED_REVIEW_ARCHIVE_NOT_PRODUCT_ACCEPTANCE',zip=ARCHIVE.name,bytes=ARCHIVE.stat().st_size,
        sha256=zip_sha,members=len(records),source_files=len(selected),original_excerpt_rows=len(excerpt),
        uncompressed_bytes=sum(len(v) for v in records.values()),zip_crc='PASS',all_member_sha_roundtrip='PASS',
        high_confidence_secret_findings=0,production_code_mismatches=0,hardware_actions=0,external_uploads=0)
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
    print(json.dumps(verification))

if __name__=='__main__':main()
