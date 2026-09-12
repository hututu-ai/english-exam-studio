#!/usr/bin/env python3
"""Draft the source ledger and the exam.json skeleton so nobody retypes the whole paper by hand.

  scaffold.py ledger --paper WORK/extracted.json --answers WORK/answers.json --out WORK/source-ledger.json
  scaffold.py exam   --ledger WORK/source-ledger.json --out WORK/exam.json

Both outputs are drafts: the ledger must be compared page by page with the paper, and the exam
skeleton still fails validate_features until the teaching content is written. The win is that the
paper text, options, question numbers and official answers are transcribed once, by machine.
"""
import argparse,hashlib,json,re,sys
from pathlib import Path
from platform_tools import force_utf8

QUESTION=re.compile(r'^\s*(\d{1,3})\s*[.、．)）]\s*(\S.*)$')
OPTION=re.compile(r'^\s*\(?([A-H])[).、．]\s*(\S.*)$')
INLINE_OPTIONS=re.compile(r'(?:(?<=^)|(?<=\s))([A-H])[.、．]\s*(.+?)(?=\s+[A-H][.、．]\s|$)')
LETTERS='ABCDEFGH'

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def load_blocks(path):
    path=Path(path)
    if path.suffix.lower()=='.json':
        data=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data,dict) and 'blocks' in data:
            lines=[]
            for block in data['blocks']:
                if block.get('type')=='table':
                    for row in block.get('rows',[]):lines.append({'text':'\t'.join(row),'table':True})
                else:lines.append({'text':block.get('text',''),'table':False})
            return lines
        raise ValueError('--paper 需要一个 blocks 数组（scripts/extract.py 的输出）或 .txt/.md 文件')
    return [{'text':line,'table':False} for line in path.read_text(encoding='utf-8',errors='replace').splitlines()]

def split_options(text):
    found={m.group(1).upper():m.group(2).strip() for m in INLINE_OPTIONS.finditer(text)}
    if len(found)>=2:
        stem=text[:INLINE_OPTIONS.search(text).start()].strip()
        return stem,{k:found[k] for k in sorted(found)}
    return text.strip(),{}

def parse_questions(lines):
    sections=[];current=None;unparsed=[];pending=None
    for index,row in enumerate(lines,1):
        text=row['text'].strip()
        if not text:
            if current and current['questions'] and not current['questions'][-1]['options']:pending='options_open'
            continue
        match=QUESTION.match(text)
        if match:
            qid=match.group(1);stem,options=split_options(match.group(2))
            if current is None:
                current={'questions':[],'paragraphs':[]};sections.append(current)
            current['questions'].append({'id':qid,'stem':stem,'options':options,'raw':text})
            continue
        option=OPTION.match(text)
        if option and current and current['questions']:
            target=current['questions'][-1]
            if option.group(1).upper() in target['options'] and len(target['options'])>1:unparsed.append({'line':index,'text':text,'reason':'选项重复或题干未识别'})
            target['options'][option.group(1).upper()]=option.group(2).strip()
            continue
        if current and current['questions']:
            sections.append({'questions':[],'paragraphs':[]});current=sections[-1]
        if current is None:
            current={'questions':[],'paragraphs':[]};sections.append(current)
        current['paragraphs'].append(text)
    sections=[s for s in sections if s['questions'] or s['paragraphs']]
    for section in sections:
        for q in section['questions']:
            q['options']={k:v for k,v in sorted(q['options'].items())}
            if q['options'] and list(q['options'])!=list(LETTERS[:len(q['options'])]):
                unparsed.append({'line':0,'text':q['raw'],'reason':f"第{q['id']}题选项标签不连续：{list(q['options'])}"})
    return sections,unparsed

def build_ledger(paper,answers,title):
    lines=load_blocks(paper);sections,unparsed=parse_questions(lines)
    table={}
    if answers and Path(answers).is_file():
        data=json.loads(Path(answers).read_text(encoding='utf-8'));table=data.get('answers',{})
    ledger={'title':title or '英语试卷讲评','status':'draft_requires_page_by_page_review',
            'sources':[{'role':'paper','path':Path(paper).name,'sha256':sha256(paper)}],
            'sections':[],'unparsed':unparsed,
            'note':'机器草稿。必须逐页对照原卷：确认题型 kind、段落边界、选项、听力原文和写作范文归属；答案只采信答案原件解析表。'}
    if answers and Path(answers).is_file():
        ledger['sources'].append({'role':'answers','path':Path(answers).name,'sha256':sha256(answers)})
    for index,section in enumerate(sections):
        sid=f'S{index+1}'
        paragraphs=[{'id':f'{sid}-p{i+1}','text':text} for i,text in enumerate(section['paragraphs'])]
        questions=[]
        for q in section['questions']:
            item={'id':q['id'],'stem':q['stem']}
            if q['options']:item['options']=q['options']
            if q['id'] in table:
                item['answer']=table[q['id']];item['answer_status']='official'
                item['answer_reference']=f'answers 原件解析表第 {q["id"]} 题'
            questions.append(item)
        ledger['sections'].append({'id':sid,'kind':'reading','title':f'待确认题型 {index+1}','paragraphs':paragraphs,'questions':questions,
                                   'todo':['确认 kind 与题型标题','核对段落边界与空位（用 {{题号}} 标记）','听力补 audio 与原文','写作补题目要求与范文归属']})
    return ledger

def exam_from_ledger(ledger,title):
    data=json.loads(Path(ledger).read_text(encoding='utf-8'));exam={'title':title or data.get('title') or '英语试卷讲评','subtitle':'课堂讲评',
        'expected_question_ids':[str(q['id']) for s in data['sections'] for q in s['questions']],'sections':[]}
    todo=[]
    for section in data['sections']:
        kind=section.get('kind','reading');sid=section['id']
        paragraphs=[]
        for p in section.get('paragraphs',[]):
            paragraphs.append({'id':p['id'],'text':p['text'],'translation':''})
        questions=[]
        for q in section.get('questions',[]):
            item={'id':str(q['id']),'stem':q['stem'],'options':q.get('options',{}),'answer':q.get('answer'),
                  'answer_status':q.get('answer_status','unresolved'),'answer_source':q.get('answer_reference') or '待补：回原件核对答案来源',
                  'question_type':'','type_note':'','solve_steps':[],'pitfall':'','analysis':'','evidence':[],'distractors':{},'strategy':''}
            questions.append(item)
        section_out={'id':sid,'kind':kind,'title':section.get('title',sid),'paragraphs':paragraphs,'questions':questions,
                     'structure':[],'vocabulary':[],'sentences':[],'quick_words':[],'writing_bank':[]}
        if any(q.get('options') for q in questions):
            counts={len(q['options']) for q in questions if q.get('options')}
            if len(counts)==1:section_out['expected_option_count']=counts.pop()
        if kind=='listening':
            section_out['blanks']=[]
            todo.append(f'{sid}（听力）：写 audio 或 audio_note、逐题 audio_context 与 blanks；运行 audio.py analyze/cut')
        if kind=='writing':
            section_out['writing_steps']={'task':'','outline':[],'language':[],'model_analysis':[]}
            section_out['teacher_model']=''
            todo.append(f'{sid}（写作）：补 writing_steps、teacher_model、writing_genre')
        if kind=='seven':todo.append(f'{sid}（七选五）：每题补 logic_links，共用 shared_options')
        if kind=='grammar':todo.append(f'{sid}（语法填空）：每题补 knowledge，原文用 {{题号}} 标记空位')
        exam['sections'].append(section_out)
        todo.append(f'{sid}：补 translation / structure / sentences / vocabulary / quick_words / writing_bank，以及每题 question_type、type_note、solve_steps(≥3)、pitfall、analysis、evidence、distractors、strategy')
    return exam,todo

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('ledger');x.add_argument('--paper',required=True);x.add_argument('--answers');x.add_argument('--out',required=True);x.add_argument('--title');x.set_defaults(func=lambda a:build_ledger(a.paper,a.answers,a.title))
    x=sub.add_parser('exam');x.add_argument('--ledger',required=True);x.add_argument('--out',required=True);x.add_argument('--title');x.set_defaults(func=lambda a:exam_from_ledger(a.ledger,a.title))
    a=p.parse_args()
    try:result=a.func(a)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:sys.exit(f'ERROR: {e}')
    if a.command=='ledger':
        Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        stats={'sections':len(result['sections']),'questions':sum(len(s['questions']) for s in result['sections']),
               'unparsed_lines':len(result['unparsed']),'out':a.out,'status':result['status']}
    else:
        exam,todo=result
        Path(a.out).write_text(json.dumps(exam,ensure_ascii=False,indent=2),encoding='utf-8')
        stats={'sections':len(exam['sections']),'questions':len(exam['expected_question_ids']),'out':a.out,'todo':todo}
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__=='__main__':force_utf8();raise SystemExit(main())
