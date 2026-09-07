#!/usr/bin/env python3
"""Audit source fidelity and delivery blockers separately from HTML structure."""
import argparse,hashlib,json,re,difflib,subprocess
from pathlib import Path

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(t):return re.sub(r'\s+',' ',str(t).translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))).strip()
def answers(v):return sorted(norm(x) for x in (v if isinstance(v,list) else [v]))
def audit_exam(d,base,ledger_path=None):
    base=Path(base);issues=[]
    def add(code,location,message):issues.append({'code':code,'location':location,'message':message})
    secs=d.get('sections',[]);numeric=[int(q['id']) for s in secs for q in s.get('questions',[]) if str(q.get('id','')).isdigit()]
    if numeric!=sorted(numeric):add('question_order','sections','章节/题目顺序未按原卷题号递增；禁止按字符串排序 L1,L10,L2')
    ledger=None
    if ledger_path is None:ledger_path=base/'source-ledger.json'
    ledger_path=Path(ledger_path)
    if not ledger_path.is_file():add('source_ledger_missing','sources','缺少独立核对的 source-ledger.json；先读取原卷和答案，不能从成品反向生成台账')
    else:
        ledger=json.loads(ledger_path.read_text());sources=ledger.get('sources',[])
        if any(q.get('answer_status')=='official' for s in secs for q in s.get('questions',[])) and not any(x.get('role')=='answers' for x in sources):add('official_answer_file','sources','官方答案必须关联role=answers的原始答案文件')
        if not sources:add('source_files_missing','sources','台账必须保留原始材料路径、用途和SHA256')
        for source in sources:
            path=ledger_path.parent/source.get('path','')
            if not path.is_file() or digest(path)!=source.get('sha256'):add('source_hash',source.get('path',''),'原始材料缺失或指纹不符')
        expected=ledger.get('sections',[])
        if [s.get('id') for s in expected]!=[s.get('id') for s in secs]:add('source_section_order','sections','与源材料台账中的章节顺序或覆盖不一致')
        actual={s.get('id'):s for s in secs}
        for src in expected:
            sid=src['id'];s=actual.get(sid)
            if not s:continue
            if s.get('kind')!=src.get('kind'):add('source_kind',sid,'题型与原卷台账不符')
            pa=[norm(p.get('text','')) for p in s.get('paragraphs',[])];ps=[norm(p.get('text','')) for p in src.get('paragraphs',[])]
            if pa!=ps:add('source_paragraphs',sid,'原文内容、段落边界或写作任务与台账不符；禁止合段、漏词数要求或把范文混入原文')
            qs={str(q['id']):q for q in s.get('questions',[])}
            if list(qs)!=[str(q['id']) for q in src.get('questions',[])]:add('source_questions',sid,'题号或题目顺序与台账不符')
            for sq in src.get('questions',[]):
                qid=str(sq['id']);q=qs.get(qid)
                if not q:continue
                for field in ['stem','options']:
                    if field in sq:
                        a=q.get(field);b=sq[field]
                        same={k:norm(v) for k,v in a.items()}=={k:norm(v) for k,v in b.items()} if isinstance(a,dict) and isinstance(b,dict) else norm(a)==norm(b)
                        if not same:add('source_'+field,qid,'题干或选项与原卷台账不符')
                if 'answer' in sq and answers(q.get('answer'))!=answers(sq['answer']):add('official_answer_mismatch',qid,'答案或可接受变体与原始答案台账不一致')
                if q.get('answer_status')=='official' and ('answer' not in sq or sq.get('answer_status')!='official' or not sq.get('answer_reference')):add('answer_provenance',qid,'官方答案缺少独立原件页码/位置依据')
    for s in secs:
        sid=s['id'];kind=s['kind'];pars=s.get('paragraphs',[]);qs=s.get('questions',[])
        if kind in ['reading','seven','cloze','grammar']:
            if any('\n' in p.get('text','').strip() for p in pars):add('collapsed_paragraphs',sid,'一条paragraph含多个换行段落，无法逐段翻译或准确定位，请保留原卷真实段落')
            if len(pars)>=3 and len(s.get('structure',[]))<2:add('structure_too_generic',sid,'多段文章只有一张覆盖全文的结构卡，请分析真实段落功能和推进关系')
        for row in s.get('structure',[]):
            if re.search(r'全文共\s*\d+\s*段.{0,50}(顺序逐段|逐段精读)',row.get('analysis','')):add('structure_placeholder',sid,'篇章结构仅描述段数，未给出实际结构分析')
        for p in pars:
            text=p.get('text','')
            for q in qs:
                if kind=='grammar' and isinstance(q.get('answer'),str):
                    if re.search(r'\{\{'+re.escape(str(q['id']))+r'\}\}\s*'+re.escape(q['answer'])+r'\b',text,re.I):add('answer_leaked_in_source',str(q['id']),'原文空格后重复出现答案，回填会重复，请核对原卷')
            if kind=='writing' and (p.get('role')=='model' or len(norm(text))>60 and norm(text) in norm(s.get('teacher_model',''))):add('model_in_source',sid,'教学范文混入原卷区域，必须放teacher_model并按需展开')
        if kind=='listening':
            if len(pars)==1 and (pars[0].get('speaker')=='M/W' or re.search(r'\bM\s*:',pars[0].get('text','')) and re.search(r'\bW\s*:',pars[0].get('text',''))):add('dialogue_collapsed',sid,'多说话者对话合成一个段落，请按话轮保存说话者、原文与翻译')
            audio=base/s.get('audio','');same=[];whole_ranges=[]
            for q in qs:
                qa=base/q.get('audio','');ctx=q.get('audio_context',{})
                if audio.is_file() and qa.is_file() and digest(audio)==digest(qa):same.append(str(q['id']))
                if ctx.get('start')==0 and isinstance(ctx.get('end'),(int,float)) and abs(ctx['end']-s.get('audio_duration',-100))<.25:whole_ranges.append(str(q['id']))
                if re.search(r'教师.{0,8}(快进|拖动)|自行.{0,8}(快进|定位)',ctx.get('selection_reason','')):add('manual_audio_workaround',str(q['id']),'不能让老师自行拖动来代替逐题切割')
            if len(qs)>1 and (len(same)==len(qs) or len(whole_ranges)==len(qs)):add('question_audio_cloned',sid,'本组所有题后音频均复制整段或覆盖完整Text；文件数不证明逐题切割完成')
            alignment=s.get('audio_alignment')
            if not alignment:add('audio_alignment_missing',sid,'缺少与原音转写对应的切点、首尾原句和转写证据')
            else:
                path=base/alignment.get('transcript_file','');start=alignment.get('full_start');end=alignment.get('full_end');whole=' '.join(p.get('text','') for p in pars)
                if not path.is_file() or digest(path)!=alignment.get('transcript_sha256'):add('audio_transcript_hash',sid,'转写证据缺失或指纹不符');continue
                if not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or not 0<=start<end:add('audio_source_window',sid,'原音切点无效');continue
                try:
                    probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(audio)],capture_output=True,text=True,check=True)
                    duration=float(probe.stdout)
                except (OSError,ValueError,subprocess.CalledProcessError):add('audio_probe',sid,'无法测量实际音频时长');continue
                if abs(duration-(end-start))>.3:add('audio_source_duration',sid,'整段实际时长与原音切点不符')
                tr=json.loads(path.read_text());full=base/d.get('full_audio','')
                if not full.is_file() or tr.get('source_audio_sha256')!=digest(full):add('transcript_source_audio',sid,'转写未关联到本卷完整原音指纹')
                selected=[r for r in tr.get('segments',[]) if r.get('end',0)>start and r.get('start',0)<end]
                for key,rows in [('opening_quote',selected[:2]),('closing_quote',selected[-2:])]:
                    quote=alignment.get(key,'');spoken=' '.join(r.get('text','') for r in rows)
                    words=lambda t:re.findall('[a-z]+',t.lower())
                    a=words(quote);b=words(spoken)
                    score=max((difflib.SequenceMatcher(None,a,b[i:i+len(a)]).ratio() for i in range(max(1,len(b)-len(a)+1))),default=0)
                    if len(a)<3 or norm(quote) not in norm(whole) or score<.65:add('audio_boundary_text',sid,'首尾原句未与实际切点转写匹配：'+key)
        if kind=='writing':
            for k in ['outline','language','model_analysis']:
                if not isinstance(s.get('writing_steps',{}).get(k),list):add('writing_field_type',sid,'writing_steps.'+k+' 必须为数组')
    return {'status':'blocked' if issues else 'automated_checks_passed','delivery_status':'not_ready' if issues else 'content_and_browser_review_required','errors':issues,'source_ledger_sha256':digest(ledger_path) if ledger_path.is_file() else None,'scope':'Checks source-ledger consistency and detectable defects. Does not certify that ledger transcription or teaching reasoning is correct. Never generate the ledger from completed lesson data to bypass checks.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('exam');p.add_argument('--source-ledger');p.add_argument('--report');a=p.parse_args();path=Path(a.exam)
    try:r=audit_exam(json.loads(path.read_text()),path.parent,a.source_ledger)
    except (OSError,ValueError,KeyError,TypeError) as e:r={'status':'blocked','delivery_status':'not_ready','errors':[{'code':'invalid_audit_input','message':str(e)}]}
    text=json.dumps(r,ensure_ascii=False,indent=2)
    if a.report:Path(a.report).write_text(text)
    print(text);return 1 if r['status']=='blocked' else 0
if __name__=='__main__':raise SystemExit(main())
