#!/usr/bin/env python3
"""DOCX extraction preserving block order; images kept for visual checking."""
import argparse,json,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from platform_tools import force_utf8
force_utf8()
p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('out');a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with zipfile.ZipFile(a.input) as z:
    root=ET.fromstring(z.read('word/document.xml')); blocks=[]
    for node in root.find('w:body',ns):
        kind=node.tag.split('}')[-1]
        if kind=='p': blocks.append({'type':'paragraph','text':''.join(x.text or '' for x in node.findall('.//w:t',ns))})
        elif kind=='tbl':blocks.append({'type':'table','rows':[[''.join(x.text or '' for x in cell.findall('.//w:t',ns)) for cell in row.findall('w:tc',ns)] for row in node.findall('w:tr',ns)]})
    images=[]
    for name in z.namelist():
        if name.startswith('word/media/') and not name.endswith('/'):
            target=out/'images'/Path(name).name;target.parent.mkdir(exist_ok=True);target.write_bytes(z.read(name));images.append(str(target.relative_to(out)))
    (out/'extracted.json').write_text(json.dumps({'blocks':blocks,'images':images,'note':'Verify images, layout, underlines and OCR against source.'},ensure_ascii=False,indent=2))
    print(f'{len(blocks)} blocks; {len(images)} images extracted')
