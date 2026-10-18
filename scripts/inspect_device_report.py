# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Rendered-page QA for the local device-flow PDF, no external requests."""
from pathlib import Path
import json
from PIL import Image,ImageDraw
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/product-flow-20261013/device-final-report'
reader=PdfReader(OUT/'TwinPulse-device-flow-report.pdf')
texts=[page.extract_text() for page in reader.pages]
assert all(text.strip() for text in texts)
assert 'TwinPulse' in texts[0] and '검증' in texts[0]
pages=sorted(OUT.glob('page-*.png'))
assert len(pages)==len(reader.pages)
for start in range(0,len(pages),8):
    sheet=Image.new('RGB',(1200,900),'#dfe7ec');draw=ImageDraw.Draw(sheet)
    for index,path in enumerate(pages[start:start+8]):
        with Image.open(path) as image:
            copied=image.copy();copied.thumbnail((288,420))
        x=(index%4)*300+6;y=(index//4)*450+24
        sheet.paste(copied,(x+(288-copied.width)//2,y))
        draw.text((x,y-18),'Page '+str(start+index+1),fill='black')
    sheet.save(OUT/('contact-'+str(start//8+1)+'.png'))
(OUT/'pdf-qa.json').write_text(json.dumps(dict(pages=len(pages),all_pages_have_text=True,korean_title_extracted=True)),encoding='utf-8')
print(json.dumps(dict(pages=len(pages),contact_sheets=(len(pages)+7)//8)))
