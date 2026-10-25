# SPDX-License-Identifier: Apache-2.0
"""Record model visual inspection AFTER view_image; not a vision ground truth."""
import hashlib,json
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parents[1]/'outputs/environment-alignment-20261024-01'
names=['ui06/02-aligned-current.png','ui06/03b-moved-tracking.png','ui06/04-off-hidden.png','cold05/02-saved-overlay.png']
rows=[]
for name in names:
    path=root/name
    with Image.open(path) as image:
        rgb=image.convert('RGB');crop=rgb.crop((650,100,min(1265,rgb.width),min(507,rgb.height)))
        purple=sum(r>110 and b>140 and b>g+30 and r>g+20 for r,g,b in crop.getdata())
        rows.append(dict(path=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),size=list(image.size),purple_pixels_in_twin_roi=purple))
review=dict(method='MODEL_VISUAL_INSPECTION_VIA_VIEW_IMAGE_PLUS_SUPPLEMENTARY_COLOR_COUNTS',images=rows,
    robot_body_and_scan_visible=True,off_removes_review_layer=True,saved_not_live=True,
    physical_world_registration_verified=False,not_human_or_optical_ground_truth=True,
    notes='Actual body, separate purple scan hits/rays and under-body labels were inspected; current/saved legends distinguished. Recording pointer is an annotation of actual input, not a robot origin circle.')
with (root/'visual-review01.json').open('x',encoding='utf-8') as stream:json.dump(review,stream,indent=2)
print(json.dumps(dict(images=len(rows),purple=[r['purple_pixels_in_twin_roi'] for r in rows])))
