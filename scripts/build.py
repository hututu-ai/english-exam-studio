#!/usr/bin/env python3
"""Validate canonical exam data and build a relocatable, offline lesson."""
import argparse,copy,json,re,shutil,subprocess
from pathlib import Path
from verify_output import verify_output, verify_template
from quality_gate import audit_exam
KINDS={'listening','reading','seven','cloze','grammar','writing'}

def validate(d):
    assert d.get('title') and d.get('sections'),'Missing title or sections'
    ids=set();qids=set(); warnings=[]
    for s in d['sections']:
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
        if s['kind']=='listening':assert s.get('audio'),'Listening section needs audio'
        assert s.get('questions'),'Missing questions'
        for q in s['questions']:
            assert q.get('question_type') and q.get('type_note') and len(q.get('solve_steps',[]))>=3 and q.get('pitfall'),'Incomplete question type teaching'
            if s['kind']=='listening':assert q.get('audio') and q.get('audio_context',{}).get('selection_reason'),'Listening question needs a contextual audio clip'
            if q.get('knowledge'):assert all(q['knowledge'].get(k) for k in ['title','rule','example','explanation']),'Incomplete inline knowledge card'
            q['id']=str(q['id']);assert q['id'] not in qids,'Duplicate question number';qids.add(q['id'])
            assert q.get('stem') and isinstance(q.get('options',{}),dict),'Invalid question'
            if s.get('expected_option_count'):
                assert len(q['options'])==s['expected_option_count'],f"Question {q['id']} option count mismatch"
                assert list(q['options'])==[chr(65+i) for i in range(s['expected_option_count'])],f"Question {q['id']} option labels mismatch"
            status=q.get('answer_status');assert status in {'official','inferred','sample','unresolved'},'Missing answer status'
            assert q.get('answer_source'),'Missing answer provenance'
            ans=q.get('answer'); answers=ans if isinstance(ans,list) else [ans]
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
    if d.get('expected_question_ids'):assert set(d['expected_question_ids'])==qids,'Paper question coverage mismatch'
    return {'sections':len(ids),'questions':len(qids),'warnings':warnings,'status':'structural_checks_passed','note':'Does not certify source fidelity, answer correctness, alignment or browser behavior.'}

def validate_features(d):
    """Require content backing for the teacher features, not just empty buttons."""
    checks=[]
    for s in d['sections']:
        sid=s['id'];kind=s['kind']
        required=['quick_words','vocabulary']
        if kind in {'reading','seven','cloze','grammar'}:
            required+=['sentences','structure','writing_bank']
        if kind=='listening':required+=['blanks']
        if kind=='writing':required+=['writing_steps','teacher_model']
        for key in required:
            assert s.get(key),f'{sid}: missing feature content {key}; complete it before delivery'
        if kind!='writing':
            assert any(p.get('translation') for p in s['paragraphs']),f'{sid}: missing paragraph translations'
        for q in s['questions']:
            assert q.get('strategy'),f'{sid}/{q["id"]}: missing method transfer'
            if kind=='seven':assert q.get('logic_links'),f'{sid}/{q["id"]}: missing visual logic links'
            if kind=='grammar':assert q.get('knowledge'),f'{sid}/{q["id"]}: missing inline grammar knowledge'
        if kind=='writing':
            for key in ['task','outline','language','model_analysis']:
                assert s['writing_steps'].get(key),f'{sid}: missing writing guidance {key}'
        checks.append({'section':sid,'kind':kind,'required_content':required,'status':'passed'})
    return {'status':'passed','sections':checks,'scope':'Required feature data present; human review still needed for teaching quality and source fidelity.'}

def build(src,out,source_ledger=None):
    src=Path(src).resolve();out=Path(out).resolve();original=json.loads(src.read_text(encoding='utf-8'));d=copy.deepcopy(original)
    for section in d.get('sections',[]):
        if section.get('kind')=='writing':section['teacher_model_word_count']=len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*",section.get('teacher_model','')))
    report=validate(d);report['feature_coverage']=validate_features(d);report['quality_gate']=audit_exam(d,src.parent,source_ledger)
    if report['quality_gate']['status']=='blocked':
        details='; '.join(x['location']+': '+x['code'] for x in report['quality_gate']['errors'])
        raise ValueError('Delivery blocked: '+details+'; run scripts/quality_gate.py INPUT --source-ledger LEDGER --report quality-report.json for details')
    report['delivery_status']='content_and_browser_review_required'
    verify_template(Path(__file__).resolve().parents[1]);resources=[]
    assets=Path(__file__).resolve().parents[1]/'assets'
    for key,filename in [('dictionary','offline-dictionary.json'),('legacy_dictionary','legacy-dictionary.json')]:
        if key not in d and (assets/filename).exists():d[key]=json.loads((assets/filename).read_text())
    def source_path(value):
        assert not re.match(r'^[a-zA-Z]+://',value),'Use local resource files'
        path=(src.parent/value).resolve();assert path.is_file(),f'Missing media: {value}';return path
    planned=[]
    def media(obj,key,folder,stem):
        if not obj.get(key):return
        source=source_path(obj[key]);name=f'{folder}/{stem}{source.suffix.lower()}'
        planned.append((source,name));obj[key]=name;resources.append(name)
    media(d,'full_audio','audio','full')
    for s in d['sections']:
        media(s,'audio','audio',s['id'])
        if s.get('audio'):
            source=next(x for x,n in planned if n==s['audio'])
            r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(source)],text=True,capture_output=True,check=True)
            dur=float(r.stdout);s['audio_duration']=dur
            for q in s['questions']:
                for ev in q.get('evidence',[]):
                    if 'end' in ev:assert ev['end']<=dur+0.05,'Audio evidence exceeds clip duration'
        for q in s['questions']:
            if q.get('audio'):
                media(q,'audio','audio','Q'+q['id'])
                qsource=next(x for x,n in planned if n==q['audio'])
                r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(qsource)],text=True,capture_output=True,check=True)
                q['audio_duration']=float(r.stdout)
                context=q.get('audio_context',{})
                assert s['kind']=='listening' and 0<=context.get('start',-1)<context.get('end',-1)<=s['audio_duration']+0.1,'Invalid question audio context'
                assert abs(q['audio_duration']-(context['end']-context['start']))<0.25,'Question audio duration mismatch'
        if s.get('origin'):media(s['origin'],'page_image','sources',s['id']+'-paper')
        for par in s['paragraphs']:media(par,'image','assets',s['id']+'-'+par['id'])
    # Complete validation before creating output.
    out.mkdir(parents=True,exist_ok=True)
    if (assets/'ECDICT-LICENSE.txt').exists():shutil.copy2(assets/'ECDICT-LICENSE.txt',out/'ECDICT-LICENSE.txt')
    for source,name in planned:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
        if source!=target:shutil.copy2(source,target)
    payload=json.dumps(d,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    template=(Path(__file__).resolve().parents[1]/'assets'/'lesson.html').read_text()
    assert template.count('__EXAM_DATA__')==1,'Invalid template token'
    (out/'index.html').write_text(template.replace('__EXAM_DATA__',payload),encoding='utf-8')
    (out/'exam.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    report['template_verification']=verify_output(out,Path(__file__).resolve().parents[1])
    report['resources']=resources
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('out');p.add_argument('--source-ledger');a=p.parse_args()
    try:build(a.input,a.out,a.source_ledger)
    except (AssertionError,ValueError,KeyError,FileNotFoundError,subprocess.CalledProcessError) as e:p.exit(1,f'ERROR: {e}\n')
