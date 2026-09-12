#!/usr/bin/env python3
"""Resolve a teacher's requested sections before authoring or building."""
import argparse, copy, json
from pathlib import Path
from platform_tools import force_utf8

ALIASES={'听力':'listening','精听':'listening','阅读':'reading','七选五':'seven',
         '完形':'cloze','完型':'cloze','语法填空':'grammar','写作':'writing'}

def select(exam, selection='all', mode=None):
    mode=mode or exam.get('generation_scope',{}).get('mode') or 'lesson'
    result=copy.deepcopy(exam)
    tokens=[t.strip() for t in selection.replace('，',',').split(',') if t.strip()]
    if not tokens:raise ValueError('请选择 all、题型或章节 ID，例如 reading,A,L6')
    if 'all' in tokens and tokens!=['all']:raise ValueError('all 不能与其他板块混用，请选择整卷或指定板块')
    sections=exam.get('sections',[])
    if mode=='intensive' and tokens==['all']:tokens=['listening']
    if 'all' not in tokens:
        matched=set()
        for token in tokens:
            target=ALIASES.get(token,token)
            found=[s['id'] for s in sections if s['id']==target or s['kind']==target]
            if not found:raise ValueError('材料中没有这个板块：'+token)
            matched.update(found)
        result['sections']=[s for s in sections if s['id'] in matched]
    if not result.get('sections'):raise ValueError('没有选中任何板块')
    if mode=='intensive' and any(s['kind']!='listening' for s in result['sections']):
        raise ValueError('精听模式只接受听力 Text；阅读精读请用普通讲评模式')
    # Preserve the original coverage contract when no section is removed. Otherwise
    # a missing question could silently disappear from the expected list as well.
    if len(result['sections'])!=len(sections) or 'expected_question_ids' not in exam:
        result['expected_question_ids']=[str(q['id']) for s in result['sections'] for q in s.get('questions',[])]
    result['generation_scope']={'section_ids':[s['id'] for s in result['sections']],
        'mode':mode,'selection':selection,'partial':bool(exam.get('generation_scope',{}).get('partial')) or len(result['sections'])!=len(sections)}
    if not any(s['kind']=='listening' for s in result['sections']):result.pop('full_audio',None)
    return result

def main():
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('exam');p.add_argument('--sections',default='all')
    p.add_argument('--mode',choices=['lesson','intensive']);p.add_argument('--out')
    a=p.parse_args();source=Path(a.exam)
    try:
        d=select(json.loads(source.read_text(encoding='utf-8')),a.sections,a.mode)
        if a.out:
            target=Path(a.out)
            # Keep relative media valid without rewriting every content field.
            if target.resolve().parent!=source.resolve().parent:raise ValueError('--out 必须与原 exam.json 同目录，避免素材相对路径失效')
            target.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(d['generation_scope'],ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError) as e:p.exit(1,f'ERROR: {e}\n')
if __name__=='__main__':main()
