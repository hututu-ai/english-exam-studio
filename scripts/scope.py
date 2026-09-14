#!/usr/bin/env python3
"""Resolve a teacher's requested sections before authoring or building."""
import argparse, copy, json
from pathlib import Path
from exam_document import load as load_exam
from platform_tools import explain_error,force_utf8
import section_kinds

# 老师说的板块名 → 呈现预设；匹配时还会按 section.id / kind / group 命中，所以
# 初中卷的"短文填空""配对阅读""语法选择"这些名字即使不在这里也能选中。
ALIASES={'听力':'listening','精听':'listening','听说应用':'listening','听说':'listening','听力理解':'listening',
         '阅读':'reading','阅读理解':'reading','任务型阅读':'reading',
         '七选五':'seven','配对阅读':'seven','信息匹配':'seven','阅读填空':'seven',
         '完形':'cloze','完型':'cloze','完形填空':'cloze','语法选择':'cloze',
         '语法填空':'grammar','短文填空':'grammar','词汇运用':'grammar','单词拼写':'grammar',
         '写作':'writing','书面表达':'writing','读写综合':'writing','读后续写':'writing','概要写作':'writing'}

RANGE_LETTERS={'a':('listening','范围 A = 只做听力'),'b':('all','范围 B = 整卷讲评'),'c':(None,'范围 C = 指定板块')}

def normalize_tokens(tokens,sections):
    """把老师说的范围字母 A/B/C 与"章节 ID"分开。

    老师的原话是"A 只做听力 / B 整卷 / C 指定板块"，助手完全可能把 A 直接传给 --sections；
    但示例卷的阅读节 ID 恰好就是 "A"——所以能对上章节 ID 时按 ID，对不上才按范围字母解释。
    """
    ids={s.get('id') for s in sections or []}
    out=[]
    for token in tokens:
        if len(token)==1 and token.lower() in RANGE_LETTERS and token not in ids:
            meaning,label=RANGE_LETTERS[token.lower()]
            if meaning is None:
                raise ValueError('C 表示"指定板块"：请把具体板块名写在 --sections 里（例如 --sections 阅读理解,配对阅读）；只写 C 无法知道要讲哪一节')
            if meaning=='all':
                if len(tokens)>1:raise ValueError('B 表示"整卷讲评"，不能与其他板块混用；只做部分板块请用具体板块名，例如 --sections 阅读理解,配对阅读')
                return ['all']
            out.append(meaning)
        else:out.append(token)
    return out

def select(exam, selection='all', mode=None):
    mode=mode or exam.get('generation_scope',{}).get('mode') or 'lesson'
    result=copy.deepcopy(exam)
    tokens=[t.strip() for t in selection.replace('，',',').split(',') if t.strip()]
    if not tokens:raise ValueError('请选择 all、题型或章节 ID，例如 reading,A,L6')
    sections_all=exam.get('sections',[])
    tokens=normalize_tokens(tokens,sections_all)
    if 'all' in tokens and tokens!=['all']:raise ValueError('all 不能与其他板块混用，请选择整卷或指定板块')
    sections=exam.get('sections',[])
    if mode=='intensive' and tokens==['all']:tokens=['listening']
    if 'all' not in tokens:
        matched=set()
        for token in tokens:
            target=ALIASES.get(token,token)
            found=[s['id'] for s in sections if s['id']==target or str(s.get('kind') or '')==target
                   or section_kinds.preset(s)==target or section_kinds.group_key(s)==target]
            if not found:
                if target=='listening':
                    raise ValueError(f'材料中没有听力节（{token} 表示"只做听力"）：这份卷子里没有 kind 为听说应用/听力 的节，也没有带音频的节；'
                                     f'整卷讲评请用 all，其他板块请直接写板块名')
                raise ValueError('材料中没有这个板块：'+token)
            matched.update(found)
        result['sections']=[s for s in sections if s['id'] in matched]
    if not result.get('sections'):raise ValueError('没有选中任何板块')
    if mode=='intensive' and any(not section_kinds.is_listening(s) for s in result['sections']):
        raise ValueError('精听模式只接受听力章节（kind 为 listening/听力理解，或本节带音频）；阅读精读请用普通讲评模式')
    # Preserve the original coverage contract when no section is removed. Otherwise
    # a missing question could silently disappear from the expected list as well.
    if len(result['sections'])!=len(sections) or 'expected_question_ids' not in exam:
        result['expected_question_ids']=[str(q['id']) for s in result['sections'] for q in s.get('questions',[])]
    result['generation_scope']={'section_ids':[s['id'] for s in result['sections']],
        'mode':mode,'selection':selection,'partial':bool(exam.get('generation_scope',{}).get('partial')) or len(result['sections'])!=len(sections)}
    if not any(section_kinds.is_listening(s) for s in result['sections']):result.pop('full_audio',None)
    return result

def main():
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('exam');p.add_argument('--sections',default='all')
    p.add_argument('--mode',choices=['lesson','intensive']);p.add_argument('--out')
    a=p.parse_args();source=Path(a.exam)
    try:
        d=select(load_exam(source),a.sections,a.mode)
        if a.out:
            target=Path(a.out)
            # Keep relative media valid without rewriting every content field.
            if target.resolve().parent!=source.resolve().parent:raise ValueError('--out 必须与原 exam.json 同目录，避免素材相对路径失效')
            target.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(d['generation_scope'],ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError) as e:p.exit(1,f'ERROR: {explain_error(e)}\n')
if __name__=='__main__':main()
