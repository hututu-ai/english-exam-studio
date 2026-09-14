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
import exam_document
from grounding import span_problem
from platform_tools import explain_error,force_utf8

# 引用范围与精听挖空共用 grounding.span_problem 的判据；这里只负责把它翻译成引用语境的说明。
SPAN_MESSAGES={'invalid':'下标无效','blank':'是空白，等于没有证据',
               'punctuation':'里没有真实词语，只遮到标点或空格',
               'half_word_start':'起点不在词首，会把单词截断','half_word_end':'终点不在词尾，会把单词截断'}

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
        if paragraph_id is None:
            candidates=node.get('paragraph_ids')
            if isinstance(candidates,list) and len(candidates)==1:paragraph_id=candidates[0]
            elif isinstance(candidates,list) and candidates:
                errors.append(f'{key} 在多段条目上无法判断范围属于哪一段；写成 {{"paragraph_ids":[...],"quote_ref":{{"paragraph_id":"...","chars":[start,end]}}}}')
                continue
        chars=ref.get('chars') if isinstance(ref,dict) else ref
        text=fills['paragraphs'].get((section,str(paragraph_id)))
        if text is None:
            errors.append(f"{key} 指向不存在的段落 {paragraph_id}（section {section}）");continue
        if not (isinstance(chars,list) and len(chars)==2 and all(isinstance(x,int) for x in chars)):
            errors.append(f"{key} 需要 [start,end] 两个整数");continue
        start,end=chars
        if not (0<=start<end<=len(text)):
            errors.append(f"{paragraph_id} 的范围 [{start},{end}] 超出段落长度 {len(text)}");continue
        # 只有"是逐字子串"这一条不够：切在单词中间得到的仍是子串，下游闸门查不出来，
        # 于是半截词会当成证据发到页面上。这里与精听挖空用同一条判据。
        problem=span_problem(text,start,end)
        if problem:
            errors.append(f"{key} 指向的 [{start},{end}] {SPAN_MESSAGES[problem]}：引用必须落在完整词上，现在会得到 {text[start:end]!r}");continue
        node[target]=text[start:end]
        del node[key]
        fills['items'].append({'paragraph_id':paragraph_id,'chars':chars,'quote':node[target][:60]})
    for value in list(node.values()):walk(value,fills,errors,section)

def load(path):
    return exam_document.load(path)

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
            if not isinstance(value,str):continue
            counts['quote']+=1
            # 篇章结构等条目用 paragraph_ids（复数）引用多段，引文只要落在其中一段即可。
            ids=[]
            if node.get('paragraph_id') is not None:ids=[node.get('paragraph_id')]
            elif isinstance(node.get('paragraph_ids'),list):ids=list(node['paragraph_ids'])
            if not ids:problems.append(f'{section}: {key} 所在条目缺少可对应的 paragraph_id 或 paragraph_ids')
            else:
                texts=[table.get((section,str(pid))) for pid in ids]
                if all(text is None for text in texts):problems.append(f'{section}: {key} 指向不存在的段落 {ids}')
                elif not value.strip():problems.append(f'{section}/{ids}: {key} 是空白或空串，等于没有证据')
                elif not any(norm(value) in norm(text) for text in texts):
                    problems.append(f'{section}/{ids}: {key} 不是所引用段落的逐字子串（"{value[:40]}…"）')
                else:
                    # 逐字子串也可能是从单词中间切出来的（quote_ref 填错范围就会这样）：下游只看"是不是子串"，
                    # 所以半截词必须在这里点名。
                    for text in texts:
                        if text is None:continue
                        at=text.find(value)
                        if at<0:continue        # 只有归一化后才匹配（空白/引号写法不同），定位不到就不断言
                        problem=span_problem(text,at,at+len(value))
                        if problem in ('half_word_start','half_word_end'):
                            problems.append(f'{section}/{ids}: {key} 把单词截断了（{SPAN_MESSAGES[problem]}）："{value[:40]}"')
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
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:sys.exit(f'ERROR: {explain_error(e)}')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result.get('status')=='needs_fix' else 0

if __name__=='__main__':raise SystemExit(main())
