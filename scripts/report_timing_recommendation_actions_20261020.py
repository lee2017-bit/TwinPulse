# SPDX-License-Identifier: Apache-2.0
"""One local report; scoped settings evidence is not physical qualification."""
from datetime import datetime,timezone
from html import escape
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/timing-recommendation-actions-20261020'

def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def link(name,label=None):return '<a href="'+escape(name)+'">'+escape(label or name)+'</a>'

if __name__=='__main__':
    install=read('installation02.json');ui=read('ui-final.json');checks=read('frozen-checks/supplementary.json')
    cleanup=[]
    for launch in ui['launches']:
        path=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launches'/launch/'cleanup-receipt.json'
        raw=path.read_bytes();copy='cleanup-'+launch+'.json';(OUT/copy).write_bytes(raw)
        cleanup.append(dict(receipt=json.loads(raw),sha256=hashlib.sha256(raw).hexdigest(),file=copy))
    result=dict(schema='timing-recommendation-actions-result-1.0',at=datetime.now(timezone.utc).isoformat(),
        verdict='PASS_SCOPED_INSTALLED_SETTINGS_NOT_PHYSICAL_QUALIFICATION',installation=install,
        ui_steps=ui['steps'],launches=ui['launches'],cleanup=cleanup,supplementary=checks,
        provider_http=0,provider_usd=0,last_recorded_additional50_remaining_usd=46.8551834,
        original_import_sha256=hashlib.sha256((ROOT/'outputs/robot-timing-settings-20261020/recorded-measurement-import.json').read_bytes()).hexdigest(),
        not_run=['Native/Explorer input (capture failed twice); same actual Test Electron BrowserWindow used instead',
            'First live automatic calibration, robot C++ compile/ROS deployment/readback, physical driving/braking',
            'New full-generation/demo acceptance, Git push/Release/publication'],
        attempts=['Old release launched before installer finished; normally exited with no settings actions; not final acceptance',
            'Build01 function checks passed; comparison table clipped by global760px min-width; preserved ui-build01.json and screenshots',
            'Build02 scoped table layout corrected; independent final installed workflow and cold reopen recorded'])
    (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    rows=''.join('<tr><td>'+escape(s['name'])+'</td><td>'+escape(s['status'])+'</td></tr>' for s in ui['steps'])
    supp=''.join('<li>'+escape(c['name'])+': '+escape(c['status'])+'</li>' for c in checks['checks'])
    attempts=''.join('<li>'+escape(a)+'</li>' for a in result['attempts'])
    limits=''.join('<li>'+escape(a)+'</li>' for a in result['not_run'])
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse · Manual parameter recommendations</title>
<style>body{font:16px/1.55 system-ui;background:#f4f7f9;color:#182d39;max-width:1120px;margin:32px auto;padding:0 22px}section{background:white;padding:22px;margin:20px 0;border:1px solid #ccd7de;border-radius:12px}h1{line-height:1.2}code{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}img{width:100%;height:auto}a{color:#08796b}.pass{color:#08796b;font-weight:bold}</style>
<h1>Manual parameter recommendations</h1><p class="pass">Installed settings workflow verified · not physical qualification</p>
<section><h2>Requested behavior</h2><p>Initial measurement may calculate and register the baseline once. After initialization, measurements only update the saved observations. They do not automatically recalculate recommendations or change registered values.</p><ol><li><b>Recalculate parameters</b> updates only the recommendation from the latest saved observations.</li><li><b>Apply recommended values</b> explicitly copies the displayed recommendation into registered values.</li></ol><p>Registered settings apply on the next explicit connection only. Existing active sessions are unchanged. Manual edits remain available. Unsaved edits must be saved or cancelled before applying a recommendation. Older recommendations are retained and labeled, never automatically refreshed.</p></section>'''
    html+='<section><h2>Frozen installed release</h2><p><code>'+escape(install['verification']['build_id'])+'</code><br>Source SHA <code>'+escape(install['verification']['source_manifest_sha256'])+'</code><br>'+str(install['verification']['files'])+' package files verified.</p><p>'+link('installation02.json')+' · '+link('ui-final.json','Actual UI actions and response receipts')+' · '+link('result.json')+'</p></section>'
    html+='<section><h2>Actual installed App checks</h2><p>Root Start-TwinPulse-Test.cmd was invoked through the execution tool, not Explorer. Actions used the same real Electron BrowserWindow, without request interception, direct mutation calls, state injection or fixed responses. No robot connection/Prepare/sensor/motor or model calls were made.</p><table><tr><th>Check</th><th>Result</th></tr>'+rows+'</table><p>Launch IDs: <code>'+escape(', '.join(ui['launches']))+'</code>. Normal cleanup receipts are linked in result.json.</p></section>'
    html+='<section><h2>Actual screen: recalculation does not apply</h2><img src="final-recalculated.png" alt="Registered input400ms and recommendation350ms with separate English actions"><h2>After explicit Apply</h2><img src="final-applied.png" alt="Registered settings after explicit Apply"><h2>After cold reopen</h2><img src="cold-restored.png" alt="Registered values and recommendation restored without recalculation"></section>'
    html+='<section><h2>Supplementary checks</h2><ul>'+supp+'</ul><p>'+link('frozen-checks/supplementary.json')+'. Fixture/API/component tests are supplementary, not user or physical journeys.</p><h2>Preserved attempts</h2><ul>'+attempts+'</ul><p>'+link('ui-build01.json')+' · '+link('startup-attempt-old-release.json')+' · '+link('native-observation.json')+'</p></section>'
    html+='<section><h2>Not run / remaining</h2><ul>'+limits+'</ul><p>Previous robot nonce/late HTTP/result-display failures are not resolved by this UI change. No physical-readiness or continuous-driving completion claim.</p><p>New provider calls:0 · USD0. Last recorded additionalUSD50 balance46.8551834; priorUSD20 ledger unchanged/separate. No dependency/OS/ROS installation, deletion, Git or upload. Current sources and historical failures/data retained. Build02 source was frozen before subsequent documentation/report-only changes.</p></section></html>'
    (OUT/'report.html').write_text(html,encoding='utf-8');print(str(OUT/'report.html'))
