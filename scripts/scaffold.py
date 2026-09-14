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
from platform_tools import explain_error,force_utf8
import section_kinds

QUESTION=re.compile(r'^\s*(\d{1,3})\s*[.、．)）]\s*(\S.*)$')
OPTION=re.compile(r'^\s*\(?([A-H])[).、．]\s*(\S.*)$')
INLINE_OPTIONS=re.compile(r'(?:(?<=^)|(?<=\s))([A-H])[.、．]\s*(.+?)(?=\s+[A-H][.、．]\s|$)')
LETTERS='ABCDEFGH'
# 试卷自己的大标题：一、听说应用(30分，共30分) / 二、语法选择(本大题共10小题，每小题1分，共10分)
HEADING=re.compile(r'^\s*([一二三四五六七八九十]+)\s*[、.．]\s*(\S.*)$')
# 页脚与卷头：九年级(上)·Unit 1 第1页(共6页)
PAGEFOOT=re.compile(r'第\s*\d+\s*页|共\s*\d+\s*页')
PAPERTITLE=re.compile(r'(年级|Unit\s*\d|测试卷|训练卷|考试卷)')
# 小标题：A. 回答问题(本题共5小题…) / B. 书面表达(本题15分)
SUBHEADING=re.compile(r'^\s*([A-E])\s*[.、．]\s*([\u4e00-\u9fff].*)$')
# 卷首说明：本卷满分120分，考试用时90分钟
PAPERINFO=re.compile(r'满分\s*([\d.]+)\s*分|考试用时\s*([\d.]+)\s*分钟|用时\s*([\d.]+)\s*分钟')
# 分值：每小题1分 / 共10分 / (30分)。"每小题"与"本题/共"要分开，别把整题分值写成每小题分值。
SCORES=re.compile(r'每小题\s*([\d.]+)\s*分|每题\s*([\d.]+)\s*分')
TOTALS=re.compile(r'共\s*([\d.]+)\s*分|[(（][^（()）]*?([\d.]+)\s*分[)）]')

def scores_of(text):
    """从试卷标题里取分值：每小题X分（per_question）与共Y分/本题Y分（total）。"""
    per=[float(value) for value in sum(SCORES.findall(text),()) if value]
    total=[float(value) for value in sum(TOTALS.findall(text),()) if value]
    return {'per_question':per[0] if per else None,'total':max(total) if total else (per[0]*0 if False else None)}

OPTION_MARKER=re.compile(r'(?:^|[\s（(])([A-H])\s*[.、．)）]\s*\S')

def is_subheading(text,match):
    """行首的 `A.~` 只有一个选项标记时才算小标题。

    "A. 图A B. 图B C. 图C" 是**选项行**（听说应用这类题的选项常这么排），
    以前会被当成小标题，把一道大题切成好几个空节。
    """
    if len(OPTION_MARKER.findall(text))>=2:return False
    body=match.group(2).strip()
    return len(body)>=2 and not re.fullmatch(r'图\s*[A-H]',body)

def heading_of(text):
    """识别试卷自己的大题标题；标题名与分值都来自试卷，不由我们指定。"""
    match=HEADING.match(text)
    if not match:return None
    rest=match.group(2).strip()
    name=re.split(r'[（(]',rest)[0].strip()
    if not name:return None
    return {'number':match.group(1),'name':name,'raw':rest,**scores_of(rest)}

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
    sections=[];current=None;unparsed=[];pending=None;ignored=[];paper_title=None;paper_info={}
    def open_section(heading=None):
        section={'questions':[],'paragraphs':[]}
        if heading:section['heading']=heading
        sections.append(section);return section
    for index,row in enumerate(lines,1):
        text=row['text'].strip()
        if not text:
            if current and current['questions'] and not current['questions'][-1]['options']:pending='options_open'
            continue
        heading=heading_of(text)
        if heading:
            # 试卷的大题标题决定题型名与板块：不再从标题往下猜"这是阅读"。
            current=open_section(heading)
            continue
        info=PAPERINFO.findall(text)
        if info and len(text)<=60:
            values=[float(x) for value in info for x in value if x]
            paper_info['full_score']=values[0] if values else None
            paper_info['minutes']=values[-1] if len(values)>1 else None
            ignored.append({'line':index,'text':text,'reason':'卷首说明，用作文档信息'})
            continue
        sub=SUBHEADING.match(text)
        if sub and is_subheading(text,sub):
            # 小标题（A. 回答问题 / B. 书面表达）另起一节，但仍归在同一个板块下。
            parent_heading=(current or {}).get('heading') or {}
            own=scores_of(text)
            # 小标题自己没写分值时，继承大题标题的"每小题 X 分"；
            # 大题的总分只在该大题只有一个节时才是这一节的总分，多节时不能挂在每个节上。
            merge_into_current=bool(current is not None and current.get('heading') and not current['questions'] and not current['paragraphs'])
            scores=dict(own)
            if not own['per_question'] and not own['total']:
                scores['per_question']=parent_heading.get('per_question')
                if merge_into_current and parent_heading.get('total') is not None:
                    scores['total']=parent_heading['total'];scores['total_inherited']=True
                else:scores['total']=None
            heading={'name':parent_heading.get('name',''),'raw':text.strip(),
                     'number':parent_heading.get('number',''),
                     'subtitle':sub.group(1)+'. '+sub.group(2).strip(),**scores}
            if merge_into_current:
                # 大题标题下紧接着第一节（如"六、读写综合"→"A. 回答问题"）：这一节就是第一节，
                # 不要再凭空多出一个空的"读写综合"节。
                current['heading']={**current['heading'],**heading}
            else:
                current=open_section(heading)
            continue
        if PAGEFOOT.search(text) and len(text)<=40:
            ignored.append({'line':index,'text':text,'reason':'页码/页脚，不是原文'})
            continue
        if paper_title is None and PAPERTITLE.search(text) and len(text)<=60:
            paper_title=text
            ignored.append({'line':index,'text':text,'reason':'卷头标题，用作文档标题'})
            continue
        match=QUESTION.match(text)
        if match:
            qid=match.group(1);stem,options=split_options(match.group(2))
            if current is None:current=open_section()
            current['questions'].append({'id':qid,'stem':stem,'options':options,'raw':text})
            continue
        option=OPTION.match(text)
        if option and current and current['questions']:
            target=current['questions'][-1]
            # "A. 图A B. 图B C. 图C" 这类续行要按 A/B/C 拆开，不能只记成 A 的长文本。
            _,inline=split_options(text)
            if len(inline)>=2:
                for letter,value in inline.items():
                    if letter in target['options'] and target['options'][letter]!=value:
                        unparsed.append({'line':index,'text':text,'reason':f"第{target['id']}题选项 {letter} 出现两次不同内容：{target['options'][letter]} / {value}"})
                    target['options'][letter]=value
                continue
            if option.group(1).upper() in target['options'] and len(target['options'])>1:unparsed.append({'line':index,'text':text,'reason':'选项重复或题干未识别'})
            target['options'][option.group(1).upper()]=option.group(2).strip()
            continue
        if current is None:current=open_section()
        elif current['questions']:current=open_section()
        current['paragraphs'].append(text)
    # 有大题标题的空节必须保留：听说应用这类题的选项是图片，文本解析不到小题，
    # 静默丢掉整道大题比留一个待核节危险得多。
    sections=[s for s in sections if s['questions'] or s['paragraphs'] or s.get('heading')]
    if paper_title:sections=[s for s in sections]
    for section in sections:
        for q in section['questions']:
            q['options']={k:v for k,v in sorted(q['options'].items())}
            if q['options'] and list(q['options'])!=list(LETTERS[:len(q['options'])]):
                unparsed.append({'line':0,'text':q['raw'],'reason':f"第{q['id']}题选项标签不连续：{list(q['options'])}"})
    return sections,unparsed,ignored,paper_title,paper_info

def section_todo(section):
    """这一节要补什么，只按它自己实际是什么来定：原卷没有的题型不生成、也不提示补全。

    "是什么"由 section_kinds.preset 判断（试卷题型名的别名 + 本节实际内容），
    所以要补音频的是听力节，要补范文的是写作节，不会互相牵连。
    """
    todo=[]
    preset=section_kinds.preset(section)
    if not section['questions']:
        todo.append('本节没有解析到小题：核对是否为图片选项、图表题或跨栏排版，按原卷补题号与题干；不要因为是"听力/阅读"就照搬别节的题')
    placeholder=sorted({letter for q in section.get('questions') or [] for letter in section_kinds.placeholder_options(q)})
    if placeholder:
        todo.append(f"本节选项 {placeholder} 看起来只是图片占位（如「图A」「图B」「图片1」）：必须用 option_images 放真实图片（构建会拦下只有占位文字的题）；"
                    f"确实拿不到图片就把该题标成待核并写进 qa-report，不要用文字冒充选项")
    if section.get('heading'):
        todo.append('核对题型名与分值是否与原卷标题一致（kind 用试卷自己的名称）')
    else:
        todo.append('确认题型名（kind）：这份大题在原卷上叫什么就写什么，不要改成预设的六种名称')
    if section['paragraphs']:
        todo.append('核对段落边界与空位（用 {{题号}} 标记），补 translation')
    if preset=='listening':todo.append('写 audio 或 audio_note、逐题 audio_context 与 blanks；运行 audio.py analyze/cut')
    elif section_kinds.has_audio(section) or section_kinds.has_audio_note(section):
        todo.append('本节带音频：确认 kind_preset（kind_preset=listening 才会显示听力工具）')
    if preset=='writing':todo.append('补 writing_steps、teacher_model、writing_genre')
    if preset=='seven':todo.append('每题补 logic_links，共用 shared_options')
    if preset=='grammar':todo.append('每题补 knowledge，原文用 {{题号}} 标记空位')
    todo.append('本节要讲的栏目按实际材料定：有原文才写 vocabulary/quick_words；两段以上再写 sentences/structure；开写作迁移才写 writing_bank')
    todo.append('每题补 question_type、type_note、solve_steps(≥3)、pitfall、analysis、evidence、distractors、strategy')
    return todo

def build_ledger(paper,answers,title):
    lines=load_blocks(paper);sections,unparsed,ignored,paper_title,paper_info=parse_questions(lines)
    table={}
    if answers and Path(answers).is_file():
        data=json.loads(Path(answers).read_text(encoding='utf-8'));table=data.get('answers',{})
    ledger={'title':title or paper_title or '英语试卷讲评','status':'draft_requires_page_by_page_review',
            'sources':[{'role':'paper','path':Path(paper).name,'sha256':sha256(paper)}],
            'sections':[],'unparsed':unparsed,'ignored_lines':ignored,'paper_info':{k:v for k,v in paper_info.items() if v},
            'note':'机器草稿。必须逐页对照原卷：确认题型 kind（用试卷自己的名称）、板块顺序、段落边界、选项、听力原文和写作范文归属；答案只采信答案原件解析表。原卷没有的题型不要补。'}
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
        heading=section.get('heading') or {}
        kind=heading.get('name') or f'待确认题型{index+1}'
        entry={'id':sid,'kind':kind,'group':kind,'group_title':kind,
               'title':heading.get('subtitle') or heading.get('raw') or kind,'paragraphs':paragraphs,'questions':questions}
        # 机器按"题型名 + 小标题"推断出的呈现方式就写进 kind_preset：宣告优先于内容推断，
        # 免得助手在写作节里只填了正文、preset 仍被推断成 custom（写作工作区与必填栏目都会丢）。
        # 推断不出来（custom）时不写，留给后面的内容推断。
        inferred=section_kinds.preset(entry)
        if inferred!='custom':entry['kind_preset']=inferred
        if heading.get('per_question') is not None:entry['score_per_question']=heading['per_question']
        derived=False
        inherited_mismatch=bool(heading.get('total_inherited') and heading.get('per_question') and questions
                                and round(heading['per_question']*len(questions),2)!=heading.get('total'))
        if inherited_mismatch:
            # 从大题继承来的总分只在这个节就是整个大题时才成立（如听说应用一节 5 题×1 分=5 分）；
            # 阅读理解底下有 A/B/C 三节时，大题的"共30分"不能挂在每一节上——按每小题×本节题数推算。
            entry['score_total']=round(heading['per_question']*len(questions),2);derived=True
        elif heading.get('total') is not None:entry['score_total']=heading['total']
        elif heading.get('per_question') and questions:
            # 原卷只给了整道大题的总分（或只给了每小题分值）：按"每小题 × 本节题数"推算，
            # 并在待办里说明这是推算值，必须对照原卷核对，不冒充原件写的数字。
            entry['score_total']=round(heading['per_question']*len(questions),2);derived=True
        entry['todo']=section_todo({'kind':kind,'paragraphs':paragraphs,'questions':questions,'heading':heading})
        if entry.get('kind_preset'):
            entry['todo'].insert(0,f"核对 kind_preset（机器按题型名与小标题推断为 {entry['kind_preset']}）：呈现方式不对就改它，名称仍用试卷自己的 kind")
        if derived:entry['todo'].append(f"本节 score_total={entry['score_total']} 是按大题标题的每小题 {heading['per_question']} 分 × 本节 {len(questions)} 题推算的（原卷只在整道大题写了总分），请对照原卷核对或删掉")
        ledger['sections'].append(entry)
    return ledger

def exam_from_ledger(ledger,title):
    data=json.loads(Path(ledger).read_text(encoding='utf-8'));exam={'title':title or data.get('title') or '英语试卷讲评','subtitle':'课堂讲评',
        'expected_question_ids':[str(q['id']) for s in data['sections'] for q in s['questions']],
        # 这里由解析结果生成，因此构建时的“无漏题”检查与解析同源、抓不到漏题；核对原卷后改成 checked。
        'expected_question_ids_source':'machine_draft','sections':[]}
    info=data.get('paper_info') or {}
    if info.get('full_score'):exam['full_score']=info['full_score']
    if info.get('minutes'):exam['exam_minutes']=info['minutes']
    kinds=[s.get('kind','?') for s in data['sections']]
    todo=['按原卷（含跨页、跨栏）独立盘点题号，确认没有漏题后把 expected_question_ids_source 改成 checked；只要还是 machine_draft，构建会阻断',
          f'本次原卷的题型只有这些：{"、".join(kinds)}；不要补原卷没有的题型，也不要因为模板里常见"听力/阅读/完形/语法填空"就照着凑']
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
        for field in ('group','group_title','score_per_question','score_total','kind_preset'):
            if section.get(field) is not None:section_out[field]=section[field]
        if any(q.get('options') for q in questions):
            counts={len(q['options']) for q in questions if q.get('options')}
            if len(counts)==1:section_out['expected_option_count']=counts.pop()
        if section_kinds.is_listening(section_out):
            section_out['blanks']=[]
        if section_kinds.preset(section_out)=='writing':
            section_out['writing_steps']={'task':'','outline':[],'language':[],'model_analysis':[]}
            section_out['teacher_model']=''
        exam['sections'].append(section_out)
        for item in (section.get('todo') or []):todo.append(f'{sid}（{kind}）：{item}')
    return exam,todo

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('ledger');x.add_argument('--paper',required=True);x.add_argument('--answers');x.add_argument('--out',required=True);x.add_argument('--title');x.set_defaults(func=lambda a:build_ledger(a.paper,a.answers,a.title))
    x=sub.add_parser('exam');x.add_argument('--ledger',required=True);x.add_argument('--out',required=True);x.add_argument('--title');x.set_defaults(func=lambda a:exam_from_ledger(a.ledger,a.title))
    a=p.parse_args()
    try:result=a.func(a)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:sys.exit(f'ERROR: {explain_error(e)}')
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
