# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Render every final report page and create contact sheets for visual review."""
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/progressive-preview-20261013'


def main():
    path=OUT/'report-final.pdf';folder=OUT/'pdf-qa'
    folder.mkdir(exist_ok=False)
    reader=PdfReader(path)
    text=[page.extract_text() for page in reader.pages]
    assert all(row.strip() for row in text), 'Empty report page'
    assert 'TwinPulse' in text[0] and '검증' in text[0], 'Title glyph extraction failed'
    subprocess.run(['pdftoppm','-png','-scale-to','1000',str(path),str(folder/'page')],check=True)
    pages=sorted(folder.glob('page-*.png'))
    assert len(pages)==len(reader.pages)
    for start in range(0,len(pages),8):
        sheet=Image.new('RGB',(4*300,2*450),'#e7edf0');draw=ImageDraw.Draw(sheet)
        for index,source in enumerate(pages[start:start+8]):
            with Image.open(source) as original:
                original.load();copy=original.copy();copy.thumbnail((288,416))
            x=(index%4)*300+6;y=(index//4)*450+24
            sheet.paste(copy,(x+(288-copy.width)//2,y));draw.text((x,y-18),'Page '+str(start+index+1),fill='black')
        sheet.save(folder/('contact-'+str(start//8+1)+'.png'))
    result=dict(status='RENDERED_PENDING_VISUAL_REVIEW',pages=len(pages),
        pdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        all_pages_have_text=True,korean_title_extracted=True,external_requests=0)
    (folder/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
