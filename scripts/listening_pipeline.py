#!/usr/bin/env python3
"""Audio -> ASR/reuse -> group windows -> alignment -> question contexts -> reviewed cuts.
Candidates never silently become verified. All checkpoints bind to source bytes.
"""
import argparse,difflib,json,re,sys,time
from pathlib import Path
from types import SimpleNamespace
from audio import sha256,probe,cut
from bounded_command import run
from platform_tools import ffmpeg_bin
from speech_runtime import probe as runtime_probe

def save(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def tokens(text):return re.findall(r"[a-z]+(?:'[a-z]+)?|\d+",text.lower().replace('’',"'"))
def clean(text):return re.sub(r'(?m)^\s*(?:W|M|Woman|Man):\s*','',text).strip()

def group_windows(exam,transcript,duration):
    """Match original texts to ordered transcript segments, keeping first repeat and alternatives."""
    rows=transcript['segments'];groups=[];problems=[];previous=0
    for s in exam['sections']:
        from section_kinds import is_listening
        if not is_listening(s):continue
        text='\n'.join(clean(p['text']) for p in s.get('paragraphs',[]));needle=tokens(text)
        if not needle:problems.append(s['id']+' 没有原件听力文本：先核对自动转写，再建立题组');continue
        matches=[]
        for i,r in enumerate(rows):
            if r['start']<previous-.05:continue
            first=tokens(r['text'])
            if len(set(first)&set(needle[:12]))<min(2,len(needle)):continue
            joined=[]
            for j in range(i,min(len(rows),i+60)):
                joined+=tokens(rows[j]['text'])
                if len(joined)>len(needle)*1.5+15:break
                if len(joined)<len(needle)*.65:continue
                if len(set(tokens(rows[j]['text']))&set(needle[-12:]))<min(2,len(needle)):continue
                score=difflib.SequenceMatcher(None,needle,joined,autojunk=False).ratio()
                if score>=.72:matches.append((score,i,j))
        if not matches:problems.append(s['id']+' 未找到可靠窗口，需核对原文与转写；未猜测秒数');continue
        matches.sort(reverse=True);best=matches[0][0]
        # Earlier occurrence among near-equal matches gives one complete reading, not two repeats.
        near=[m for m in matches if m[0]>=best-.025];score,i,j=min(near,key=lambda m:(m[1],-m[0],m[2]))
        start=max(previous,rows[i]['start']-.3);end=min(duration,rows[j]['end']+.4)
        groups.append({'id':s['id'],'start':start,'end':end,'text':text,'score':round(score,4),'verified':False,
                       'alternatives':[{'start':rows[x]['start'],'end':rows[y]['end'],'score':round(sc,4)} for sc,x,y in matches[:4]],
                       'question_ids':[str(q['id']) for q in s.get('questions',[])]})
        previous=end
    return {'segments':groups,'issues':problems,'status':'windows_review_required'}

def question_contexts(exam,aligned):
    groups={g['id']:g for g in aligned['segments']};result=[];issues=[]
    for s in exam['sections']:
        if s['id'] not in groups:continue
        g=groups[s['id']];words=g.get('words',[])
        for q in s.get('questions',[]):
            evidence=q.get('evidence',[])
            if isinstance(evidence,dict):evidence=[evidence]
            spans=[]
            for e in evidence:
                quote=tokens(e.get('quote',''));hay=[];indexes=[]
                for k,w in enumerate(words):
                    ts=tokens(w.get('word',''));hay.extend(ts);indexes.extend([k]*len(ts))
                found=[i for i in range(len(hay)-len(quote)+1) if quote and hay[i:i+len(quote)]==quote]
                if len(found)!=1:issues.append('第 '+str(q['id'])+' 题引句未唯一匹配对齐词，需核对指代、数字或重复表达');continue
                k=found[0];spans.append((indexes[k],indexes[k+len(quote)-1]))
            if not spans:continue
            left=min(a for a,b in spans);right=max(b for a,b in spans)
            # Preserve complete sentence boundaries around the evidence, not isolated keywords.
            while left>0 and not re.search(r'[.!?]["\u201d\u2019]?$',words[left-1]['word']):left-=1
            while right+1<len(words) and not re.search(r'[.!?]["\u201d\u2019]?$',words[right]['word']):right+=1
            result.append({'id':'Q'+str(q['id']),'question_ids':[str(q['id'])],'group_id':s['id'],
                           'start':max(g['start'],words[left]['start']-.25),'end':min(g['end'],words[right]['end']+.3),
                           'context':' '.join(w['word'] for w in words[left:right+1]),'verified':False,
                           'evidence_quotes':[e.get('quote','') for e in evidence],
                           'review_prompt':'试听首尾；核对否定、因果、指代及推断所需前文，必要时扩大语境。'})
    return {'segments':result,'issues':issues,'status':'question_context_review_required'}

def execute(args):
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True);audio=Path(args.audio).resolve();source=sha256(audio)
    exam=getattr(args,'selected_exam',None) or json.loads(Path(args.exam).read_text(encoding='utf-8'));duration=probe(audio);log={'source_audio_sha256':source,'duration':duration,'stages':[]}
    def phase(name,status,**extra):
        log['stages'].append({'name':name,'status':status,**extra});save(out/'listening-run.json',log)
    phase('probe','passed')
    runtime=None
    if args.transcript:
        transcript=json.loads(Path(args.transcript).read_text(encoding='utf-8'))
        if transcript.get('source_audio_sha256')!=source:raise ValueError('已有转写不是本次原音，禁止复用')
        if not transcript.get('segments') or any(not 0<=r['start']<r['end']<=duration+.05 for r in transcript['segments']):raise ValueError('已有转写时间无效或超出原音')
        phase('transcript','reused');save(out/'transcript.json',transcript)
    else:
        runtime=runtime_probe(args.python)
        if runtime['status']!='package_ready':phase('runtime','needs_setup',detail=runtime);return log
        phase('runtime','package_ready',python=runtime['python'])
        # First prove real short-audio processing before spending a full-paper budget.
        short=out/'smoke.wav'
        code,stdout,stderr=run([ffmpeg_bin(),'-v','error','-y','-i',str(audio),'-t','25','-ar','16000','-ac','1',str(short)],45)
        if code:raise ValueError('短音频准备失败：'+stderr)
        worker=Path(__file__).with_name('speech_worker.py')
        for name,source_file,target in [('smoke',short,out/'smoke-transcript.json'),('transcript',audio,out/'transcript.json')]:
            tick=time.monotonic();cmd=[runtime['python'],str(worker),str(source_file),'--out',str(target),'--cache',args.cache,'--model',args.model]
            code,stdout,stderr=run(cmd,args.seconds)
            if code:phase(name,'failed',command=cmd,stderr=stderr,stdout=stdout);return log
            data=json.loads(target.read_text(encoding='utf-8'))
            if not data.get('segments'):phase(name,'failed',reason='未识别出有效英文，停止整卷处理');return log
            phase(name,'passed',seconds=round(time.monotonic()-tick,2))
        transcript=json.loads((out/'transcript.json').read_text(encoding='utf-8'))
    windows=json.loads(Path(args.windows).read_text(encoding='utf-8')) if getattr(args,'windows',None) else group_windows(exam,transcript,duration)
    if getattr(args,'windows',None) and windows.get('source_audio_sha256')!=source:raise ValueError('人工修订窗口属于另一份原音')
    windows['source_audio_sha256']=source;save(out/'windows.json',windows)
    phase('windows',windows['status'],issues=windows['issues'])
    if windows['issues']:return log
    runtime=runtime or runtime_probe(args.python)
    if runtime['status']!='package_ready':phase('alignment','needs_setup',detail=runtime);return log
    # align_whisperx validates every returned time and leaves review pending.
    cmd=[runtime['python'],str(Path(__file__).with_name('align_whisperx.py')),str(audio),str(out/'windows.json'),'--out',str(out/'aligned.json'),'--cache',args.cache]
    code,stdout,stderr=run(cmd,args.seconds)
    if code:phase('alignment','failed',command=cmd,stderr=stderr,stdout=stdout);return log
    aligned=json.loads((out/'aligned.json').read_text(encoding='utf-8'));phase('alignment',aligned['status'])
    questions=question_contexts(exam,aligned);save(out/'question-contexts.json',questions)
    manifest={'source_audio_sha256':source,'expected_count':len(windows['segments'])+len(questions['segments']),
              'segments':[{k:v for k,v in g.items() if k not in ('alternatives',)} for g in windows['segments']]+questions['segments'],
              'issues':questions['issues'],'expected_group_ids':[g['id'] for g in windows['segments']],'expected_question_ids':[str(q['id']) for s in exam['sections'] if s['id'] in {g['id'] for g in windows['segments']} for q in s.get('questions',[])],'status':'listening_review_required'}
    save(out/'cuts-candidates.json',manifest);phase('contexts','review_required',issues=questions['issues'])
    return log

def finalize(args):
    root=Path(args.out);manifest=json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    if manifest.get('source_audio_sha256')!=sha256(args.audio):raise ValueError('切片清单与本次原音不符')
    rows=manifest.get('segments',[])
    if set(manifest.get('expected_group_ids',[]))!={r['id'] for r in rows if not r.get('group_id')} or set(manifest.get('expected_question_ids',[]))!={str(q) for r in rows if r.get('group_id') for q in r.get('question_ids',[])}:raise ValueError('已核对清单遗漏题组或题号，不能交付完整精听')
    if not rows or manifest.get('issues'):raise ValueError('切片清单还有未解决问题，不能交付')
    for row in rows:
        if row.get('verified') is not True or len(row.get('evidence','').strip())<12:raise ValueError('片段 '+str(row.get('id'))+' 尚未记录实际试听与题意核对')
    root.mkdir(parents=True,exist_ok=True)
    import shutil
    results=[]
    for kind,subset,dest in [('text',[r for r in rows if not r.get('group_id')],root),('question',[r for r in rows if r.get('group_id')],root/'questions')]:
        if not subset:raise ValueError('缺少整段或逐题清单，不能标完整精听')
        path=root/(kind+'-reviewed.json');save(path,{'kind':kind,'expected_count':len(subset),'segments':subset})
        results.append(cut(SimpleNamespace(input=args.audio,manifest=str(path),out=str(dest),transcript=args.transcript,allow_unverified=False,resume=True,jobs=2)))
    if args.transcript:shutil.copy2(args.transcript,root/'transcript.json')
    return {'status':'cuts_verified_by_record','out':str(root),'note':'继续 build.py、浏览器播放与交付验收'}

def main():
    from platform_tools import force_utf8
    force_utf8();p=argparse.ArgumentParser();p.add_argument('command',choices=['run','cut']);p.add_argument('--audio',required=True);p.add_argument('--out',required=True);p.add_argument('--exam');p.add_argument('--plan');p.add_argument('--source-ledger');p.add_argument('--transcript');p.add_argument('--python');p.add_argument('--manifest');p.add_argument('--windows',help='核对或规范化后的同源窗口；不重新计算候选');p.add_argument('--cache',default='.listening-cache');p.add_argument('--model',default='base.en');p.add_argument('--seconds',type=float,default=600);a=p.parse_args()
    try:
        if not 0<a.seconds<=3600:raise ValueError('运行预算须为1–3600秒')
        if a.command=='run' and not a.exam:raise ValueError('请用 --exam 提供本次听力原文与题目')
        if a.command=='cut' and not a.manifest:raise ValueError('请用 --manifest 提供已试听核对的清单')
        if a.command=='run':
            if not a.plan or not a.source_ledger:raise ValueError('听力处理前请先记录老师的选择，并提供 --plan 和 --source-ledger')
            import task_contract
            from preferences import apply_plan
            from section_kinds import is_listening
            data=json.loads(Path(a.plan).read_text(encoding='utf-8'));contract=task_contract.validate(data,a.source_ledger)
            if not any(m['role']=='audio' and m['sha256']==sha256(a.audio) for m in contract['materials']):raise ValueError('原音未绑定本次已确认计划，请先核对材料')
            a.selected_exam=apply_plan(json.loads(Path(a.exam).read_text(encoding='utf-8')),data)
            a.selected_exam['sections']=[s for s in a.selected_exam['sections'] if is_listening(s)]
            if not a.selected_exam['sections']:raise ValueError('老师本次未选择听力，不启动音频处理')
        r=execute(a) if a.command=='run' else finalize(a);print(json.dumps(r,ensure_ascii=False,indent=2));return 2 if isinstance(r,dict) and any(x.get('status') in ('failed','needs_setup') for x in r.get('stages',[])) else 0
    except (OSError,ValueError,KeyError,AssertionError) as e:p.exit(1,'ERROR: '+str(e)+'\n')
if __name__=='__main__':raise SystemExit(main())
