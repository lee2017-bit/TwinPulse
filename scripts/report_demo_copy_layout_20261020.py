# SPDX-License-Identifier: Apache-2.0
"""Local before/after video-led UI review, not full product/hardware acceptance."""
from datetime import datetime,timezone
from html import escape
from pathlib import Path
import hashlib,json,os,re
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/demo-copy-layout-20261020'
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def link(path,label=None):return '<a href="'+escape(path)+'">'+escape(label or path)+'</a>'
if __name__=='__main__':
    ui=read('actual-ui05/result.json');install=read('installation05.json');audit=read('video-audit.json')
    artifacts=[]
    for folder in (OUT,OUT/'actual-ui02',OUT/'actual-ui03',OUT/'actual-ui04',OUT/'actual-ui05'):
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix in {'.json','.mp4','.png','.log'} and path.name not in {'report-qa.png','manifest.json'} and not (folder==OUT and path.name=='result.json'):
                artifacts.append(dict(path=path.relative_to(OUT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    cleanup=[]
    for launch in ['70aa9d7705b34df086d9ec2d5d89e7e6',read('actual-ui03/result.json')['identity']['engine']['launch_id'],read('actual-ui04/result.json')['identity']['engine']['launch_id'],ui['identity']['engine']['launch_id']]:
        path=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launches'/launch/'cleanup-receipt.json'
        if path.exists():
            raw=path.read_bytes();name='cleanup-'+launch+'.json';(OUT/name).write_bytes(raw)
            cleanup.append(dict(file=name,sha256=hashlib.sha256(raw).hexdigest(),receipt=json.loads(raw)))
    tests=(OUT/'ui-final03.log').read_text(encoding='utf-8',errors='replace')
    result=dict(schema='demo-copy-layout-result-1.0',at=datetime.now(timezone.utc).isoformat(),
        verdict=ui['status'],installation=install,video_audit=audit,steps=ui['steps'],sizes=ui['sizes'],
        hold=ui.get('hold'),operation_id=ui.get('operation_id'),cleanup=cleanup,
        supplementary=dict(ui=re.findall(r'Test Files[^\r\n]*|Tests  [^\r\n]*',tests),types_log='types-final.log',settings_api_log='settings-api.log'),
        artifacts=artifacts,provider_http=0,provider_usd=0,last_recorded_additional50_remaining_usd=46.8551834,
        not_run=['Native screen/input and Explorer launch; same explicit Test BrowserWindow used after capture timeouts',
          'OS DPI / another PC / every App screen and every transient video frame',
          'Fresh generation/photo fidelity or physical robot connection/driving; restored original demo used only for UI regression',
          'Robot C++/ROS deployment and prior nonce/lateHTTP problems; UI changes do not resolve hardware-readiness items',
          'New Git/GitHub/Release upload; original videos and failed attempts remain unchanged'])
    (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    rows=''.join('<tr><td>'+escape(x['name'])+'</td><td>'+escape(x['status'])+'</td></tr>' for x in ui['steps'])
    findings=''.join('<li><b>'+escape(x['id'])+'</b> '+escape(x['issue'])+' ('+str(x['time_s'])+'s)</li>' for x in audit['findings'])
    sizes=''.join('<tr><td>'+str(x['width'])+' × '+str(x['height'])+'</td><td>'+escape(x['status'])+'</td><td>'+str(x.get('intersection_px2'))+'</td></tr>' for x in ui['sizes'])
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse · Video-led UI copy review</title><style>body{font:16px/1.55 system-ui;max-width:1160px;margin:30px auto;padding:0 20px;background:#f4f7f9;color:#18303c}section{background:white;border:1px solid #d2dee3;border-radius:12px;padding:22px;margin:22px 0}h1{line-height:1.2}img,video{width:100%;height:auto}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:left}table{border-collapse:collapse;width:100%}code{overflow-wrap:anywhere}a{color:#087366}</style><h1>Video-led UI copy and layout review</h1>'''
    html+='<p><b>'+escape(ui['status'])+'</b> · scoped installed UI acceptance, not full product or robot readiness.</p><section><h2>Inspection before product edits</h2><p>Reviewed both the latest successful local full demo and the previously published GitHub demo: five-second samples across their full durations plus full-resolution105/155/230s and150s keyframes. This is not every transient video frame. Original bytes were not changed.</p><ul>'+findings+'</ul><p>'+link('video-audit.json','Video paths, SHA and inspection scope')+'</p><img src="latest-230.png" alt="Before: notice overlaps command progress"><p>Before: latest local demo at230s.</p></section>'
    html+='<section><h2>Changes</h2><ul><li>Short English actions: Exit, Readiness, Twin controls, LiDAR on/off, Send, Save, Cancel, Recalculate, Apply recommended, Preview route, Run and Reset. Complete accessible names/help retained.</li><li>Shutdown/test explanation, calibration/validation notes, sensor correction and SIM command guide are expandable or contextual. Historical chat text remains unchanged.</li><li>Critical Stop, real failure reasons, sensor state, current command state and original-clock safety behavior remain. No timeout, speed, collision or robot-permission changes.</li><li>Fixed compact grid rows and removed the inherited18px/8px command-label margins that made the form exceed its row. Status and command result must have zero geometric overlap.</li></ul><p>Final installed <code>'+escape(install['verification']['build_id'])+'</code><br>Source <code>'+escape(install['verification']['source_manifest_sha256'])+'</code> · '+str(install['verification']['files'])+' files verified.</p></section>'
    html+='<section><h2>Actual final App checks</h2><p>Normal root Test Start via execution tool → same installed Electron BrowserWindow → UI reopen of original demo project → View current Twin → SIM-only Connect/Prepare → LiDAR → commands/Stop. No direct product mutation API, fake response, request interception or internal state injection.</p><table><tr><th>Check</th><th>Result</th></tr>'+rows+'</table><table><tr><th>CSS viewport</th><th>Result</th><th>Notice/result overlap px²</th></tr>'+sizes+'</table><p>Operation <code>'+escape(str(ui.get('operation_id')))+'</code>; launch <code>'+escape(ui['identity']['engine']['launch_id'])+'</code>.</p><p>'+link('actual-ui03/result.json','Original measurements and actual steps')+' · '+link('actual-ui03/fleet-http-receipts.json','Actual command ACK/epoch receipts')+'</p><img src="actual-ui03/final-controls.png" alt="After: compact live controls and separate command/status rows"></section>'
    html+='<section><h2>Recording</h2><p>Scoped UI regression in the restored original demo, not fresh generation or a replacement full-journey marketing video. Renderer recording only.</p><video controls preload="none" src="actual-ui03/app-screen.mp4"></video><p>'+link('actual-ui03/frame-times.json','Original capture times')+'</p></section>'
    html+='<section><h2>Preserved attempts</h2><ul><li>Build01 not installed: superseded during stylesheet review.</li><li>Build02: same-demo measured overlap4309.4px²; global label margins exceeded the90px row. Original failed recording/results retained; no movement in this attempt.</li><li>Prepare returned READY; the first harness incorrectly waited for PAUSED. Recorded as a harness assumption, not a product fault.</li><li>Native capture timed out; a retry binding error and fresh-window capture failure are disclosed. Explicit same-BrowserWindow path used.</li><li>Old test text lookups were updated to complete accessible names for the shortened visible labels. Initial failing tests were not presented as PASS.</li></ul><p>'+link('actual-ui02/result.json')+' · '+link('actual-ui02/app-screen.mp4','Original layout reproduction recording')+' · '+link('ui-attempt02.log')+'</p><h2>Limits and cost</h2><ul>'+''.join('<li>'+escape(x)+'</li>' for x in result['not_run'])+'</ul><p>Provider calls0 / USD0. Last recorded additionalUSD50 balance46.8551834; previousUSD20 ledger separate/unchanged. No new dependency/OS/ROS changes, deletion or publication.</p><p>'+link('result.json','One aggregate result with SHA-bound artifact list')+'</p></section></html>'
    html=html.replace('actual-ui03/','actual-ui05/')
    html=html.replace('<section><h2>Recording</h2>','<section><h2>Short timing actions</h2><img src="actual-ui05/timing-short-labels.png" alt="Short English Save Cancel Recalculate and Apply recommended actions"><p>Complete accessible names remain. Long formula/provenance text is expandable; saved timing values and next-connection application semantics are unchanged.</p></section><section><h2>Recording</h2>')
    html=html.replace('<h2>Limits and cost</h2>','<p>Build03 passed canvas/control checks but failed additional minimum-size LiDAR toolbar inspection. Its inherited label margin made the toolbar59px tall and clipped it. This was not accepted; '+link('actual-ui03/result.json','Original minimum-size failure')+' is preserved. Build04 removed label margins but the select still inherited9px top margin, clipping its border1.15px at800×600 although text was visible. '+link('actual-ui04/result.json','Original selector-edge failure')+' is preserved. Build05 removes the select margin and reruns the independent final checks.</p><h2>Limits and cost</h2>')
    (OUT/'report.html').write_text(html,encoding='utf-8');print(str(OUT/'report.html'))
