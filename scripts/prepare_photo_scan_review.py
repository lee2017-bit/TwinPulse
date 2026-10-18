# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline, review-only photo/actual native scan association. No transport/control.

Fit observed 2-D line segments, not room walls or free space. A monocular photo
does not supply surveyed dimensions or a verified photo-to-LiDAR transform.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
from twinpulse_core.revisions import InputRevision
from twinpulse_core.photo_track import PhotoTrackManifest

CONFIRMED_PHOTO_SHA256 = 'a183bf7e30cb6d1ddc712aa25f484f8763bca6ccbc75d4c8977aa99cbb6f6ea0'
CONFIRMED_RAW_SHA256 = '4b6d732b717e2cc6242366e3a6040d5212b59b3271be76d525466b45a6e39e07'


def require_confirmed_pair(photo_hash, raw_hash):
    # The operator's same-position declaration applies to this pair only.
    if photo_hash != CONFIRMED_PHOTO_SHA256 or raw_hash != CONFIRMED_RAW_SHA256:
        raise ValueError('This review recipe is scoped to the user-confirmed photo/scan pair')

PHOTO_OBSERVATIONS = [
    {'id': 'bed', 'label': 'Bed / bedding', 'box_normalized': [.525, .37, 1.0, .89], 'location': 'photo right; runs toward back'},
    {'id': 'wardrobe', 'label': 'Open wardrobe', 'box_normalized': [.498, .103, .815, .52], 'location': 'photo back-right'},
    {'id': 'desk', 'label': 'Desk', 'box_normalized': [.30, .35, .56, .52], 'location': 'photo back-left under window'},
    {'id': 'chair', 'label': 'Chair', 'box_normalized': [.28, .42, .49, .61], 'location': 'left of aisle, in front of desk'},
    {'id': 'fan', 'label': 'Fan / boxes', 'box_normalized': [.11, .499, .32, .77], 'location': 'photo left near robot'},
    {'id': 'bag', 'label': 'Black bag', 'box_normalized': [.739, .632, .977, .875], 'location': 'photo near-right by bed'},
    {'id': 'left_luggage', 'label': 'Clothing / luggage', 'box_normalized': [.04, .746, .458, .994], 'location': 'photo near-left'},
    {'id': 'robot', 'label': 'TurtleBot', 'box_normalized': [.492, .632, .578, .711], 'location': 'aisle; scan position confirmed by user'},
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform_point(x, y, rotation, mirror):
    angle = math.radians(rotation)
    y = -y if mirror else y
    return x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle)


def orientation_candidates(lines):
    if not lines:
        return []
    alpha = lines[0]['direction_deg_mod180']
    return [{'id': ('mirror' if mirror else 'rotate') + str(k),
             'rotation_deg': ((alpha if mirror else -alpha) + 90*k) % 360,
             'mirror_native_y': mirror, 'status': 'UNVERIFIED_DISPLAY_HYPOTHESIS'}
            for mirror in (False, True) for k in range(4)]


def fit_segments(points, tolerance=.035, max_gap=.18):
    """Deterministic line hypotheses, continuity checked; no semantic labels."""
    if not 2 <= len(points) <= 4096:
        raise ValueError('Point count outside review bounds')
    xy = [(p['x_m'], p['y_m']) for p in points]
    if any(not all(math.isfinite(v) and abs(v) <= 100 for v in p) for p in xy):
        raise ValueError('Invalid points')
    remaining = set(range(len(xy)))
    rng = random.Random(20260927)
    lines = []
    for _ in range(8):
        if len(remaining) < 15:
            break
        best = []
        for _ in range(1000):
            a, b = rng.sample(sorted(remaining), 2)
            dx, dy = xy[b][0]-xy[a][0], xy[b][1]-xy[a][1]
            length = math.hypot(dx, dy)
            if length < .5:
                continue
            ux, uy = dx/length, dy/length
            inliers = [i for i in remaining if abs((xy[i][0]-xy[a][0])*uy-(xy[i][1]-xy[a][1])*ux) <= tolerance]
            inliers.sort(key=lambda i: xy[i][0]*ux+xy[i][1]*uy)
            groups = [[]]
            for i in inliers:
                if groups[-1] and math.dist(xy[i], xy[groups[-1][-1]]) > max_gap:
                    groups.append([])
                groups[-1].append(i)
            for group in groups:
                if len(group) > len(best) and math.dist(xy[group[0]], xy[group[-1]]) >= .5:
                    best = group
        if len(best) < 15:
            break
        cx = sum(xy[i][0] for i in best)/len(best)
        cy = sum(xy[i][1] for i in best)/len(best)
        xx = sum((xy[i][0]-cx)**2 for i in best)
        yy = sum((xy[i][1]-cy)**2 for i in best)
        cross = sum((xy[i][0]-cx)*(xy[i][1]-cy) for i in best)
        angle = .5*math.atan2(2*cross, xx-yy)
        ux, uy = math.cos(angle), math.sin(angle)
        ts = [(xy[i][0]-cx)*ux+(xy[i][1]-cy)*uy for i in best]
        distances = [(xy[i][0]-cx)*uy-(xy[i][1]-cy)*ux for i in best]
        lines.append({'id': chr(65+len(lines)), 'support': len(best),
                      'direction_deg_mod180': math.degrees(angle) % 180,
                      'length_m': max(ts)-min(ts),
                      'rms_residual_m': math.sqrt(sum(d*d for d in distances)/len(best)),
                      'endpoints_m': [[cx+t*ux, cy+t*uy] for t in [min(ts), max(ts)]],
                      'point_indices': sorted(best), 'object_identity': 'UNASSIGNED'})
        remaining.difference_update(best)
    return lines


def draw_plot(points, lines, destination, rotation=0, mirror=False, photo_candidate=False):
    from PIL import Image, ImageDraw, ImageFont
    def rotate(x, y):
        return transform_point(x, y, rotation, mirror)
    transformed = [rotate(p['x_m'], p['y_m']) for p in points]
    extent = max(max(abs(x), abs(y)) for x, y in transformed) + .4
    size, middle = 900, 450
    scale = 365/extent
    def pixel(x, y):
        return middle+x*scale, middle-y*scale
    image = Image.new('RGB', (size, 1030), '#101b2d')
    d = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 20)
    small = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 16)
    for i in range(-math.ceil(extent), math.ceil(extent)+1):
        if abs(i) > extent:
            continue
        x, y = pixel(i, i)
        d.line((x, 70, x, 830), fill='#334155')
        d.line((70, y, 830, y), fill='#334155')
        d.text((x, 840), str(i), fill='#cbd5e1', font=small)
        d.text((35, y-8), str(i), fill='#cbd5e1', font=small)
    for x, y in transformed:
        a, b = pixel(x, y)
        d.ellipse((a-2, b-2, a+2, b+2), fill='#5eead4')
    for line in lines:
        ends = [pixel(*rotate(*p)) for p in line['endpoints_m']]
        d.line((*ends[0], *ends[1]), fill='#fb923c', width=3)
        label_x = sum(p[0] for p in ends)/2
        label_y = sum(p[1] for p in ends)/2
        d.text((label_x+8, label_y-22), line['id'], fill='#f8fafc', font=font)
    d.ellipse((444, 444, 456, 456), fill='#ffffff')
    d.text((465, 453), 'LiDAR', fill='#ffffff', font=small)
    d.text((30, 22), f'Actual saved returns | rotation {rotation:.1f} deg | mirror {mirror}', fill='#ffffff', font=font)
    d.text((30, 885), 'Axes: metres from LiDAR. Orange: fitted surface segments A-H.', fill='#ffffff', font=font)
    d.text((30, 924), 'Object labels / photo alignment / robot heading UNVERIFIED.', fill='#cbd5e1', font=font)
    d.text((30, 963), 'Missing returns are UNKNOWN. Review only, not a navigation map.', fill='#cbd5e1', font=font)
    if photo_candidate:
        d.text((310, 55), 'Toward window (candidate)', fill='#ffffff', font=small)
        d.text((515, 405), 'A: bed-side candidate', fill='#ffffff', font=small)
        d.text((80, 375), 'B: left clutter candidate', fill='#ffffff', font=small)
        d.text((390, 235), 'C: back furniture candidate', fill='#ffffff', font=small)
    image.save(destination)


def report_html(result):
    """A static local review artifact, not a mock of the production App."""
    options = ''.join('<option value="'+c['id']+'"'+(' selected' if c['id'] == 'mirror1' else '')+'>'+c['id']+' / '+str(round(c['rotation_deg'], 1))+' deg</option>'
                      for c in result['orientation_candidates'])
    rows = ''.join('<tr><td>'+s['id']+'</td><td>'+str(round(s['length_m'], 2))+' m</td><td>'+str(s['support'])+'</td><td>'+str(round(s['rms_residual_m']*1000, 1))+' mm</td></tr>'
                   for s in result['surface_segments'])
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TwinPulse · Actual photo / scan review</title><style>
body{font-family:system-ui,sans-serif;margin:0;background:#101b2d;color:#e2e8f0}main{max-width:1400px;margin:auto;padding:24px}
h1{font-size:24px}p{line-height:1.65}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.grid img{width:100%;height:auto;display:block}
figure{margin:0}figcaption{padding:10px 0}select{padding:10px;margin-bottom:12px;background:#233047;color:inherit;max-width:100%}
table{border-collapse:collapse;width:100%;margin:12px 0}td,th{padding:8px;text-align:left;border-bottom:1px solid #334155}
.warning{border-left:3px solid #fb923c;padding:8px 16px}a{color:#5eead4}@media(max-width:800px){.grid{grid-template-columns:1fr}main{padding:14px}}
</style><main><h1>현장 사진 + 실제 라이다 · 정합 검토 초안</h1>
<p>같은 장소·같은 로봇 위치: 사용자 확인. 로봇 원점은 라이다 위치이며, 로봇의 전방은 아직 지정하지 않았습니다.</p>
<p class="warning">검토 후보입니다. 사진과 스캔의 좌표 보정·가구 식별은 미검증입니다. 로봇 제어/주행 지도/Active Twin에는 적용하지 않았습니다.</p>
<div class="grid"><figure><figcaption>원본 사진 · 변경 없이 보존</figcaption><img src="room.jpg" alt="사용자가 제공한 같은 위치의 방 사진"></figure>
<figure><figcaption>같은 위치의 실제 측정점 · 표시 방향 후보</figcaption><label for="candidate">방향 후보 </label><select id="candidate">'''+options+'''</select>
<img id="plot" src="candidate-mirror1.png" alt="실제 스캔의 미검증 표시 방향 후보"><p id="note">우선 검토 후보: A를 오른쪽 침대 옆면, C를 창문 쪽 가구 면으로 대응. 점군을 좌우 반전한 표시 후보이며, 실제 센서 축 보정값으로 확정한 것이 아닙니다.</p></figure></div>
<h2>측정값과 사진 해석 구분</h2><p>A~D는 실제 점군에 맞춘 선분입니다. 아래 길이는 보이는 선분 길이이지 가구 전체 치수가 아닙니다. 사진에서는 오른쪽 침대, 뒤쪽 책상·옷장, 왼쪽 의자·선풍기, 양쪽 앞부분 짐을 확인했습니다. 라이다는 한 높이의 단면만 보기 때문에 이 물체들이 모두 같은 모양으로 잡힌다고 가정하지 않습니다.</p>
<table><thead><tr><th>선분</th><th>관측 길이</th><th>지지 측정점</th><th>선 맞춤 RMS</th></tr></thead><tbody>'''+rows+'''</tbody></table>
<p>침대 높이·전체 방 치수·사진 픽셀→미터 변환은 아직 미확정입니다. 가려진 곳과 응답 없는 곳은 빈 공간으로 채우지 않았습니다. 사진 밖 영역의 사물도 임의로 붙이지 않았습니다.</p>
<p><a href="review.json">근거 및 후보 기록</a> · <a href="native-surfaces.png">변환 전 실제 점군</a></p></main>
<script>const select=document.getElementById('candidate');const allowed=['rotate0','rotate1','rotate2','rotate3','mirror0','mirror1','mirror2','mirror3'];
select.addEventListener('change',()=>{if(!allowed.includes(select.value))return;document.getElementById('plot').src='candidate-'+select.value+'.png';document.getElementById('note').textContent=select.value==='mirror1'?'우선 검토 후보: A=침대 옆면, C=창문 쪽 가구 면. 모두 미검증 대응입니다.':'대안 방향 후보입니다. 가구 대응 미지정. 변경은 이 화면에만 적용됩니다.';});</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photo', type=Path, required=True)
    parser.add_argument('--scan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from review_lidar_recording import summarize
    capture = args.scan / 'lidar-20260927T031354Z-323c99a6'
    nodes = [json.loads(line) for line in (args.scan / 'nodes.ndjson').read_text().splitlines()]
    report = json.loads((capture / 'report.json').read_text())
    require_confirmed_pair(digest(args.photo), digest(capture / 'raw.bin'))
    summary, points = summarize((capture / 'raw.bin').read_bytes(), nodes, report)
    revision = InputRevision.create(
        prompt='이 사진기준으로 한번 해봐. 방금 스캔한 위치도 지금 이 사진 그대로야.',
        images=[('room.jpg', 'image/jpeg', args.photo.read_bytes())],
        measurement_constraints=[], profile_id='burger-photo-review-unqualified',
        generation_settings={'adapter_kind': 'local_photo_scan_review_no_provider'}, input_kind='photo')
    manifest = PhotoTrackManifest(site_id='bedroom-20260927', photo_input_digest=revision.digest,
                                  photo_sha256=digest(args.photo), photo_site_confirmed=True)
    manifest.verify_input(revision)
    lines = fit_segments(points)
    candidates = orientation_candidates(lines)
    result = {'schema_version': 'photo-native-scan-review-1.0', 'status': 'REVIEW_ONLY',
              'photo_input': revision.to_dict(), 'photo_track': manifest.to_dict(),
              'same_scan_position': {'source': 'user_declaration', 'confirmed': True},
              'raw_sha256': report['raw_sha256'], 'nodes_sha256': digest(args.scan / 'nodes.ndjson'),
              'selected_complete_scan': summary['selected_complete_scan'], 'surface_segments': lines,
              'photo_to_sensor_transform': None, 'robot_heading': None, 'room_dimensions_m': None,
              'photo_observations': PHOTO_OBSERVATIONS,
              'orientation_candidates': candidates,
              'preferred_display_hypothesis': {'id': 'mirror1', 'selection': 'qualitative_assistant_review_not_registration',
                  'semantic_candidates': {'A': 'right bed-side', 'B': 'left clutter/fan area', 'C': 'back furniture face'},
                  'correspondences_verified': False, 'metric_dimensions_from_photo': False},
              'geometry_verified': False, 'navigation_authorized': False, 'active_twin_modified': False}
    args.output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.photo, args.output / 'room.jpg')  # Preserve original photo bytes; never edit image.
    (args.output / 'review.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    draw_plot(points, lines, args.output / 'native-surfaces.png')
    for candidate in candidates:
        draw_plot(points, lines, args.output / ('candidate-'+candidate['id']+'.png'),
                  candidate['rotation_deg'], candidate['mirror_native_y'], candidate['id'] == 'mirror1')
    (args.output / 'index.html').write_text(report_html(result), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'photo_bound': manifest.ready_for_photo_review,
                      'manual_alignment_ready': manifest.ready_for_manual_alignment_review,
                      'orientation_candidates': len(candidates), 'segments': len(lines),
                      'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
