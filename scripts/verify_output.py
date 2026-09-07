#!/usr/bin/env python3
"""Verify a generated lesson uses the bundled template exactly, apart from exam data."""
import argparse,hashlib,json
from pathlib import Path

def verify_template(skill_root):
    root=Path(skill_root);manifest=json.loads((root/'assets/template-manifest.json').read_text())
    template=(root/'assets/lesson.html').read_text()
    if template.count('__EXAM_DATA__')!=1:raise ValueError('Template must contain exactly one data placeholder')
    actual=hashlib.sha256(template.encode()).hexdigest()
    if actual!=manifest['template_sha256']:raise ValueError('Bundled template differs from its manifest; restore package or explicitly version an authorized template change')
    return template,manifest

def verify_output(output,skill_root=None):
    root=Path(skill_root) if skill_root else Path(__file__).resolve().parents[1]
    template,manifest=verify_template(root);out=Path(output)
    before,after=template.split('__EXAM_DATA__');html=(out/'index.html').read_text()
    if not html.startswith(before) or not html.endswith(after):raise ValueError('Generated HTML does not match the bundled template. Rebuild with scripts/build.py; do not rewrite the interface')
    payload=html[len(before):len(html)-len(after)]
    if json.loads(payload)!=json.loads((out/'exam.json').read_text()):raise ValueError('Embedded exam data differs from exam.json')
    return {'status':'passed','template_version':manifest['template_version'],'template_sha256':manifest['template_sha256'],'html_sha256':hashlib.sha256(html.encode()).hexdigest(),'scope':'Exact template and embedded-data verification; not an audit of OCR, teaching content, audio alignment or host compatibility.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args()
    try:print(json.dumps(verify_output(a.output),ensure_ascii=False))
    except (ValueError,KeyError,FileNotFoundError) as e:p.exit(1,'ERROR: '+str(e)+'\n')
