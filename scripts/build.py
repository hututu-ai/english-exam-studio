#!/usr/bin/env python3
"""Validate canonical exam data and build a relocatable, offline lesson.

Audio is wired automatically from an audio bundle (audio.py output) so no one has to keep the
file names in sync by hand: --audio-bundle DIR, or auto-detected audio-work / audio-out.
"""
import argparse,base64,copy,json,re,shutil,subprocess,time,mimetypes
from pathlib import Path
from audio_wiring import bundle_dir, wire_audio
from verify_output import verify_output, verify_template
from quality_gate import audit_exam
from answer_audit import audit as answer_audit
from platform_tools import force_utf8, find_tool
from scope import select
KINDS={'listening','reading','seven','cloze','grammar','writing'}

def validate_section(s,ids,warnings,problems,qids):
    """One section, all checks; isolated so every problem can be reported in a single pass."""
    sid=s.get('id','?')
    assert re.fullmatch(r'[A-Za-z0-9_-]+',s['id']) and s['id'] not in ids,'Invalid/duplicate section ID';ids.add(s['id'])
    assert s['kind'] in KINDS and s.get('title'),'Unknown kind or missing section title'
    pars={}
    for p in s.get('paragraphs',[]):
        assert re.fullmatch(r'[A-Za-z0-9_-]+',p['id']) and p['id'] not in pars,'Invalid/duplicate paragraph ID'
        assert isinstance(p.get('text'),str),'Missing paragraph text';pars[p['id']]=p
    assert pars,'Missing source text'
    if s.get('source_groups'):
        grouped=[pid for group in s['source_groups'] for pid in group['paragraph_ids']]
        assert grouped==list(pars),'Reading groups must preserve all source paragraphs in order'
    for w in s.get('quick_words',[]):
        assert w.get('meaning') and w.get('word'),'Missing quick word or meaning'
        assert w.get('paragraph_id') in pars and w['word'].lower() in pars[w['paragraph_id']]['text'].lower(),'Quick word must use the actual source form'
        actual=len(re.findall(r'\b'+re.escape(w['word'])+r'\b',' '.join(p['text'] for p in pars.values()),re.I))
        assert w.get('occurrences')==actual,'Quick word count must match this section'
    if s.get('origin'):
        origin=s['origin']
        assert isinstance(origin.get('exam_page'),int) and origin['exam_page']>0 and origin.get('page_image'),'Missing source page image or page number'
        for link in origin.get('links',[]):
            assert re.match(r'^https?://',link.get('url','')) and link.get('relation'),'Source link must state its relation to the paper'
    for item in s.get('writing_bank',[]):
        assert item.get('paragraph_id') in pars and item.get('quote') in pars[item['paragraph_id']]['text'],'Writing-bank quote absent from source'
        assert all(item.get(k) for k in ['category','why','frame','scene','example','check']),'Incomplete writing transfer'
    for item in s.get('logic_steps',[]):
        assert item.get('paragraph_id') in pars and item.get('quote') in pars[item['paragraph_id']]['text'],'Logic quote absent from source'
    for item in s.get('inquiry',[]):
        assert item.get('question') and item.get('answer') and item.get('paragraph_id') in pars,'Invalid teaching inquiry'
    for item in s.get('transfer_tasks',[]):
        assert item.get('paragraph_id') in pars and item.get('source_quote') in pars[item['paragraph_id']]['text'] and item.get('prompt') and item.get('check'),'Invalid transfer source or instructions'
    for item in s.get('writing_steps',{}).get('model_analysis',[]):
        assert item.get('quote') and item['quote'] in s.get('teacher_model','') and item.get('analysis'),'Writing analysis must quote the actual model'
    ranges={}
    for b in s.get('blanks',[]):
        assert b['paragraph_id'] in pars,'Unknown blank paragraph'
        assert b.get('purpose') and b.get('question_ids') and all(str(qid) in [str(q['id']) for q in s['questions']] for qid in b['question_ids']),'Blank needs a teaching purpose and valid question links'
        assert isinstance(b['start'],int) and isinstance(b['end'],int) and 0<=b['start']<b['end']<=len(pars[b['paragraph_id']]['text']),'Invalid blank offsets'
        seen=ranges.setdefault(b['paragraph_id'],[])
        assert not any(b['start']<end and b['end']>start for start,end in seen),'Overlapping blanks';seen.append((b['start'],b['end']))
    if s['kind']=='listening':
        if not (s.get('audio') or s.get('audio_note')):problems.append(f'{sid}: 听力章节必须有音频或明确的缺音频说明（见 SKILL.md 三档降级）')
        if s.get('audio_note') and not s.get('audio'):warnings.append(f"{s['id']} 未提供音频：{s['audio_note']}")
    if not s.get('questions'):problems.append(f'{sid}: Missing questions')
    for q in (s.get('questions') or []):
        try:
            assert q.get('question_type') and q.get('type_note') and len(q.get('solve_steps',[]))>=3 and q.get('pitfall'),'Incomplete question type teaching'
            if q.get('audio'):
                assert s['kind']=='listening' and q.get('audio_context',{}).get('selection_reason'),'Question audio needs a section, a context and a selection reason'
            if q.get('knowledge'):assert all(q['knowledge'].get(k) for k in ['title','rule','example','explanation']),'Incomplete inline knowledge card'
            q['id']=str(q['id']);assert re.fullmatch(r'[A-Za-z0-9_-]+',q['id']),'Invalid question ID';assert q['id'] not in qids,'Duplicate question number';qids.add(q['id'])
            assert q.get('stem') and isinstance(q.get('options',{}),dict),'Invalid question'
            if s.get('expected_option_count'):
                assert len(q['options'])==s['expected_option_count'],f"Question {q['id']} option count mismatch"
                assert list(q['options'])==[chr(65+i) for i in range(s['expected_option_count'])],f"Question {q['id']} option labels mismatch"
            status=q.get('answer_status');assert status in {'official','inferred','sample','unresolved'},'Missing answer status'
            assert q.get('answer_source'),'Missing answer provenance'
            ans=q.get('answer');answers=ans if isinstance(ans,list) else [ans]
            if status!='unresolved':assert ans is not None and ans!='' and ans!=[],'Missing answer'
            if q.get('options') and ans is not None:assert all(x in q['options'] for x in answers),'Answer absent from options'
            if status=='unresolved':warnings.append(f"Question {q['id']} unresolved")
            assert q.get('analysis'),'Missing explanation'
            if q.get('options') and status!='unresolved':
                assert q.get('evidence'),'Objective item missing evidence'
                assert all(k in q.get('distractors',{}) for k in q['options'] if k not in answers),'Missing distractor explanations'
            for link in q.get('logic_links',[]):
                assert s['kind']=='seven','Logic links require a sentence-selection section'
                assert link.get('color') in ['amber','violet','teal','blue'] and link.get('label') and link.get('explanation'),'Invalid logic link label or color'
                ends=link.get('endpoints',[])
                assert len(ends)>=2 and any('option' in e for e in ends) and any('paragraph_id' in e for e in ends),'Logic links must connect original and option'
                for endpoint in ends:
                    assert ('option' in endpoint)!=('paragraph_id' in endpoint),'Ambiguous logic endpoint'
                    text=q.get('options',{}).get(endpoint.get('option'),'') if 'option' in endpoint else pars.get(endpoint.get('paragraph_id'),{}).get('text','')
                    assert endpoint.get('quote') and endpoint['quote'] in text,'Logic link quote absent from source'
            for ev in q.get('evidence',[]):
                assert ev['paragraph_id'] in pars,'Unknown evidence paragraph'
                assert ev.get('quote') and ev['quote'] in pars[ev['paragraph_id']]['text'],'Evidence quote absent from source'
                if 'start' in ev or 'end' in ev:assert s.get('audio') and 0<=ev['start']<ev['end'],'Invalid audio evidence timing'
        except (AssertionError,KeyError,TypeError,IndexError,AttributeError,ValueError) as error:
            problems.append(f"{sid}/{q.get('id','?') if isinstance(q,dict) else '?'}: {error}")
    for v in s.get('vocabulary',[]):
        assert v.get('word') and v.get('meaning'),'Invalid vocabulary'
        if v.get('paragraph_id'):assert v['paragraph_id'] in pars and v['word'].lower() in pars[v['paragraph_id']]['text'].lower(),'Vocabulary not in source paragraph'
    for item in s.get('structure',[]):assert all(i in pars for i in item['paragraph_ids']),'Unknown structure paragraph'
    for sentence in s.get('sentences',[]):
        assert sentence['paragraph_id'] in pars and sentence['quote'] in pars[sentence['paragraph_id']]['text'],'Sentence source absent'
    for p in pars.values():
        for u in p.get('underlines',[]):assert u in p['text'],'Underline source absent'
        for gap in re.findall(r'\{\{(\d+)\}\}',p['text']):
            assert gap in [q['id'] for q in s['questions']],'Gap has no question'

def validate(d):
    if not (d.get('title') and d.get('sections')):raise ValueError('缺少 title 或 sections')
    problems=[];warnings=[];ids=set();declared=set()
    for s in d['sections']:
        for q in s.get('questions',[]) or []:
            if isinstance(q,dict) and q.get('id') is not None:declared.add(str(q['id']))
    qids=set();paragraph_ids=set()
    for s in d['sections']:
        for par in s.get('paragraphs',[]):
            pid=par.get('id')
            if pid in paragraph_ids:problems.append('Duplicate paragraph ID across sections: '+str(pid))
            paragraph_ids.add(pid)
        try:validate_section(s,ids,warnings,problems,qids)
        except (AssertionError,KeyError,TypeError,IndexError,ValueError) as error:
            problems.append(f"{s.get('id','?')}: {error}")
    if d.get('expected_question_ids'):
        expected={str(x) for x in d['expected_question_ids']}
        if expected!=declared:
            missing=sorted(expected-declared);extra=sorted(declared-expected)
            problems.append(f"sections: 题号覆盖不一致（缺 {missing or '无'}，多 {extra or '无'}）")
    if problems:
        raise ValueError(f'共 {len(problems)} 处问题，一次改完再重跑：\n- '+ '\n- '.join(str(x) for x in problems))
    return {'sections':len(ids),'questions':len(declared),'warnings':warnings,'status':'structural_checks_passed','note':'Does not certify source fidelity, answer correctness, alignment or browser behavior.'}

def validate_features(d,profile='full',selection='all',mode='lesson',audio_mode='embedded'):
    """Require content backing for the teacher features, not just empty buttons.

    profile=full  : 现有要求，精读项（句子精讲、篇章结构、写作积累）齐全
    profile=quick : 先保讲课必需项（逐题解析、答案证据、听力挖空、证据段译文），精读项可后补
    """
    quick=profile=='quick';checks=[];enrichment=[]
    for s in d['sections']:
        sid=s['id'];kind=s['kind']
        required=['blanks'] if kind=='listening' else []
        if kind=='writing':required+=['writing_steps','teacher_model']
        if quick:
            assert s.get('quick_words') or s.get('vocabulary'),f'{sid}: 快速档也要求生词速查或重点词汇至少一项'
            evidence_paragraphs={e.get('paragraph_id') for q in s['questions'] for e in q.get('evidence',[]) if e.get('paragraph_id')}
            missing_translation=[pid for pid in sorted(evidence_paragraphs) if not next((p.get('translation') for p in s['paragraphs'] if p['id']==pid),'')]
            assert not missing_translation,f'{sid}: 快速档也要求证据段落有译文：{missing_translation}'
            enrichment+=[{'section':sid,'missing':key} for key in ['sentences','structure','writing_bank'] if not s.get(key)]
        else:
            required+=['quick_words','vocabulary']
            if kind in {'reading','seven','cloze','grammar'}:required+=['sentences','structure','writing_bank']
        for key in required:
            assert s.get(key),f'{sid}: missing feature content {key}; complete it before delivery'
        if kind!='writing' and not quick:
            assert any(p.get('translation') for p in s['paragraphs']),f'{sid}: missing paragraph translations'
        for q in s['questions']:
            assert q.get('strategy'),f'{sid}/{q["id"]}: missing method transfer'
            if kind=='seven':assert q.get('logic_links'),f'{sid}/{q["id"]}: missing visual logic links'
            if kind=='grammar':assert q.get('knowledge'),f'{sid}/{q["id"]}: missing inline grammar knowledge'
        if kind=='writing':
            for key in ['task','outline','language','model_analysis']:
                assert s['writing_steps'].get(key),f'{sid}: missing writing guidance {key}'
        checks.append({'section':sid,'kind':kind,'required_content':required,'status':'passed'})
    return {'status':'passed','profile':profile,'sections':checks,'missing_enrichment':enrichment,
            'scope':'Required feature data present; human review still needed for teaching quality and source fidelity.'}

def build(src,out,source_ledger=None,audio_bundle=None,answer_key=None,profile='full',selection='all',mode=None,audio_mode='embedded'):
    src=Path(src).resolve();out=Path(out).resolve();original=json.loads(src.read_text(encoding='utf-8'));d=select(original,selection,mode)
    started=time.perf_counter()
    for section in d.get('sections',[]):
        if section.get('kind')=='writing':section['teacher_model_word_count']=len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*",section.get('teacher_model','')))
    directory=bundle_dir(src.parent,audio_bundle) if any(s['kind']=='listening' for s in d['sections']) else None
    audio_report=wire_audio(d,src.parent,directory)
    report=validate(d);report['generation_scope']=d['generation_scope'];report['feature_coverage']=validate_features(d,profile);report['profile']=profile
    ledger_path=source_ledger or (str(src.parent/'source-ledger.json') if (src.parent/'source-ledger.json').is_file() else None)
    key_path=answer_key
    if key_path is None:
        for candidate in [src.parent/'answers.json',(src.parent/'answers')/'answers.json']:
            if candidate.is_file():key_path=str(candidate);break
    report['quality_gate']=audit_exam(d,src.parent,ledger_path,key_path)
    if report['quality_gate']['status']=='blocked':
        details='; '.join(x['location']+': '+x['code'] for x in report['quality_gate']['errors'])
        raise ValueError('Delivery blocked: '+details+'; run scripts/quality_gate.py INPUT --source-ledger LEDGER --report quality-report.json for details')
    report['answer_audit']=answer_audit(d,ledger_path,key_path)
    if report['answer_audit']['status']=='blocked':
        details='; '.join(x['question']+': '+x['code'] for x in report['answer_audit']['blocking'])
        raise ValueError('答案审计未通过: '+details+'；回原件核对后再构建')
    report['audio']=audio_report
    report['pending_items']=sorted(set(audio_report['pending']+[x['location']+'：'+x['message'] for x in report['quality_gate'].get('warnings',[])]+[f"第{x['question']}题：{x['message']}" for x in report['answer_audit']['review']]))
    report['delivery_status']='quick_profile_content_and_browser_review_required' if profile=='quick' else 'content_and_browser_review_required'
    if profile=='quick' and report['feature_coverage']['missing_enrichment']:
        report['pending_items']=sorted(set(report.get('pending_items',[])+['快速档：部分精读项未生成，详见 missing_enrichment，补齐后跑 --profile full 重新构建']))
    verify_template(Path(__file__).resolve().parents[1]);resources=[]
    assets=Path(__file__).resolve().parents[1]/'assets'
    for key,filename in [('dictionary','offline-dictionary.json'),('legacy_dictionary','legacy-dictionary.json')]:
        if key not in d and (assets/filename).exists():d[key]=json.loads((assets/filename).read_text(encoding='utf-8'))
    def source_path(value):
        assert not re.match(r'^[a-zA-Z]+://',value),'Use local resource files'
        path=(src.parent/value).resolve();assert path.is_file(),f'Missing media: {value}';return path
    planned=[]
    audio_sources={}
    def media(obj,key,folder,stem):
        if not obj.get(key):return
        source=source_path(obj[key]);name=f'{folder}/{stem}{source.suffix.lower()}'
        if folder=='audio':
            if source in audio_sources:obj[key]=audio_sources[source];return
            audio_sources[source]=name
        planned.append((source,name));obj[key]=name;resources.append(name)
    probe_cache={}
    def duration_of(source,required=True):
        key=str(source.resolve())
        if key in probe_cache:return probe_cache[key]
        exe=find_tool('ffprobe')
        if not exe:
            if required:raise ValueError('验证分段时长需要 ffprobe；未分段原音可不依赖 ffprobe')
            return 0
        result=subprocess.run([exe,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',key],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,check=True)
        probe_cache[key]=float(result.stdout);return probe_cache[key]
    media(d,'full_audio','audio','full')
    for s in d['sections']:
        media(s,'audio','audio',s['id'])
        if s.get('audio'):
            source=next(x for x,n in planned if n==s['audio'])
            dur=duration_of(source,s.get('audio_scope')!='full_paper');s['audio_duration']=dur
            for q in s['questions']:
                for ev in q.get('evidence',[]):
                    if 'end' in ev:assert ev['end']<=dur+0.05,'Audio evidence exceeds clip duration'
        for q in s['questions']:
            if q.get('audio'):
                media(q,'audio','audio','Q'+q['id'])
                qsource=next(x for x,n in planned if n==q['audio'])
                q['audio_duration']=duration_of(qsource)
                context=q.get('audio_context',{})
                assert s['kind']=='listening' and 0<=context.get('start',-1)<context.get('end',-1)<=s['audio_duration']+0.1,'Invalid question audio context'
                assert abs(q['audio_duration']-(context['end']-context['start']))<0.25,'Question audio duration mismatch'
        if s.get('origin'):media(s['origin'],'page_image','sources',s['id']+'-paper')
        for par in s['paragraphs']:media(par,'image','assets',s['id']+'-'+par['id'])
    for section in d['sections']:
        alignment=section.get('audio_alignment',{})
        if alignment.get('transcript_file'):
            media(alignment,'transcript_file','verification',section['id']+'-transcript')
    # Complete validation before creating output.
    out.mkdir(parents=True,exist_ok=True)
    if (assets/'ECDICT-LICENSE.txt').exists():shutil.copy2(assets/'ECDICT-LICENSE.txt',out/'ECDICT-LICENSE.txt')
    for source,name in planned:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
        if source!=target:shutil.copy2(source,target)
    embedded={}
    for source,name in planned:
        if name.startswith('audio/') and audio_mode=='embedded':
            mime=mimetypes.guess_type(name)[0] or 'audio/mpeg'
            embedded[name]='data:'+mime+';base64,'+base64.b64encode(source.read_bytes()).decode('ascii')
    d['audio_delivery']={'mode':audio_mode,'embedded_count':len(embedded),'external_audio_count':sum(n.startswith('audio/') for _,n in planned)}
    html_data={**d,'_embedded_audio':embedded}
    payload=json.dumps(html_data,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    template=(Path(__file__).resolve().parents[1]/'assets'/'lesson.html').read_text(encoding='utf-8')
    assert template.count('__EXAM_DATA__')==1,'Invalid template token'
    (out/'index.html').write_text(template.replace('__EXAM_DATA__',payload),encoding='utf-8')
    shutil.copy2(assets/'open-guide.html',out/'打开课件.html')
    (out/'exam.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    report['template_verification']=verify_output(out,Path(__file__).resolve().parents[1])
    report['resources']=resources
    report['audio_embedded']=bool(embedded)
    report['audio_delivery']=d['audio_delivery']
    report['elapsed_seconds']=round(time.perf_counter()-started,3)
    report['browser_playback']='not_tested_by_builder'
    (out/'answer-audit.json').write_text(json.dumps(report['answer_audit'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('out')
    p.add_argument('--source-ledger');p.add_argument('--audio-bundle');p.add_argument('--answer-key')
    p.add_argument('--profile',choices=['full','quick'],default='full',help='quick=先出可上课版，精读项后补')
    p.add_argument('--sections',default='all',help='all 或逗号分隔的题型/章节ID，如 reading,A,L6')
    p.add_argument('--mode',choices=['lesson','intensive'])
    p.add_argument('--audio-mode',choices=['embedded','folder'],default='embedded')
    a=p.parse_args()
    try:build(a.input,a.out,a.source_ledger,a.audio_bundle,a.answer_key,a.profile,a.sections,a.mode,a.audio_mode)
    except (AssertionError,ValueError,KeyError,FileNotFoundError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:p.exit(1,f'ERROR: {e}\n')
