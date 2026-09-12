#!/usr/bin/env python3
"""Verify fixed lesson code, permitting only host page-node markers and inert markup formatting."""
import argparse,base64,hashlib,json,re
from pathlib import Path
from html.parser import HTMLParser
from platform_tools import force_utf8

class Markup(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=False);self.events=[];self.raw=0
    def handle_starttag(self,tag,attrs):
        self.events.append(('start',tag,tuple(sorted((k,v) for k,v in attrs if k!='data-page-node-id'))))
        if tag in {'script','style','pre','textarea'}:self.raw+=1
    def handle_endtag(self,tag):
        self.events.append(('end',tag))
        if tag in {'script','style','pre','textarea'}:self.raw=max(0,self.raw-1)
    def handle_startendtag(self,tag,attrs):self.events.append(('self',tag,tuple(sorted((k,v) for k,v in attrs if k!='data-page-node-id'))))
    def handle_data(self,data):
        if not self.raw and data.isspace() and '\n' in data:return
        self.events.append(('data',data))
    def handle_comment(self,data):self.events.append(('comment',data))
    def handle_decl(self,data):self.events.append(('decl',data))
    def handle_entityref(self,name):self.events.append(('entity',name))
    def handle_charref(self,name):self.events.append(('char',name))
def canonical(html):
    parser=Markup();parser.feed(html);parser.close();return parser.events

def verify_template(skill_root):
    root=Path(skill_root);manifest=json.loads((root/'assets/template-manifest.json').read_text(encoding='utf-8'));template=(root/'assets/lesson.html').read_text(encoding='utf-8')
    if template.count('__EXAM_DATA__')!=1:raise ValueError('Template must contain exactly one data placeholder')
    actual=hashlib.sha256(template.encode()).hexdigest()
    if actual!=manifest['template_sha256']:raise ValueError('Bundled template differs from its manifest; restore package or explicitly version an authorized template change')
    return template,manifest

def verify_output(output,skill_root=None):
    root=Path(skill_root) if skill_root else Path(__file__).resolve().parents[1];template,manifest=verify_template(root);out=Path(output);html=(out/'index.html').read_text(encoding='utf-8');before,after=template.split('__EXAM_DATA__');method='exact'
    if html.startswith(before) and html.endswith(after):payload=html[len(before):len(html)-len(after)]
    else:
        matches=list(re.finditer(r'<script\b(?=[^>]*\bid=[\"\']examData[\"\'])[^>]*>(.*?)</script\s*>',html,re.S))
        if len(matches)!=1:raise ValueError('Missing or duplicate examData payload')
        payload=matches[0].group(1)
        if canonical(html)!=canonical(template.replace('__EXAM_DATA__',payload)):raise ValueError('Generated HTML does not match the bundled template; host markers do not permit code, style or functional changes')
        method='host_markup_normalized'
    data=json.loads(payload);media=data.pop('_embedded_audio',{})
    if data!=json.loads((out/'exam.json').read_text(encoding='utf-8')):raise ValueError('Embedded exam data differs from exam.json')
    paths=set([data['full_audio']] if data.get('full_audio') else [])
    for section in data['sections']:
        if section.get('audio'):paths.add(section['audio'])
        paths.update(q['audio'] for q in section['questions'] if q.get('audio'))
    if data.get('audio_delivery',{}).get('mode')=='embedded' and set(media)!=paths:raise ValueError('Embedded audio coverage mismatch')
    for name,value in media.items():
        if name not in paths or ';base64,' not in value:raise ValueError('Unexpected embedded audio')
        binary=base64.b64decode(value.split(';base64,',1)[1],validate=True)
        if binary!=(out/name).read_bytes():raise ValueError('Embedded audio differs from packaged file: '+name)
    resources=set(paths)
    for section in data['sections']:
        if section.get('origin',{}).get('page_image'):resources.add(section['origin']['page_image'])
        resources.update(p['image'] for p in section.get('paragraphs',[]) if p.get('image'))
    fingerprints={}
    for name in sorted(resources):
        file=(out/name).resolve()
        if out.resolve() not in file.parents or not file.is_file() or file.stat().st_size==0:raise ValueError('Missing or invalid packaged media: '+name)
        fingerprints[name]=hashlib.sha256(file.read_bytes()).hexdigest()
    return {'resource_sha256':fingerprints,'status':'passed','comparison':method,'template_version':manifest['template_version'],'template_sha256':manifest['template_sha256'],'html_sha256':hashlib.sha256(html.encode()).hexdigest(),'ignored_host_attributes':['data-page-node-id'] if method!='exact' else [],'scope':'Template code and embedded-data verification only. Not an answer, audio-alignment or teaching-quality certificate.'}
if __name__=='__main__':
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args()
    try:print(json.dumps(verify_output(a.output),ensure_ascii=False))
    except (ValueError,KeyError,FileNotFoundError) as e:p.exit(1,'ERROR: '+str(e)+'\n')
