#!/usr/bin/env python3
"""Fill long source quotes from character ranges so nobody retypes (or mistypes) them.

Instead of copying a 40-word sentence into evidence/writing_bank and hoping it matches byte for
byte, write the range and let this fill it:

  {"paragraph_id":"A-p2","quote_ref":[120,158]}      ->  {"paragraph_id":"A-p2","quote":"..."}
  {"paragraph_id":"A-p2","source_quote_ref":[120,158]} -> {"paragraph_id":"A-p2","source_quote":"..."}

  python3 scripts/quotes.py fill WORK/exam.json [--out WORK/exam.json]
  python3 scripts/quotes.py check WORK/exam.json
"""
import argparse,json,re,sys
from pathlib import Path
from platform_tools import force_utf8

def norm(t):
    return re.sub(r'\s+',' ',str(t).translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))).strip()

def paragraphs(document):
    table={}
    for section in document.get('sections',[]):
        for paragraph in section.get('paragraphs',[]) or []:
            if isinstance(paragraph,dict) and paragraph.get('id') is not None:
                table[(section.get('id'),str(paragraph['id']))]=paragraph.get('text','')
    return table

def walk(node,fills,errors,current_section=None):
    if isinstance(node,list):
        for item in node:walk(item,fills,errors,current_section)
        return
    if not isinstance(node,dict):return
    section=node.get('id') if ('kind' in node and 'questions' in node) else current_section
    pid=node.get('paragraph_id')
    for key,target in (('quote_ref','quote'),('source_quote_ref','source_quote')):
        ref=node.get(key)
        if ref is None:continue
        paragraph_id=pid or (ref.get('paragraph_id') if isinstance(ref,dict) else None)
        chars=ref.get('chars') if isinstance(ref,dict) else ref
        text=fills['paragraphs'].get((section,str(paragraph_id)))
        if text is None:
            errors.append(f"{key} 指向不存在的段落 {paragraph_id}（section {section}）");continue
        if not (isinstance(chars,list) and len(chars)==2 and all(isinstance(x,int) for x in chars)):
            errors.append(f"{key} 需要 [start,end] 两个整数");continue
        start,end=chars
        if not (0<=start<end<=len(text)):
            errors.append(f"{paragraph_id} 的范围 [{start},{end}] 超出段落长度 {len(text)}");continue
        node[target]=text[start:end]
        del node[key]
        fills['items'].append({'paragraph_id':paragraph_id,'chars':chars,'quote':node[target][:60]})
    for value in list(node.values()):walk(value,fills,errors,section)

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def fill(path,out):
    document=load(path)
    data={'paragraphs':paragraphs(document),'items':[]}
    errors=[]
    walk(document,data,errors)
    if errors:raise ValueError('引用范围有问题：\n- '+'\n- '.join(errors))
    target=Path(out or path);target.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'filled':len(data['items']),'out':str(target),'items':data['items'][:20]}

def check(path):
    document=load(path);table=paragraphs(document)
    problems=[];counts={'quote':0}
    def scan(node,section=None):
        if isinstance(node,list):
            for item in node:scan(item,section)
            return
        if not isinstance(node,dict):return
        section=node.get('id') if ('kind' in node and 'questions' in node) else section
        for key in ('quote','source_quote'):
            value=node.get(key)
            if isinstance(value,str) and value.strip():
                counts['quote']+=1
                pid=node.get('paragraph_id')
                text=table.get((section,str(pid)))
                if text is None:problems.append(f'{section}: {key} 所在条目缺少可对应的 paragraph_id')
                elif norm(value) not in norm(text):problems.append(f'{section}/{pid}: {key} 不是该段落的逐字子串（"{value[:40]}…"）')
        for value in node.values():scan(value,section)
    scan(document)
    return {'quotes_checked':counts['quote'],'problems':problems,'status':'ok' if not problems else 'needs_fix'}

def main():
    force_utf8()
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('fill');x.add_argument('exam');x.add_argument('--out');x.set_defaults(func=lambda a:fill(a.exam,a.out))
    x=sub.add_parser('check');x.add_argument('exam');x.set_defaults(func=lambda a:check(a.exam))
    a=p.parse_args()
    try:result=a.func(a)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:sys.exit(f'ERROR: {e}')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result.get('status')=='needs_fix' else 0

if __name__=='__main__':raise SystemExit(main())
