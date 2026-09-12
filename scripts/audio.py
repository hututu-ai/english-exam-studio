#!/usr/bin/env python3
"""Analyze listening audio and cut semantic segments; Python stdlib only.

Fast paths that matter on a teacher laptop:
  analyze --jobs N         split at real silence and transcribe the chunks in parallel
  analyze --no-asr         silence-only candidates when whisper is unavailable; never blocks the deck
  analyze --reuse          skip ASR when transcript.json already matches this exact audio
  cut --resume             re-encode only the clips that are missing or wrong
  cut --allow-unverified   emit audio without semantic verification, recorded as auto_silence
"""
import argparse,concurrent.futures,difflib,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
from platform_tools import IS_WINDOWS,ffmpeg_bin,ffprobe_bin,force_utf8,install_hints,whisper_bin

AUDIO_COPY_SUFFIXES={'.mp3','.m4a','.aac','.ogg','.oga','.opus'}
MAX_WORKERS=min(4,max(1,(os.cpu_count() or 2)//2))
DEVICE={'mode':'auto','supports_no_gpu':None}

def whisper_exe():
    path=whisper_bin()
    if not path:raise ValueError('找不到 whisper.cpp 可执行文件（whisper-cli / main.exe）。'+install_hints()['whisper'])
    return path

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def run(args,timeout=600):
    try:r=subprocess.run(list(map(str,args)),capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout or 600)
    except FileNotFoundError as error:
        name=str(args[0])
        hint=install_hints().get('ffmpeg') if name.startswith(('ffmpeg','ffprobe')) else install_hints().get('whisper')
        raise ValueError(f'找不到命令 {name}。{hint or ""}') from error
    if r.returncode:raise ValueError(' '.join(map(str,args[:2]))+': '+r.stderr[-2500:])
    return r.stdout

def probe(path):
    return float(run([ffprobe_bin(),'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',path]))

def dump(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def progress(message):
    print(message,file=sys.stderr,flush=True)

def normalised(t):
    return re.sub(r'\s+',' ',str(t).translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))).strip().lower()

def transcript(data):
    if 'segments' in data:rows=data['segments']
    elif 'transcription' in data:
        rows=[{'start':x['offsets']['from']/1000,'end':x['offsets']['to']/1000,'text':x['text']} for x in data['transcription']]
    else:raise ValueError('Transcript needs segments or whisper.cpp transcription')
    prev=-1
    for s in rows:
        assert isinstance(s['text'],str) and 0<=s['start']<s['end'] and s['start']>=prev,'Invalid transcript time'
        prev=s['start']
    return rows

def find_silences(path,noise_db='-35dB',min_len=0.6):
    try:r=subprocess.run([ffmpeg_bin(),'-hide_banner','-i',str(path),'-af',f'silencedetect=n={noise_db}:d={min_len}','-f','null','-'],timeout=300,capture_output=True,text=True,encoding="utf-8",errors="replace")
    except FileNotFoundError as error:raise ValueError('找不到 ffmpeg。'+install_hints()['ffmpeg']) from error
    if r.returncode:raise ValueError(r.stderr[-2000:])
    sil=[];start=None
    for line in r.stderr.splitlines():
        m=re.search(r'silence_start: ([\d.]+)',line)
        if m:start=float(m[1])
        m=re.search(r'silence_end: ([\d.]+)',line)
        if m and start is not None:sil.append({'start':start,'end':float(m[1])});start=None
    return sil

def split_points(silences,duration,jobs,min_chunk=25.0):
    """Pick real silence centres so parallel ASR never cuts inside a word."""
    if jobs<2 or duration<jobs*min_chunk*2:return []
    candidates=[(s['start']+s['end'])/2 for s in silences if s['end']-s['start']>=0.25]
    points=[]
    for i in range(1,jobs):
        target=duration*i/jobs
        near=[c for c in candidates if min_chunk<=c<=duration-min_chunk and all(abs(c-p)>=min_chunk for p in points)]
        if not near:continue
        points.append(min(near,key=lambda c:abs(c-target)))
    return sorted(points)

def whisper_supports_no_gpu():
    """whisper.cpp segfaults on machines without a usable GPU backend; probe once for the flag."""
    if DEVICE['supports_no_gpu'] is None:
        text=''
        exe=whisper_bin()
        if exe:
            try:r=subprocess.run([exe,'--help'],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=20);text=(r.stdout or '')+(r.stderr or '')
            except (OSError,subprocess.SubprocessError):text=''
        DEVICE['supports_no_gpu']='-ng' in text or '--no-gpu' in text
    return DEVICE['supports_no_gpu']

def whisper_rows(wav,model,language,out_stem,threads,timeout,no_gpu=False,retry=True):
    flags=['-ng'] if (no_gpu or DEVICE['mode']=='cpu') else []
    command=[whisper_exe(),'-m',model,'-f',str(wav),'-l',language,'-oj','-of',str(out_stem),'-np','-t',threads]+flags
    try:run(command,timeout=timeout or 600)
    except (ValueError,subprocess.TimeoutExpired) as error:
        if retry and not flags and whisper_supports_no_gpu():
            progress('whisper 的 GPU 后端失败（常见于容器/无显卡/沙箱环境），自动改用 -ng 重新转写')
            DEVICE['mode']='cpu'
            return whisper_rows(wav,model,language,out_stem,threads,timeout,no_gpu=True,retry=False)
        raise
    return transcript(json.loads(Path(str(out_stem)+'.json').read_text(encoding='utf-8')))

def quote_matches(quote,rows):
    words=lambda t:re.findall('[a-z]+',str(t).lower())
    a=words(quote);spoken=' '.join(r.get('text','') for r in rows);b=words(spoken)
    if len(a)<3:return False,0.0
    score=max((difflib.SequenceMatcher(None,a,b[i:i+len(a)]).ratio() for i in range(max(1,len(b)-len(a)+1))),default=0.0)
    return (normalised(quote) in normalised(spoken)) or score>=0.65,round(score,3)

def analyze(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    source=Path(a.input).resolve();source_hash=sha256(source)
    d=probe(source)
    progress(f'原音 {d/60:.1f} 分钟，指纹 {source_hash[:12]}')
    model=a.model or os.environ.get('WHISPER_MODEL')
    cached=out/'transcript.json';rows=None
    if a.reuse and cached.is_file():
        old=json.loads(cached.read_text(encoding='utf-8'))
        if old.get('source_audio_sha256')==source_hash and old.get('segments'):
            rows=transcript(old);progress(f'复用已有转写（{len(rows)} 段），跳过 ASR 与解码')
    if rows is None and a.transcript:
        imported=json.loads(Path(a.transcript).read_text(encoding='utf-8'))
        if imported.get('source_audio_sha256')!=source_hash:raise ValueError('外部转写必须绑定当前原音 SHA256，不能复用未知来源转写')
        rows=transcript(imported)
    wav=out/'asr.wav'
    if rows is None:
        progress('生成 16k 单声道工作副本…')
        run([ffmpeg_bin(),'-y','-v','error','-i',str(source),'-vn','-ar','16000','-ac','1',str(wav)])
    sil=find_silences(source)
    dump(out/'silences.json',sil)
    progress(f'静音候选 {len(sil)} 处')
    if rows is None and a.no_asr:
        gaps=[(sil[i]['end'],sil[i+1]['start']) for i in range(len(sil)-1)]
        blocks=[{'start':round(s,2),'end':round(e,2),'length':round(e-s,2)} for s,e in gaps if e-s>=a.min_gap]
        dump(out/'speech_blocks.json',blocks)
        rows=[]
        progress(f'--no-asr：给出 {len(blocks)} 个可能的文本块（按静音切分），边界必须人工确认')
    elif rows is None:
        if not model or not Path(model).is_file():raise ValueError('Supply --model LOCAL_MODEL or --transcript TIMED_JSON, or fall back to --no-asr')
        if a.no_gpu:DEVICE['mode']='cpu'
        jobs=max(1,min(a.jobs,os.cpu_count() or 1));threads=max(1,min(a.threads,(os.cpu_count() or 1)//jobs))
        points=split_points(sil,d,jobs)
        spans=list(zip([0.0]+points,points+[d]))
        progress(f'ASR：{len(spans)} 个分片并行，每片 {threads} 线程（源 {str(source) if not wav.is_file() else "16k wav"}）')
        def work(item):
            index,(start,end)=item
            piece=out/f'asr-part{index}.wav'
            run([ffmpeg_bin(),'-y','-v','error','-ss',start,'-t',end-start,'-i',str(wav if wav.is_file() else source),'-ar','16000','-ac','1',str(piece)])
            return index,start,whisper_rows(piece,model,a.language,out/f'whisper-part{index}',threads,a.timeout)
        merged=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures=[pool.submit(work,item) for item in enumerate(spans)]
            try:
                for future in concurrent.futures.as_completed(futures):
                    index,start,part=future.result()
                    progress(f'  分片 {index+1}/{len(spans)} 完成：{len(part)} 段')
                    merged+=[{'start':round(r['start']+start,3),'end':round(r['end']+start,3),'text':r['text'].strip()} for r in part]
            except subprocess.TimeoutExpired as e:
                raise ValueError(f'ASR 超时（{a.timeout}s）：改 --no-asr 或加大 --timeout，不要无限等待') from e
        rows=[r for r in sorted(merged,key=lambda r:r['start']) if r['text']]
        for piece in list(out.glob('asr-part*.wav'))+list(out.glob('whisper-part*.json')):piece.unlink(missing_ok=True)
    assert all(x['end']<=d+0.5 for x in (rows or [{'end':0}])),'Transcript exceeds source duration'
    dump(out/'transcript.json',{'source':str(source),'source_audio_sha256':source_hash,'duration':d,'segments':rows})
    progress(f'转写 {len(rows)} 段 → transcript.json（已绑定原音指纹，可 --reuse 复用）')
    names={x:i+1 for i,x in enumerate('one two three four five six seven eight nine ten eleven twelve'.split())}
    candidates=[]
    for s in rows:
        for m in re.finditer(r'\btext\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b|第\s*(\d+)\s*段',s['text'],re.I):
            v=m[1] or m[2];n=int(v) if v.isdigit() else names[v.lower()]
            candidates.append({'text_number':n,'around':s['start'],'cue':s['text'],'verified':False})
    report={'source':str(source),'source_audio_sha256':source_hash,'duration':d,'mode':'no_asr' if a.no_asr else 'asr','device':DEVICE['mode'],
            'transcript_segments':len(rows),'silences':len(sil),'candidate_markers':candidates,
            'chunk_parallelism':max(1,a.jobs),'status':'needs_semantic_review',
            'note':'Markers and silences are candidates. Agent must map actual question groups and confirm content boundaries.'}
    dump(out/'analysis.json',report)
    print(json.dumps({**{k:report[k] for k in ['duration','mode','transcript_segments','silences','chunk_parallelism']},**{'markers':len(candidates),'out':str(out)}},ensure_ascii=False))

def cut(a):
    manifest=json.loads(Path(a.manifest).read_text(encoding='utf-8'));rows=manifest['segments']
    source=Path(a.input).resolve();d=probe(source);source_hash=sha256(source)
    assert rows and len(rows)==manifest['expected_count'],'Segment count mismatch'
    kind=manifest.get('kind','text');assert kind in {'text','question'},'Unknown segment kind'
    seen=set();questions=set();end=0
    for s in rows:
        assert re.fullmatch(r'[A-Za-z0-9_-]+',s['id']),'Unsafe segment ID'
        assert s['id'] not in seen,'Duplicate segment ID';seen.add(s['id'])
        assert s.get('evidence','').strip(),'Needs a reason in evidence'
        assert s.get('verified') is True or a.allow_unverified,'Needs semantic verification evidence, or pass --allow-unverified for a silence-based pass'
        assert 0<=s['start']<s['end']<=d+0.025,'Out-of-range segment'
        if kind=='text':assert s['start']>=end,'Overlapping Text segments'
        else:assert len(s.get('question_ids',[]))==1,'Question clip must map to exactly one question'
        assert s.get('question_ids'),'Missing mapped questions'
        for q in s['question_ids']:
            assert str(q) not in questions,'Question mapped more than once';questions.add(str(q))
        end=s['end']
    transcript_rows=[]
    if a.transcript:
        data=json.loads(Path(a.transcript).read_text(encoding='utf-8'));transcript_rows=transcript(data)
        if data.get('source_audio_sha256') and data['source_audio_sha256']!=source_hash:
            raise ValueError('转写来自另一个音频文件：先对本次原音重跑 analyze')
    unverified=[s['id'] for s in rows if s.get('verified') is not True]
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    suffix=source.suffix.lower();keep_full=suffix in AUDIO_COPY_SUFFIXES
    full_name='full'+suffix if keep_full else 'full.mp3'
    previous={}
    if a.resume and (out/'segments.json').is_file():
        previous=json.loads((out/'segments.json').read_text(encoding='utf-8'))
    reusable_source=previous.get('source_audio_sha256')==source_hash
    prior={str(x['id']):x for x in previous.get('segments',[])}
    if not a.resume:
        stale=[x.name for x in [out/full_name,out/'segments.json']+[out/(s['id']+'.mp3') for s in rows] if x.exists()]
        assert not stale,'输出目录已有文件（'+', '.join(stale[:4])+'）；加 --resume 复用或换目录'
    threads=max(1,a.threads);jobs=max(1,a.jobs)
    with tempfile.TemporaryDirectory(dir=out) as temp:
        stage=Path(temp)
        if not (out/full_name).is_file() or not reusable_source:
            progress('准备完整原音…')
            if keep_full:shutil.copy2(source,stage/full_name)
            else:run([ffmpeg_bin(),'-v','error','-threads',threads,'-i',str(source),'-vn','-c:a','libmp3lame','-q:a','2',str(stage/full_name)])
        final=[];todo=[];reused=[]
        for s in rows:
            expected=round(s['end']-s['start'],3);target=out/(s['id']+'.mp3')
            if a.resume and reusable_source and target.is_file() and all(prior.get(s['id'],{}).get(k)==s[k] for k in ['start','end']):
                try:
                    measured=probe(target)
                    if abs(measured-expected)<0.25:reused.append(s['id']);final.append({**s,'audio':target.name,'duration':round(measured,3)});continue
                except ValueError:pass
            todo.append((s,expected))
        def encode(item):
            s,expected=item;p=stage/(s['id']+'.mp3')
            run([ffmpeg_bin(),'-v','error','-threads',threads,'-ss',s['start'],'-i',str(source),'-t',expected,'-vn','-c:a','libmp3lame','-q:a','2',str(p)])
            measured=probe(p)
            assert abs(measured-expected)<0.25,f'{s["id"]}: 裁剪时长异常 {measured:.2f}s'
            return {**s,'audio':s['id']+'.mp3','duration':round(measured,3)}
        if todo:
            progress(f'裁剪 {len(todo)} 个片段（{jobs} 并发）'+(f'，复用 {len(reused)} 个' if reused else ''))
            with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:final+=list(pool.map(encode,todo))
        order=[s['id'] for s in rows];final.sort(key=lambda x:order.index(x['id']))
        checks=[]
        for entry in final:
            if not transcript_rows:continue
            window=[r for r in transcript_rows if r['end']>entry['start'] and r['start']<entry['end']]
            entry['transcript_text']=' '.join(r['text'] for r in window).strip()
            for key,rows_for_check in [('opening_quote',window[:2]),('closing_quote',window[-2:])]:
                quote=entry.get(key)
                if not quote:continue
                ok,score=quote_matches(quote,rows_for_check)
                entry[key+'_match']=score;checks.append({'segment':entry['id'],'check':key,'passed':ok,'score':score})
                if not ok:raise ValueError(f'{entry["id"]} 的 {key} 与该切点的转写不匹配（{score}）：回听或改引句，不能改音频去迁就引文')
        verification='verified' if not unverified else ('auto_silence' if a.allow_unverified else 'mixed')
        dump(stage/'segments.json',{'kind':kind,'source':str(source),'source_audio_sha256':source_hash,'source_duration':round(d,3),
                                    'expected_count':len(final),'full_audio':full_name,'verification_mode':verification,
                                    'unverified':unverified,'quote_checks':checks,'segments':final})
        for p in stage.iterdir():p.replace(out/p.name)
    print(json.dumps({'segments':len(final),'reused':reused,'verification_mode':verification,'full_audio':full_name,'resumed':bool(a.resume),'out':str(out)},ensure_ascii=False))

if __name__=='__main__':
    force_utf8()
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('analyze');x.add_argument('input');x.add_argument('--out',required=True);x.add_argument('--model');x.add_argument('--transcript')
    x.add_argument('--language',default='en');x.add_argument('--no-asr',action='store_true');x.add_argument('--reuse',action='store_true')
    x.add_argument('--jobs',type=int,default=1);x.add_argument('--threads',type=int,default=max(1,(os.cpu_count() or 2)//2))
    x.add_argument('--timeout',type=float,default=0);x.add_argument('--min-gap',type=float,default=1.2);x.add_argument('--no-gpu',action='store_true');x.set_defaults(func=analyze)
    x=sub.add_parser('cut');x.add_argument('input');x.add_argument('--manifest',required=True);x.add_argument('--out',required=True)
    x.add_argument('--transcript');x.add_argument('--allow-unverified',action='store_true');x.add_argument('--resume',action='store_true')
    x.add_argument('--jobs',type=int,default=MAX_WORKERS);x.add_argument('--threads',type=int,default=2);x.set_defaults(func=cut)
    args=p.parse_args()
    if hasattr(args,'timeout'):args.timeout=args.timeout or None
    try:args.func(args)
    except (ValueError,AssertionError,KeyError,FileNotFoundError,subprocess.TimeoutExpired) as e:p.exit(1,f'ERROR: {e}\n')
