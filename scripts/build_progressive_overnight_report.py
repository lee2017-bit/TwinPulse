# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local, self-contained acceptance report from explicit raw evidence paths.

No API, robot, automatic PASS promotion or public export. Screenshots are
embedded so the final HTML needs no server or separate image downloads.
"""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'outputs/progressive-twin-overnight-20261012'


def escape(value):return html.escape(str(value))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index',type=Path)
    parser.add_argument('--output',type=Path,default=OUTPUT/'report.html')
    args=parser.parse_args()
    index=json.loads(args.index.read_text(encoding='utf-8'))
    output=args.output.resolve()
    if not output.is_relative_to(OUTPUT) or output.exists() or output.is_symlink():
        raise ValueError('NEW_NAMED_LOCAL_REPORT_ONLY')
    evidence=[];parts=[];screenshots=0
    for entry in index['evidence']:
        path=(OUTPUT/entry['path']).resolve()
        if not path.is_relative_to(OUTPUT) or path.is_symlink():raise ValueError('EVIDENCE_PATH_INVALID')
        value=json.loads(path.read_text(encoding='utf-8'))
        status=value
        for field in entry.get('status_field',['status']):status=status[field]
        if not isinstance(status,str):raise ValueError('EVIDENCE_STATUS_REQUIRED')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        evidence.append(dict(path=entry['path'],sha256=digest,status=status))
        images=[]
        for image in entry.get('images',[]):
            image_path=(OUTPUT/image['path']).resolve()
            if not image_path.is_relative_to(OUTPUT) or image_path.is_symlink():raise ValueError('IMAGE_PATH_INVALID')
            mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'}[image_path.suffix.lower()]
            encoded=base64.b64encode(image_path.read_bytes()).decode('ascii')
            images.append('<figure><img loading="lazy" alt="'+escape(image['caption'])+'" src="data:'+mime+';base64,'+
                encoded+'"><figcaption>'+escape(image['caption'])+'</figcaption></figure>')
            screenshots+=1
        parts.append('<article><h2>'+escape(entry['title'])+' <span class="badge">'+escape(status)+'</span></h2><p>'+
            escape(entry['scope'])+'</p><p class="mono">Evidence: '+escape(entry['path'])+'<br>SHA256: '+digest+
            '</p><ul>'+''.join('<li>'+escape(item)+'</li>' for item in entry.get('observations',[]))+
            '</ul><div class="images">'+''.join(images)+'</div></article>')
    def table(headers,rows):
        return '<div class="table"><table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+\
            '</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(v)+'</td>' for v in row)+'</tr>' for row in rows)+\
            '</tbody></table></div>'
    generated=datetime.now(timezone.utc).isoformat()
    content='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TwinPulse 야간 구현·실제 인수 보고서</title><style>
body{margin:0;background:#f2f5f8;color:#172332;font:16px/1.65 system-ui,sans-serif;overflow-wrap:anywhere}main{max-width:1250px;margin:auto;padding:30px}
h1{font-size:32px;line-height:1.25}h2{font-size:23px}article,section{background:#fff;border:1px solid #d4dee7;border-radius:16px;padding:24px;margin:22px 0}
.badge{font-size:15px;background:#e5eef4;padding:4px 10px;border-radius:6px;display:inline-block;max-width:100%;box-sizing:border-box}.mono{font:12px/1.6 monospace;overflow-wrap:anywhere;color:#586a7c}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;border:1px solid #d7e1e9;text-align:left;vertical-align:top}th{background:#eaf1f6}.table{overflow:auto}
.images{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;min-width:0}figure{margin:0;min-width:0}img{width:100%;height:auto;border:1px solid #d6e0e7;border-radius:9px;box-sizing:border-box}figcaption{font-size:13px;color:#4d6476}
.notice{border-left:5px solid #cc8b28;padding:12px 18px;background:#fff1d8}@media(max-width:650px){main{padding:14px}article,section{padding:16px}.images{grid-template-columns:1fr}}
</style><main><h1>TwinPulse 야간 구현·실제 인수 보고서</h1>'''
    content+='<p>'+escape(index['summary'])+'</p><p class="mono">생성 UTC '+escape(generated)+\
        ' · 승인 원마감 2026-10-12 07:33 KST · 로봇/Cloud/설치/공개 배포 금지</p>'
    content+='<div class="notice">실제 제품 기능, 명시적 고정 응답 시험, 실제 LLM 생성, 사진 충실도와 실물 인수는 서로 다른 결과입니다. '+\
        '로봇 접속·실센서·모터 시험은 이번에 실행하지 않았으며, 과거 실패와 UNKNOWN/held는 삭제하거나 승격하지 않았습니다.</div>'
    content+='<section><h2>아침 사용자 시험 준비 상태</h2>'+table(['사용자 흐름','실제 근거/상태','남은 확인'],
        index['morning_flows'])+'</section>'
    content+='<section><h2>비용과 실행 ID</h2>'+table(['항목','금액 또는 상태'],index['cost_rows'])+\
        '<p>추정 사용액과 미확정 예약은 청구서 확정값이 아닙니다. 추가 총 USD10은 모든 신규 호출·중복·UNKNOWN/held를 포함합니다.</p>'+\
        table(['실행/operation ID','범위','결과'],index['execution_rows'])+'</section>'
    content+=''.join(parts)
    content+='<section><h2>정확한 잔여 작업</h2><ol>'+''.join('<li>'+escape(v)+'</li>' for v in index['remaining'])+\
        '</ol><h2>아침 실행 순서</h2><ol>'+''.join('<li>'+escape(v)+'</li>' for v in index['morning_steps'])+'</ol></section>'
    content+='<section><h2>검증 경계</h2><ul>'+''.join('<li>'+escape(v)+'</li>' for v in index['limitations'])+\
        '</ul><p class="mono">Report index SHA256: '+hashlib.sha256(args.index.read_bytes()).hexdigest()+'</p></section></main></html>'
    with output.open('x',encoding='utf-8') as stream:stream.write(content)
    metrics=dict(schema_version='progressive-overnight-local-report-1.0',generated_at=generated,
        index_sha256=hashlib.sha256(args.index.read_bytes()).hexdigest(),
        report_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),embedded_screenshots=screenshots,
        evidence=evidence,physical_robot_connections=0,public_release=False)
    with output.with_suffix('.audit.json').open('x',encoding='utf-8') as stream:json.dump(metrics,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status='LOCAL_REPORT_CREATED_NOT_NEW_ACCEPTANCE',embedded_screenshots=screenshots,
        report=str(output),sha256=metrics['report_sha256'])))


if __name__=='__main__':main()
