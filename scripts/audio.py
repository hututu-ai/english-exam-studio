#!/usr/bin/env python3
"""Analyze listening audio and cut verified semantic segments; Python stdlib only."""
import argparse,json,os,re,subprocess,tempfile
from pathlib import Path

def run(args):
    r=subprocess.run(list(map(str,args)),capture_output=True,text=True)
    if r.returncode: raise ValueError(r.stderr[-2500:])
    return r.stdout

def duration(path):
    return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',path]))

def dump(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def transcript(data):
    if 'segments' in data: rows=data['segments']
    elif 'transcription' in data:
        rows=[{'start':x['offsets']['from']/1000,'end':x['offsets']['to']/1000,'text':x['text']} for x in data['transcription']]
    else: raise ValueError('Transcript needs segments or whisper.cpp transcription')
    prev=-1
    for s in rows:
        assert isinstance(s['text'],str) and 0<=s['start']<s['end'] and s['start']>=prev,'Invalid transcript time'
        prev=s['start']
    return rows

def analyze(a):
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    d=duration(a.input)
    r=subprocess.run(['ffmpeg','-hide_banner','-i',a.input,'-af','silencedetect=n=-35dB:d=0.6','-f','null','-'],capture_output=True,text=True)
    if r.returncode: raise ValueError(r.stderr[-2000:])
    sil=[]; start=None
    for line in r.stderr.splitlines():
        m=re.search(r'silence_start: ([\d.]+)',line)
        if m:start=float(m[1])
        m=re.search(r'silence_end: ([\d.]+)',line)
        if m and start is not None:sil.append({'start':start,'end':float(m[1])});start=None
    dump(out/'silences.json',sil)
    if a.transcript: rows=transcript(json.loads(Path(a.transcript).read_text()))
    else:
        model=a.model or os.environ.get('WHISPER_MODEL')
        if not model or not Path(model).is_file():raise ValueError('Supply --model LOCAL_MODEL or --transcript TIMED_JSON')
        wav=out/'asr.wav'
        run(['ffmpeg','-y','-v','error','-i',a.input,'-vn','-ar','16000','-ac','1',wav])
        run(['whisper-cli','-m',model,'-f',wav,'-l',a.language,'-oj','-of',out/'whisper','-np'])
        rows=transcript(json.loads((out/'whisper.json').read_text()))
    assert all(x['end']<=d+0.5 for x in rows),'Transcript exceeds source duration'
    dump(out/'transcript.json',{'segments':rows})
    names={x:i+1 for i,x in enumerate('one two three four five six seven eight nine ten eleven twelve'.split())}
    candidates=[]
    for s in rows:
        for m in re.finditer(r'\btext\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b|第\s*(\d+)\s*段',s['text'],re.I):
            v=m[1] or m[2]; n=int(v) if v.isdigit() else names[v.lower()]
            candidates.append({'text_number':n,'around':s['start'],'cue':s['text'],'verified':False})
    report={'source':str(Path(a.input).resolve()),'duration':d,'candidate_markers':candidates,'status':'needs_semantic_review','note':'Markers and silences are candidates. Agent must map actual question groups and confirm content boundaries.'}
    dump(out/'analysis.json',report)
    print(json.dumps({'duration':d,'transcript_segments':len(rows),'markers':len(candidates),'out':str(out)},ensure_ascii=False))

def cut(a):
    manifest=json.loads(Path(a.manifest).read_text()); rows=manifest['segments']; d=duration(a.input)
    assert rows and len(rows)==manifest['expected_count'],'Segment count mismatch'
    kind=manifest.get('kind','text');assert kind in {'text','question'},'Unknown segment kind'
    seen=set(); questions=set(); end=0
    for s in rows:
        assert re.fullmatch(r'[A-Za-z0-9_-]+',s['id']),'Unsafe segment ID'
        assert s['id'] not in seen,'Duplicate segment ID'; seen.add(s['id'])
        assert s.get('verified') is True and s.get('evidence','').strip(),'Needs semantic verification evidence'
        assert 0<=s['start']<s['end']<=d+0.025,'Out-of-range segment'
        if kind=='text':assert s['start']>=end,'Overlapping Text segments'
        else:assert len(s.get('question_ids',[]))==1,'Question clip must map to exactly one question'
        assert s.get('question_ids'),'Missing mapped questions'
        for q in s['question_ids']:
            assert str(q) not in questions,'Question mapped more than once';questions.add(str(q))
        end=s['end']
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    destinations=[out/(s['id']+'.mp3') for s in rows]+[out/'full.mp3',out/'segments.json']
    assert not any(x.exists() for x in destinations),'Use a fresh output directory; refusing to overwrite prior cuts'
    # Stage all work before publishing the output files.
    with tempfile.TemporaryDirectory(dir=out) as temp:
        stage=Path(temp)
        run(['ffmpeg','-v','error','-i',a.input,'-vn','-c:a','libmp3lame','-q:a','2',stage/'full.mp3'])
        final=[]
        for s in rows:
            p=stage/(s['id']+'.mp3'); expected=s['end']-s['start']
            run(['ffmpeg','-v','error','-ss',s['start'],'-i',a.input,'-t',expected,'-vn','-c:a','libmp3lame','-q:a','2',p])
            measured=duration(p)
            assert abs(measured-expected)<0.2,'Unexpected cut duration'
            final.append({**s,'audio':p.name,'duration':measured})
        dump(stage/'segments.json',{'kind':kind,'source_duration':d,'expected_count':len(final),'full_audio':'full.mp3','segments':final})
        for p in stage.iterdir():p.replace(out/p.name)
    print(json.dumps({'segments':len(final),'out':str(out)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('analyze');x.add_argument('input');x.add_argument('--out',required=True);x.add_argument('--model');x.add_argument('--transcript');x.add_argument('--language',default='en');x.set_defaults(func=analyze)
    x=sub.add_parser('cut');x.add_argument('input');x.add_argument('--manifest',required=True);x.add_argument('--out',required=True);x.set_defaults(func=cut)
    args=p.parse_args()
    try:args.func(args)
    except (ValueError,AssertionError,KeyError,FileNotFoundError) as e:p.exit(1,f'ERROR: {e}\n')
