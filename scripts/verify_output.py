#!/usr/bin/env python3
"""Verify fixed lesson code, permitting only host page-node markers and inert markup formatting."""
import argparse,base64,hashlib,json,re
from pathlib import Path
from html.parser import HTMLParser
from platform_tools import explain_error,force_utf8

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
    if template.count('__EXAM_DATA__')!=1:raise ValueError(f'模板里的 __EXAM_DATA__ 占位符必须正好 1 个，实际 {template.count("__EXAM_DATA__")} 个；请重新安装完整 Skill 包')
    actual=hashlib.sha256(template.encode()).hexdigest()
    if actual!=manifest['template_sha256']:raise ValueError('assets/lesson.html 与模板清单 assets/template-manifest.json 的指纹不一致：模板被改动过或安装不完整。请恢复官方包；确实要改模板就必须同时更新 template_sha256 与 template_version 并重新验收')
    return template,manifest

def verify_output(output,skill_root=None):
    root=Path(skill_root) if skill_root else Path(__file__).resolve().parents[1];template,manifest=verify_template(root);out=Path(output);html=(out/'index.html').read_text(encoding='utf-8');before,after=template.split('__EXAM_DATA__');method='exact'
    if html.startswith(before) and html.endswith(after):payload=html[len(before):len(html)-len(after)]
    else:
        matches=list(re.finditer(r'<script\b(?=[^>]*\bid=[\"\']examData[\"\'])[^>]*>(.*?)</script\s*>',html,re.S))
        if len(matches)!=1:raise ValueError(f'index.html 里的 examData 数据块应正好 1 个，实际 {len(matches)} 个；请重新构建，不要手工编辑生成的 HTML')
        payload=matches[0].group(1)
        if canonical(html)!=canonical(template.replace('__EXAM_DATA__',payload)):raise ValueError('生成的 HTML 与官方模板不一致（只允许宿主注入的页面标记与标签间空行差异）：代码、样式或功能被改过。请用官方模板重新构建，不要手工改 index.html')
        method='host_markup_normalized'
    try:data=json.loads(payload)
    except ValueError as error:
        # 手工编辑或宿主注入把数据块弄坏/弄成两份时，以前会把 json 模块的英文原文甩出来
        # （实测：`JSONDecodeError: Extra data: line 1 column 456981`），既看不懂也不知道该做什么。
        raise ValueError(f'index.html 里的 examData 不是合法 JSON（可能被手工编辑，或嵌入了两份数据）：{error}；'
                         '请用官方模板重新构建，不要手工改 index.html') from None
    media=data.pop('_embedded_audio',{})
    if data!=json.loads((out/'exam.json').read_text(encoding='utf-8')):raise ValueError('index.html 内嵌的考试数据与 exam.json 不一致；请重新构建，确保交付的是同一次生成的产物')
    paths=set([data['full_audio']] if data.get('full_audio') else [])
    for section in data['sections']:
        if section.get('audio'):paths.add(section['audio'])
        paths.update(q['audio'] for q in section['questions'] if q.get('audio'))
    if data.get('audio_delivery',{}).get('mode')=='embedded' and set(media)!=paths:raise ValueError(f'内嵌音频与音频文件不一致：课件登记 {len(paths)} 个音频文件，实际内嵌 {len(media)} 个；请重新构建')
    for name,value in media.items():
        # 两条分开报：一是"内嵌了清单里没有的音频"（手改 HTML 或宿主注入），二是"值不是 data:…;base64"
        # 这种形式（页面里根本播不出声）。以前合成一句，第二种情况会被说成"找不到文件"，指错方向。
        if name not in paths:raise ValueError(f'出现了没有对应音频文件的内嵌音频：{name}（audio/ 目录里找不到这个文件）；请重新构建')
        if ';base64,' not in value:raise ValueError(f'内嵌音频 {name} 不是 data:…;base64 形式，页面里播不出声；请重新构建，不要手工编辑生成的 HTML')
        binary=base64.b64decode(value.split(';base64,',1)[1],validate=True)
        target=out/name
        # 文件不在时不在这里报：下面的资源清单循环会给出「缺少或无效的媒体文件：<名字>」。
        # 以前这里直接 read_bytes()，文件缺失会抛英文的 FileNotFoundError，比报错更难懂。
        if target.is_file() and binary!=target.read_bytes():raise ValueError('内嵌音频与 audio/ 里的同名文件内容不一致：'+name+'；请重新构建，避免课上播放的是旧音频')
    resources=set(paths)
    for section in data['sections']:
        origin=section.get('origin',{})
        if origin.get('page_image'):resources.add(origin['page_image'])
        resources.update(origin.get('page_images') or [])
        resources.update(p['image'] for p in section.get('paragraphs',[]) if p.get('image'))
        for q in section.get('questions',[]):
            resources.update((q.get('option_images') or {}).values())
    fingerprints={}
    for name in sorted(resources):
        file=(out/name).resolve()
        if out.resolve() not in file.parents or not file.is_file() or file.stat().st_size==0:raise ValueError('缺少或无效的媒体文件：'+name+'（文件不存在、为空，或指向输出目录之外）；请重新构建或重新复制素材')
        fingerprints[name]=hashlib.sha256(file.read_bytes()).hexdigest()
    return {'resource_sha256':fingerprints,'status':'passed','comparison':method,'template_version':manifest['template_version'],'template_sha256':manifest['template_sha256'],
      # Hash the file's real bytes, not the newline-normalized text: on Windows write_text
      # emits CRLF while read_text normalizes it away, so a text hash would disagree with
      # browser_check.cjs and package_lesson.py, which both hash raw bytes.
      'html_sha256':hashlib.sha256((out/'index.html').read_bytes()).hexdigest(),'ignored_host_attributes':['data-page-node-id'] if method!='exact' else [],'scope':'Template code and embedded-data verification only. Not an answer, audio-alignment or teaching-quality certificate.'}
if __name__=='__main__':
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args()
    try:print(json.dumps(verify_output(a.output),ensure_ascii=False))
    except (ValueError,KeyError,FileNotFoundError) as e:p.exit(1,'ERROR: '+explain_error(e,'先跑 scripts/build.py <exam.json> <输出目录> 生成产物')+'\n')
