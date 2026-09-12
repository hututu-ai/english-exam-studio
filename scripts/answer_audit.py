#!/usr/bin/env python3
"""Per-question answer audit: what is provable from the source, and what a teacher must re-check.

Blocks on traceable facts (answer key disagreement, evidence quote not in the source, answer not in
its own options). Puts judgement calls in review[] instead of pretending they are verified."""
import argparse,json,re,sys
from pathlib import Path
from platform_tools import force_utf8

STOPWORDS={'the','a','an','of','to','in','on','at','for','and','or','but','is','are','was','were','be','been',
           'it','its','this','that','these','those','with','by','as','from','he','she','they','we','you','i',
           'not','no','do','does','did','will','would','can','could','should','has','have','had','there','here'}

def norm(t):
    return re.sub(r'\s+',' ',str(t).translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))).strip()

def words(t):
    return re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*",str(t).lower())

def content(t):
    return {w for w in words(t) if w not in STOPWORDS and len(w)>3}

def answers_of(q):
    a=q.get('answer')
    return [x for x in (a if isinstance(a,list) else [a]) if x not in (None,'')]

def audit(exam,ledger=None,answer_key=None):
    blocking=[];review=[]
    counts={'questions':0,'objective':0,'subjective':0,'official':0,'inferred':0,'sample':0,'unresolved':0}
    def block(code,question,message):blocking.append({'code':code,'question':question,'message':message})
    def flag(code,question,message):review.append({'code':code,'question':question,'message':message})
    key={}
    if answer_key:
        data=json.loads(Path(answer_key).read_text());key=data.get('answers',data)
        key={str(k):str(v).strip().upper() for k,v in key.items()}
    ledger_questions={}
    if ledger:
        for section in json.loads(Path(ledger).read_text()).get('sections',[]):
            for q in section.get('questions',[]):ledger_questions[str(q['id'])]=q
    for section in exam.get('sections',[]):
        sid=section['id'];kind=section['kind']
        options_seen={}
        for q in section.get('questions',[]):
            qid=str(q['id']);counts['questions']+=1
            status=q.get('answer_status','unresolved')
            counts[status if status in counts else 'unresolved']+=1
            options=q.get('options') or {};answer=answers_of(q);subjective=not options
            counts['subjective' if subjective else 'objective']+=1
            if not answer and status!='unresolved':block('answer_missing',qid,'非 unresolved 的题必须有答案')
            if options and answer:
                unknown=[a for a in answer if a not in options]
                if unknown:block('answer_not_in_options',qid,f'答案 {unknown} 不在选项里')
                for a in answer:options_seen[a]=options_seen.get(a,0)+1
            if options and status!='unresolved' and not q.get('evidence'):
                block('evidence_missing',qid,'客观题缺少可定位的原文/音频证据')
            for item in q.get('evidence',[]):
                paragraph=next((p for p in section.get('paragraphs',[]) if p['id']==item.get('paragraph_id')),None)
                if paragraph is None:block('evidence_paragraph_unknown',qid,f"证据段 {item.get('paragraph_id')} 不存在")
                elif item.get('quote') and norm(item['quote']) not in norm(paragraph.get('text','')):
                    block('evidence_quote_absent',qid,'证据引句在原段中找不到，回原件核对')
            if options and answer and section.get('kind') in {'reading','listening','seven','cloze'}:
                option_text=' '.join(str(options.get(a,'')) for a in answer)
                evidence_text=' '.join(str(e.get('quote','')) for e in q.get('evidence',[]))
                wanted=content(option_text);hit=wanted&content(evidence_text)
                if len(wanted)>=2 and not hit:
                    flag('evidence_option_low_overlap',qid,f'正确选项与证据句没有共同实词（{sorted(wanted)[:4]}）：要么答案错，要么证据不是依据句')
            if kind=='cloze' and answer and len(' '.join(str(options.get(a,'')) for a in answer).split())>3:
                flag('cloze_answer_too_long',qid,'完形答案超过三个词，复核是否抄错选项')
            if kind=='grammar' and answer:
                for a in answer:
                    if isinstance(a,str) and re.search(r'[。，；：]{2,}',a):flag('grammar_answer_suspicious',qid,'语法填空答案含多余标点')
            if status=='official':
                reference=str(q.get('answer_source',''))
                if not re.search(r'页|第|p\.|P\.|page|行|答案',reference):flag('answer_source_vague',qid,f'官方答案来源过于笼统（{reference or "空"}），写明原件页码/位置')
                if key:
                    letters=re.findall(r'[A-H]',str(q.get('answer','')).upper())
                    expected=key.get(qid)
                    if expected is None:flag('answer_key_missing',qid,'答案原件解析表里没有这一题')
                    elif letters and ''.join(letters)!=expected and expected not in [str(a).upper() for a in answer]:
                        block('answer_key_mismatch',qid,f'答案原件解析为 {expected}，成品写 {answer}')
                if qid in ledger_questions:
                    lq=ledger_questions[qid]
                    if 'answer' in lq and [str(x).upper() for x in answers_of(lq)]!=[str(x).upper() for x in answer]:
                        block('ledger_answer_mismatch',qid,'exam.json 与 source-ledger.json 答案不一致')
                    if norm(lq.get('stem',''))!=norm(q.get('stem','')):flag('ledger_stem_drift',qid,'题干与台账不一致')
        if kind=='cloze' and options_seen and len(section['questions'])>=10:
            top=max(options_seen.values())
            if top/len(section['questions'])>0.45:flag('answer_distribution_skew',sid,f'完形答案 {list(options_seen.items())} 过于集中，回原件逐题核对')
    status='blocked' if blocking else ('review_required' if review else 'answer_checks_passed')
    return {'status':status,'counts':counts,'blocking':blocking,'review':review,
            'answer_key_used':str(answer_key) if answer_key else None,
            'scope':'逐题检查答案可追溯性、证据引句与选项一致性。不替代教师对语义、篇章与主观题评分标准的判断。'}

def main():
    p=argparse.ArgumentParser();p.add_argument('exam');p.add_argument('--ledger');p.add_argument('--answer-key');p.add_argument('--report')
    a=p.parse_args()
    try:result=audit(json.loads(Path(a.exam).read_text()),a.ledger,a.answer_key)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:sys.exit(f'ERROR: {e}')
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.report:Path(a.report).write_text(text,encoding='utf-8')
    print(text)
    return 1 if result['status']=='blocked' else 0

if __name__=='__main__':force_utf8();raise SystemExit(main())
